"""Modelflare routing, prefix stripping, and bilingual error mapping.

Nothing here calls the network.
"""

from __future__ import annotations

import io
import sys
from unittest.mock import Mock

import pytest
import requests
from rich.console import Console

from hedge_fund import run
from hedge_fund.llm import DEFAULT_MODEL, LLMCallError, make_llm, provider_for
from hedge_fund.llm.client import ChatLLM
from hedge_fund.llm.modelflare_errors import explain, wire_model
from hedge_fund.llm.registry import PROVIDER_ENV_VARS
from hedge_fund.paths import EXAMPLE_MANDATE
from hedge_fund.tui.modelflare_onboarding import api_root, should_prompt_modelflare
from hedge_fund.tui.shared import DEFAULT_MODEL_LABEL


def test_provider_for_keeps_openai_ids_and_prefixes_modelflare():
    assert next(iter(PROVIDER_ENV_VARS)) == "Modelflare"
    assert PROVIDER_ENV_VARS["Modelflare"] == "MODELFLARE_API_KEY"
    assert provider_for("modelflare/gpt-6-sol") == "Modelflare"
    assert provider_for("modelflare/claude-sonnet-5") == "Modelflare"
    assert provider_for("gpt-6-sol") == "OpenAI"
    assert provider_for("gpt-6-astra") == "OpenAI"
    assert provider_for("claude-opus-5-5") == "Anthropic"


def test_default_model_is_modelflare_sol():
    assert DEFAULT_MODEL == "modelflare/gpt-6-sol"
    assert DEFAULT_MODEL_LABEL == "GPT-6 Sol · Modelflare"
    assert wire_model("modelflare/gpt-6-sol") == "gpt-6-sol"
    assert wire_model("gpt-6-sol") == "gpt-6-sol"
    assert wire_model("modelflare/gemini-3.1-pro-preview") == "gemini-3.1-pro-preview"


def test_make_llm_strips_prefix_and_uses_modelflare_base(monkeypatch):
    monkeypatch.setenv("MODELFLARE_API_KEY", "sk-test")
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    monkeypatch.setenv("MODELFLARE_BASE_URL", "https://example.test/v1")
    import langchain_openai

    captured: dict = {}

    class FakeChat:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", FakeChat)
    llm = make_llm("modelflare/gpt-6-sol")
    assert captured["model"] == "gpt-6-sol"
    assert captured["base_url"] == "https://example.test/v1"
    assert captured["api_key"] == "sk-test"
    assert llm.model == "modelflare/gpt-6-sol"
    assert llm.provider == "Modelflare"


def test_api_root_adds_v1_once():
    assert api_root("https://modelflare.dev/v1") == "https://modelflare.dev/v1"
    assert api_root("https://modelflare.dev") == "https://modelflare.dev/v1"
    assert api_root("https://modelflare.dev/v1/") == "https://modelflare.dev/v1"


@pytest.mark.parametrize(
    "status,message,expected",
    [
        (401, "invalid", "API Key 无效或已停用"),
        (402, "payment required", "余额不足"),
        (429, "insufficient quota", "余额不足"),
        (400, "额度不够", "余额不足"),
        (403, "forbidden", "分组无法调用模型 gpt-6-sol"),
        (503, "model_not_found", "分组无法调用模型 gpt-6-sol"),
        (503, "upstream 分组未开放", "分组无法调用模型 gpt-6-sol"),
    ],
)
def test_explain_modelflare_statuses(status, message, expected):
    text = explain(status, message, model="modelflare/gpt-6-sol", provider="Modelflare")
    assert text is not None and expected in text
    assert " / " in text


def test_explain_ignores_other_providers():
    assert explain(401, "invalid", model="gpt-6-sol", provider="OpenAI") is None
    assert explain(402, "insufficient", model="claude-opus-5-5", provider="Anthropic") is None
    assert explain(500, "boom", model="modelflare/gpt-6-sol", provider="Modelflare") is None


class _StatusError(Exception):
    def __init__(self, status: int, message: str = "nope") -> None:
        super().__init__(message)
        self.status_code = status


class _Invoke:
    def __init__(self, error: BaseException) -> None:
        self._error = error

    def invoke(self, messages):
        raise self._error

    def stream(self, messages):
        raise AssertionError("invoke path should not stream")
        yield


class _Stream:
    def __init__(self, error: BaseException) -> None:
        self._error = error

    def invoke(self, messages):
        raise AssertionError("stream path should not invoke")

    def stream(self, messages):
        raise self._error
        yield


def test_complete_maps_invoke_and_stream_only_for_modelflare():
    invoke = _Invoke(_StatusError(401))
    with pytest.raises(LLMCallError, match="invalid or revoked"):
        ChatLLM("modelflare/gpt-6-sol", invoke, provider="Modelflare").complete("s", "u")

    response = requests.Response()
    response.status_code = 403
    response.encoding = "utf-8"
    response._content = b'{"error":"model_not_found"}'
    response._content_consumed = True
    http_error = requests.HTTPError("403")
    http_error.response = response
    with pytest.raises(LLMCallError, match="gpt-6-astra"):
        ChatLLM("modelflare/gpt-6-astra", _Stream(http_error), lambda _: None, "Modelflare").complete("s", "u")

    with pytest.raises(_StatusError):
        ChatLLM("gpt-6-sol", _Invoke(_StatusError(401)), provider="OpenAI").complete("s", "u")

    with pytest.raises(RuntimeError, match="programmer error"):
        ChatLLM("modelflare/gpt-6-sol", _Invoke(RuntimeError("programmer error")), provider="Modelflare").complete("s", "u")


def test_onboarding_respects_an_explicit_other_model(monkeypatch):
    for variable in PROVIDER_ENV_VARS.values():
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)
    assert should_prompt_modelflare() is True

    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("HEDGE_FUND_LLM_MODEL", "gpt-6-sol")
    assert should_prompt_modelflare() is False

    monkeypatch.setenv("HEDGE_FUND_LLM_MODEL", "modelflare/gpt-6-sol")
    assert should_prompt_modelflare() is True

    monkeypatch.setenv("MODELFLARE_API_KEY", "sk-mf")
    assert should_prompt_modelflare() is False


def test_backtest_exits_2_when_the_modelflare_key_is_missing(tmp_path, monkeypatch, capsys):
    mandate = tmp_path / "example.yaml"
    mandate.write_text(EXAMPLE_MANDATE.read_text())
    monkeypatch.setattr(run, "apply_credentials", lambda: None)
    monkeypatch.setattr(run, "ensure_mandates_dir", lambda: tmp_path)
    monkeypatch.delenv("MODELFLARE_API_KEY", raising=False)
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    monkeypatch.setattr(run, "backtest_fund", Mock(side_effect=AssertionError("should not run")))
    monkeypatch.setattr(sys, "argv", [
        "aihf", "backtest", str(mandate), "--universe", "AAPL",
        "--start", "2025-01-06", "--end", "2025-01-13",
    ])
    with pytest.raises(SystemExit) as exc:
        run.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "modelflare.dev/keys" in err and "sign-up" in err
    run.backtest_fund.assert_not_called()


def test_guard_skips_a_non_modelflare_model_and_paper_list(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HEDGE_FUND_LLM_MODEL", "gpt-6-sol")
    monkeypatch.delenv("MODELFLARE_API_KEY", raising=False)
    run._require_modelflare_key(Console(file=io.StringIO()))

    monkeypatch.setattr(run, "apply_credentials", lambda: None)
    monkeypatch.setattr(run, "ensure_mandates_dir", lambda: tmp_path)
    monkeypatch.setattr(run, "PAPER_DIR", tmp_path)
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    monkeypatch.setattr(sys, "argv", ["aihf", "paper", "list"])
    run.main()
    assert capsys.readouterr().out == ""


def test_help_does_not_require_a_modelflare_key(monkeypatch):
    monkeypatch.setattr(run, "apply_credentials", lambda: None)
    monkeypatch.setattr(run, "ensure_mandates_dir", lambda: None)
    monkeypatch.delenv("MODELFLARE_API_KEY", raising=False)
    monkeypatch.delenv("HEDGE_FUND_LLM_MODEL", raising=False)
    monkeypatch.setattr(sys, "argv", ["aihf", "--help"])
    with pytest.raises(SystemExit) as exc:
        run.main()
    assert exc.value.code == 0
