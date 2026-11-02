from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from fronteira_fx.adapters._common import city_from_text, payload_kind, slug
from fronteira_fx.adapters._http import (
    DEFAULT_TIMEOUT,
    USER_AGENT,
    build_evidence,
    excerpt,
    is_stale,
    looks_blocked,
    parse_decimal,
    sha256_hex,
    try_parse_decimal,
)


@pytest.mark.parametrize(
    ("text", "hint", "expected"),
    [
        ("7.350,00", "auto", Decimal("7350.00")),
        ("7,350", "auto", Decimal("7350")),
        ("7.350", "auto", Decimal("7350")),
        ("7350", "auto", Decimal("7350")),
        ("7,350", "en_US", Decimal("7350")),
        ("7.350", "en_US", Decimal("7.350")),
        ("7,350", "es_PY", Decimal("7.350")),
        ("7.350", "es_PY", Decimal("7350")),
        ("5.800", "es_PY", Decimal("5800")),
        ("3,4", "es_PY", Decimal("3.4")),
        ("3,55", "auto", Decimal("3.55")),
        ("5.4043", "es_PY", Decimal("5.4043")),
        ("5.4043", "auto", Decimal("5.4043")),
        ("1.100,01", "es_PY", Decimal("1100.01")),
        ("1.536,3428", "es_PY", Decimal("1536.3428")),
        ("23.315.467,62", "auto", Decimal("23315467.62")),
        ("1,234,567.89", "auto", Decimal("1234567.89")),
        ("1,234,567", "auto", Decimal("1234567")),
        ("Gs. 5.680", "es_PY", Decimal("5680")),
        ("R$ 5,44", "pt_BR", Decimal("5.44")),
        ("US$ 1.080,37", "pt_BR", Decimal("1080.37")),
        ("  5 401 871 ", "auto", Decimal("5401871")),
        ("-12,5", "pt_BR", Decimal("-12.5")),
        ("0,000", "es_PY", Decimal("0.000")),
        (5750, "auto", Decimal("5750")),
        (3.4, "auto", Decimal("3.4")),
        (Decimal("1.5"), "auto", Decimal("1.5")),
    ],
)
def test_parse_decimal(text: str, hint: str, expected: Decimal) -> None:
    assert parse_decimal(text, hint) == expected  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["", "   ", "sin datos", "Gs.", "--", None, True])
def test_parse_decimal_rejects_non_numbers(bad: object) -> None:
    with pytest.raises((ValueError, TypeError)):
        parse_decimal(bad)  # type: ignore[arg-type]
    assert try_parse_decimal(bad) is None


def test_parse_decimal_ambiguous_multi_separator() -> None:
    with pytest.raises(ValueError):
        parse_decimal("1.23.4", "en_US")


def test_sha256_and_excerpt() -> None:
    assert sha256_hex("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    assert sha256_hex(b"abc") == sha256_hex("abc")
    assert excerpt("  a \n\n b\t c ") == "a b c"
    long = "x" * 5000
    assert len(excerpt(long)) == 2000
    assert excerpt("<td>5.750</td> <i class='x'></i>", strip_tags=True) == "5.750"


def test_build_evidence() -> None:
    now = datetime(2026, 11, 2, tzinfo=UTC)
    ev = build_evidence(
        source_id="x", kind="html", url="https://e.x/", captured_at=now, raw="<b>hi</b>" * 1000, rules=["r1"]
    )
    assert ev.sha256 == sha256_hex("<b>hi</b>" * 1000)
    assert len(ev.excerpt) <= 2000 and "<b>" not in ev.excerpt
    assert ev.rules == ["r1"] and ev.kind == "html" and ev.captured_at == now


def test_is_stale() -> None:
    now = datetime(2026, 11, 2, 12, tzinfo=UTC)
    assert not is_stale(None, now, timedelta(hours=1))
    assert not is_stale(now - timedelta(minutes=30), now, timedelta(hours=1))
    assert is_stale(now - timedelta(hours=2), now, timedelta(hours=1))
    assert is_stale(datetime(2026, 11, 1), now, timedelta(hours=1))  # naive treated as UTC


def test_constants() -> None:
    assert "Mozilla/5.0" in USER_AGENT
    assert DEFAULT_TIMEOUT == 20.0


def test_looks_blocked() -> None:
    assert looks_blocked(403, "")
    assert looks_blocked(429, "")
    assert looks_blocked(200, "<title>Just a moment...</title>")
    assert not looks_blocked(200, "<html>ok</html>")
    assert not looks_blocked(500, "")


def test_city_from_text() -> None:
    assert city_from_text("Ciudad del Este - Km7") == "CDE"
    assert city_from_text("Casa Central - Asuncion") == "ASU"
    assert city_from_text("Asunción") == "ASU"
    assert city_from_text("Sucursal Pedro Juan Caballero") == "PJC"
    assert city_from_text("villamorra") == "ASU"
    assert city_from_text("Hernandarias - Super Carretera") is None
    assert city_from_text("Encarnación") is None
    assert city_from_text("") is None


def test_payload_kind_and_slug() -> None:
    assert payload_kind('  {"a": 1}') == "json"
    assert payload_kind(b"[1]") == "json"
    assert payload_kind("<html>") == "html"
    assert payload_kind("   ") == "empty"
    assert slug("Paraná Country") == "parana-country"
    assert slug("ASUNCIÓN") == "asuncion"
