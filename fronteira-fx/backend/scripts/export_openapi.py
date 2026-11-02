"""Export the OpenAPI spec to docs/openapi.json (repo root /docs).

Usage: uv run python scripts/export_openapi.py [output_path]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fronteira_fx.config import Settings
from fronteira_fx.main import create_app


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2] / "docs" / "openapi.json"
    app = create_app(Settings(_env_file=None, database_url="sqlite://", auto_create_schema=False))
    spec = app.openapi()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out} ({len(spec['paths'])} paths)")


if __name__ == "__main__":
    main()
