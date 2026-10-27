"""First-run Modelflare key. Shown when the product default has no key.

Saving uses the same ~/.hedge-fund/.env line edit as the other providers.
The probe is urllib on purpose: it must not import the langchain stack.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from rich.text import Text
from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Input, Static

from hedge_fund.llm.modelflare_errors import (
    DEFAULT_BASE_URL,
    SIGNUP_URL,
    explain,
    is_modelflare_model,
)
from hedge_fund.llm.registry import PROVIDER_ENV_VARS
from hedge_fund.tui.keys import missing_key, save_credential
from hedge_fund.tui.palette import BRIGHT, CYAN, GREEN, MUTED


def should_prompt_modelflare() -> bool:
    """True when MODELFLARE_API_KEY is missing and the user is on the default.

    Someone who already has another provider key and pointed
    HEDGE_FUND_LLM_MODEL at a non-Modelflare model is not blocked.
    """
    if not missing_key("Modelflare"):
        return False
    model = os.environ.get("HEDGE_FUND_LLM_MODEL", "").strip()
    if model and not is_modelflare_model(model) and _other_provider_key():
        return False
    return True


def _other_provider_key() -> bool:
    for provider, variable in PROVIDER_ENV_VARS.items():
        if provider != "Modelflare" and os.environ.get(variable):
            return True
    return bool(os.environ.get("MOONSHOT_API_KEY"))


def api_root(base_url: str | None = None) -> str:
    """OpenAI-compatible root, exactly one /v1 suffix."""
    root = (base_url or os.getenv("MODELFLARE_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    if not root.endswith("/v1"):
        root += "/v1"
    return root


def probe(api_key: str, base_url: str | None = None, timeout: float = 20.0) -> str:
    """GET {base}/v1/models, then a tiny gpt-6-sol chat. Success is 已连通."""
    root = api_root(base_url)
    steps = (
        ("GET", f"{root}/models", None),
        ("POST", f"{root}/chat/completions", {
            "model": "gpt-6-sol",
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 8,
        }),
    )
    for method, url, payload in steps:
        failure = _call(method, url, api_key, payload, timeout)
        if failure:
            return failure
    return "已连通"


def _call(method: str, url: str, api_key: str, payload: dict | None, timeout: float) -> str | None:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        return explain(exc.code, body, model="gpt-6-sol", provider="Modelflare") or (
            f"Modelflare HTTP {exc.code}。 / Modelflare returned HTTP {exc.code}."
        )
    except urllib.error.URLError as exc:
        return f"无法连接 Modelflare（{exc.reason}）。 / Could not reach Modelflare ({exc.reason})."
    return None


class ModelflareOnboarding(Screen):
    """One key, the signup link, and the result of the automatic test call."""

    BINDINGS = [Binding("escape", "skip", "skip")]

    def __init__(self) -> None:
        super().__init__()
        self._busy = False

    def compose(self) -> ComposeResult:
        with Vertical(id="mf-onboard"):
            yield Static(Text("Modelflare", style=f"bold {BRIGHT}"), id="mf-title")
            yield Static(Text.assemble(
                ("默认模型是 GPT-6 Sol。注册后复制 Key，粘贴到下面。\n", MUTED),
                ("The default model is GPT-6 Sol. Paste a key to continue.\n", MUTED),
                (SIGNUP_URL, f"underline {CYAN}"),
            ), id="mf-blurb")
            yield Input(password=True, placeholder="MODELFLARE_API_KEY", id="mf-key")
            yield Static("", id="mf-status")
            yield Static(Text.assemble(
                ("enter", f"bold {GREEN}"), ("  save and test   ", MUTED),
                ("esc", f"bold {BRIGHT}"), ("  skip", MUTED),
            ), classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#mf-key", Input).focus()

    @on(Input.Submitted, "#mf-key")
    def _submit(self, event: Input.Submitted) -> None:
        if self._busy:
            return
        key = event.value.strip()
        if not key:
            self._set_status("请粘贴 API Key。 / Paste an API key.")
            return
        save_credential("MODELFLARE_API_KEY", key)
        self._busy = True
        self._set_status("正在测试连通… / Checking the key…")
        self.run_worker(self._probe, thread=True, exclusive=True, exit_on_error=False)

    def _probe(self) -> None:
        try:
            message = probe(os.environ.get("MODELFLARE_API_KEY", ""))
        except Exception as exc:
            message = f"测试失败：{exc} / Probe failed: {exc}"
        self.app.call_from_thread(self._finish, message)

    def _finish(self, message: str) -> None:
        self._busy = False
        self._set_status(message)
        if message == "已连通":
            self.set_timer(0.4, lambda: self.dismiss(True))

    def _set_status(self, message: str) -> None:
        self.query_one("#mf-status", Static).update(message)

    def action_skip(self) -> None:
        if not self._busy:
            self.dismiss(False)
