"""Friendly Modelflare failures. Other providers are not rewritten.

ChatOpenAI raises ``openai.APIStatusError`` (and langchain sometimes wraps
that text as ``Error code: <status>``). ``requests`` and ``httpx`` expose the
status on the response. A bug with no HTTP status is left alone.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from hedge_fund.llm.registry import provider_for

SIGNUP_URL = "http://modelflare.dev/sign-up?utm_source=github&utm_campaign=mf_ai-hedge-fund"
KEYS_URL = "https://modelflare.dev/keys"
WALLET_URL = "https://modelflare.dev/wallet"
DEFAULT_BASE_URL = "https://modelflare.dev/v1"

_KEY = (
    "Modelflare API Key 无效或已停用。请到 https://modelflare.dev/keys 复制新的 Key。"
    " / Your Modelflare API key is invalid or revoked. Get a key at https://modelflare.dev/keys"
)
_BALANCE = (
    f"Modelflare 余额不足，请充值：{WALLET_URL}"
    f" / Insufficient Modelflare balance. Top up at {WALLET_URL}"
)
_BILLING = re.compile(r"quota|balance|insufficient|额度|余额", re.IGNORECASE)
_ERROR_CODE = re.compile(r"Error code:\s*(\d{3})")
_HTTP_TYPES = frozenset({
    "APIStatusError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "RateLimitError",
    "InternalServerError",
    "HTTPError",
    "HTTPStatusError",
})


def wire_model(model: str) -> str:
    """Id sent to the Modelflare API. The registry prefix avoids OpenAI's gpt-6-sol."""
    return model.removeprefix("modelflare/")


def is_modelflare_model(model: str | None) -> bool:
    """True for a registry Modelflare id or any modelflare/ prefixed id."""
    if not model:
        return False
    if model.startswith("modelflare/"):
        return True
    return provider_for(model) == "Modelflare"


def is_modelflare_call(model: str | None, provider: str | None) -> bool:
    return provider == "Modelflare" or is_modelflare_model(model)


def explain(status_code: int | None, message: str = "", *, model: str = "", provider: str | None = None) -> str | None:
    """Bilingual Modelflare message, or None when this failure should pass through.

    401 is an invalid key. 402, or a body matching quota/balance/insufficient/额度/余额,
    is an empty balance. 403, a 503 ``model_not_found``, or a body containing 分组,
    means the key's group cannot call the model. Non-Modelflare calls return None.
    """
    if not is_modelflare_call(model, provider):
        return None
    text = message or ""
    if status_code == 401:
        return _KEY
    if status_code == 402 or _BILLING.search(text):
        return _BALANCE
    grouped = "model_not_found" in text.lower() or "分组" in text
    if status_code == 403 or (status_code == 503 and grouped) or "分组" in text:
        shown = wire_model(model) or model or "unknown"
        return (
            f"当前 Key 的分组无法调用模型 {shown}，请在 https://modelflare.dev/keys 调整分组，或换一个模型。"
            f" / This key's group cannot call {shown}. Change the group at https://modelflare.dev/keys or pick another model."
        )
    return None


def friendly_llm_error(exc: BaseException, *, model: str, provider: str | None) -> str | None:
    """Map a Modelflare HTTP failure. Return None to re-raise the original error."""
    if not is_modelflare_call(model, provider):
        return None
    status, text = _status_and_text(exc)
    if status is None:
        return None
    return explain(status, text, model=model, provider=provider or "Modelflare")


def _status_and_text(exc: BaseException) -> tuple[int | None, str]:
    texts: list[str] = []
    status: int | None = None
    current: BaseException | None = exc
    seen: set[int] = set()
    httpish = False
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        texts.append(str(current))
        if type(current).__name__ in _HTTP_TYPES or type(current).__module__.split(".")[0] in {"openai", "httpx", "requests"}:
            httpish = True
        body = getattr(current, "body", None)
        if isinstance(body, str):
            texts.append(body)
        elif isinstance(body, (Mapping, list)):
            texts.append(json.dumps(body, ensure_ascii=False, default=str))
        response = getattr(current, "response", None)
        if response is not None:
            try:
                raw = response.text
            except Exception:
                raw = None
            if isinstance(raw, str):
                texts.append(raw)
            code = getattr(response, "status_code", None)
            if status is None and isinstance(code, int):
                status = code
                httpish = True
        code = getattr(current, "status_code", None)
        if status is None and isinstance(code, int):
            status = code
            httpish = True
        if status is None and type(current).__name__ == "HTTPError":
            code = getattr(current, "code", None)
            if isinstance(code, int):
                status = code
                httpish = True
        current = current.__cause__
    text = "\n".join(texts)
    # Wrapped OpenAI/langchain errors often keep only "Error code: 401" in the
    # message. A bug that does not say that has no status and is not remapped.
    if status is None and (httpish or _ERROR_CODE.search(text)):
        match = _ERROR_CODE.search(text)
        if match:
            status = int(match.group(1))
    return status, text
