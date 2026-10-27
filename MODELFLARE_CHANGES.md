# Modelflare Edition changes

Fork of [virattt/ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) at `29b32f7`. The v2 engine, investor prompts, mandate format, backtest/paper math, other providers, the MIT license, and Virat Singh's attribution are unchanged. The deleted v1 `app/` frontend is not restored.

## Routing

- `hedge_fund/llm/registry.py` — `Modelflare` / `MODELFLARE_API_KEY` is the first `PROVIDER_ENV_VARS` entry (`SUPPORTED_PROVIDERS` follows the dict). Fallback model is `modelflare/gpt-6-sol`.
- `hedge_fund/llm/api_models.json` — six `modelflare/` models prepended. Existing OpenAI `gpt-6-sol` rows stay, so `provider_for("gpt-6-sol")` is still OpenAI. The prefix is what keeps the global model-id lookup from colliding.
- `hedge_fund/llm/client.py` — `DEFAULT_MODEL` is `modelflare/gpt-6-sol`. `make_llm` builds `ChatOpenAI` for Modelflare, strips the `modelflare/` prefix, and uses `MODELFLARE_BASE_URL` or `https://modelflare.dev/v1`. An unlisted `modelflare/` id stays on Modelflare instead of the Anthropic fallback. `ChatLLM.complete` (invoke and stream) remaps Modelflare HTTP failures only.
- `hedge_fund/llm/modelflare_errors.py` — prefix strip (`wire_model`), bilingual messages for 401, 402 / quota / balance / insufficient / 额度 / 余额, and 403 / 503 `model_not_found` / 分组. Other providers and non-HTTP bugs are not rewritten.
- `hedge_fund/tui/shared.py` — default picker label is `GPT-6 Sol · Modelflare`.

## Key gate

- `hedge_fund/tui/modelflare_onboarding.py` — Textual screen: one masked key, signup link, status line. Submit writes `MODELFLARE_API_KEY` with the existing `save_credential` (`~/.hedge-fund/.env`), then urllib `GET {base}/v1/models` and a `max_tokens: 8` chat on `gpt-6-sol`. Success shows 已连通.
- `hedge_fund/tui/app.py` — after credentials load, push that screen when the Modelflare key is missing, unless another provider key is set and `HEDGE_FUND_LLM_MODEL` names a non-Modelflare model.
- `hedge_fund/tui/app.tcss` — styles for the new screen only.
- `hedge_fund/tui/conftest.py` — screen tests set a dummy Modelflare key so they still land on the existing screens.
- `hedge_fund/run.py` — `backtest`, `paper tick`, and `paper run` exit 2 with the signup and keys URLs when the selected model is Modelflare (including the default) and the key is missing. `status`, `list`, `halt`, `resume`, `scorecard`, `stop`, `create`, and `--help` do not.
- `hedge_fund/test_run.py` — the offline engine fixture sets a dummy key so those backtests still exercise the engine.

## Web shell

- `hedge_fund/web.py` — `textual-serve` serves `python -m hedge_fund.tui` on `0.0.0.0` and `PORT` (default 8000). `PUBLIC_URL` defaults to `http://127.0.0.1:$PORT` because textual-serve bakes the bind address into asset URLs.
- `pyproject.toml` — dependency `textual-serve = "^1.1.3"` and script `aihf-web`.
- `poetry.lock` — regenerated with `poetry lock --no-update` (Poetry 1.8.5). `textual-serve` 1.1.3 was already locked via `textual-dev`; the content hash now includes it as a main dependency.
- `Dockerfile` — `python:3.12-slim`, Poetry 1.8.5, `poetry install --only main`, `CMD ["poetry", "run", "aihf-web"]`, `VOLUME /root/.hedge-fund`.
- `.dockerignore` — keeps `.git`, virtualenvs, pytest/mypy caches, `__pycache__`, and `.env` out of the build context.
- `docker-compose.yml` — build `.`, `127.0.0.1:8000:8000`, `MODELFLARE_API_KEY`, `MODELFLARE_BASE_URL` default `https://modelflare.dev/v1`, `./data:/root/.hedge-fund`.
- `render.yaml` — one Docker web service and a disk at `/root/.hedge-fund`.
- `.github/workflows/mf-upstream-sync.yml` — weekly merge (never rebase) of `virattt/ai-hedge-fund`; PR on success, issue on conflict.
- `.github/workflows/mf-docker.yml` — `workflow_dispatch` only; `docker build` without push.
- `.env.example` — `MODELFLARE_API_KEY` and a commented base URL prepended. Existing provider lines are unchanged. No secrets.
- `README.md` — `<!-- MF-START -->` … `<!-- MF-END -->` block only. Original README below is unchanged. The block states the single-user limit (every browser session is a TUI process sharing `~/.hedge-fund/.env` and the ledger) and a Caddy basic-auth example.

## Tests

- `hedge_fund/llm/test_modelflare.py` — provider routing, default model, prefix strip, `explain` for 401/402/403 and non-Modelflare, invoke/stream mapping, onboarding decision, CLI exit 2, and commands that must not require the key. No live LLM call.
