from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
# Captures that belong only to the adapter tests (maxicambios.html, myd.html, dolarpy.json) live next to them.
LOCAL_FIXTURES = Path(__file__).resolve().parent / "fixtures"

# All HTML/JSON fixtures were captured 2026-10-30 .. 2026-11-02; this instant is "fresh" for all of them.
CAPTURED_AT = datetime(2026, 11, 2, 6, 0, tzinfo=UTC)
# ...and this one is far enough in the future to make every declared timestamp stale.
MUCH_LATER = datetime(2026, 12, 1, 12, 0, tzinfo=UTC)


def load(name: str) -> str:
    """Read a fixture as text. Real pages are not always valid UTF-8 (myd.html declares UTF-8 but
    carries legacy bytes), so undecodable bytes are replaced instead of failing the test run."""
    hits = [base / name for base in (LOCAL_FIXTURES, FIXTURES) if (base / name).exists()]
    if not hits:
        raise FileNotFoundError(f"fixture {name!r} not found in {LOCAL_FIXTURES} or {FIXTURES}")
    if len(hits) > 1:
        raise RuntimeError(f"fixture {name!r} exists in both {LOCAL_FIXTURES} and {FIXTURES}; keep exactly one")
    return hits[0].read_bytes().decode("utf-8", errors="replace")


def load_json(name: str) -> Any:
    return json.loads(load(name))


def without_tables(html: str) -> str:
    """Simulate a layout change: drop every <table> element."""
    return re.sub(r"<table\b.*?</table>", "", html, flags=re.S | re.I)


@pytest.fixture
def captured_at() -> datetime:
    return CAPTURED_AT


@pytest.fixture
def much_later() -> datetime:
    return MUCH_LATER
