"""Entrypoint for the Vercel Python runtime (the Vercel project root is `fronteira-fx/backend`).

Vercel looks for an ASGI `app` in app.py at the project root. The package lives in `src/`, so that folder goes on
`sys.path` first. Local runs keep using `uv run uvicorn fronteira_fx.main:app`.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fronteira_fx.main import app  # noqa: E402

__all__ = ["app"]
