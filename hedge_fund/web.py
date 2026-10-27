"""Browser shell for the existing Textual app.

textual-serve starts one TUI process per browser connection. Those processes
share ~/.hedge-fund (the key file and the paper ledger). Single-user self-host
only — do not publish it without a reverse proxy.
"""

from __future__ import annotations

import os
import sys

from textual_serve.server import Server


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    # textual-serve puts `host` into asset URLs. 0.0.0.0 is not a browser
    # address, so PUBLIC_URL wins and local use defaults to the published port.
    # Use this interpreter so the child sees the same env. `python` is not on
    # PATH in every image; python:3.12-slim has it, a venv often does not.
    public_url = os.getenv("PUBLIC_URL") or f"http://127.0.0.1:{port}"
    Server(
        f"{sys.executable} -m hedge_fund.tui",
        host="0.0.0.0",
        port=port,
        public_url=public_url,
    ).serve()


if __name__ == "__main__":
    main()
