"""Bonanza Cambios S.A. (https://www.bonanzacambios.com.py/, Ciudad del Este).

The home page is a 954-byte React shell; its bundle (`assets/main-*.js`) does
``fetch("/api/board")`` every 5 minutes and ``POST /api/calcular`` for the
converter. ``GET /api/board`` answers plain JSON (no browser needed):

    {"actualizado": "2026-10-31T13:02:45.000Z",
     "sucursales": [{"cod": 0, "nombre": "Casa Matriz", "corto": "MATRIZ",
                     "cotizaciones": [{"codigo": 102, "moneda": "Dolar Americano", "prefix": "usa",
                                       "compra": 5830, "venta": 5920, ...}, ...],
                     "arbitrajes": [...]}, ...],
     "historico": ..., "monedasConversor": ...}

`parse()` takes that JSON. Given the HTML shell it returns ERROR (nothing to parse).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from dateutil import parser as dtparser

from ._common import (
    BranchInfo,
    as_text,
    city_from_text,
    error_result,
    finalize,
    payload_kind,
    quotes_excerpt,
    slug,
    strip_accents,
)
from ._http import ACCEPT_JSON, build_evidence, default_headers, http_get, positive_or_none, try_parse_decimal, utcnow
from .base import AdapterInfo, AdapterResult, City, QuoteDraft

BASE = "https://www.bonanzacambios.com.py"
HOME_URL = f"{BASE}/"
API_BOARD = f"{BASE}/api/board"

RULE_JSON = "bonanza json v1 (/api/board: sucursales[].cotizaciones[].prefix/compra/venta, actualizado)"

_PREFIX_TO_ISO = {"usa": "USD", "brasil": "BRL"}
_NAME_TO_ISO = {"dolar americano": "USD", "real": "BRL", "real brasileno": "BRL"}
# Bonanza is a Ciudad del Este house: Casa Matriz and Jebai (Jebai Center) are downtown CDE;
# Paraná Country Club is in Hernandarias (metro area, not CDE proper) -> None.
_BRANCH_CITY: dict[str, City] = {"matriz": "CDE", "jebai": "CDE", "parana": None, "asuncion": "ASU"}
CURRENCIES: frozenset[str] = frozenset({"USD", "BRL"})


def _branch(suc: dict[str, Any]) -> BranchInfo:
    corto = str(suc.get("corto") or suc.get("nombre") or suc.get("cod") or "?")
    name = str(suc.get("nombre") or corto)
    key = slug(corto) or slug(name)
    city = _BRANCH_CITY.get(key, city_from_text(name))
    return BranchInfo(f"bonanza-{key}", name, city, str(suc.get("cod", key)))


def _iso(row: dict[str, Any]) -> str | None:
    prefix = str(row.get("prefix") or "").lower()
    if prefix in _PREFIX_TO_ISO:
        return _PREFIX_TO_ISO[prefix]
    return _NAME_TO_ISO.get(strip_accents(str(row.get("moneda") or "")).lower())


class BonanzaAdapter:
    info = AdapterInfo(
        id="bonanza",
        name="Bonanza Cambios",
        kind="exchange_house",
        method="official_api",
        integration="endpoint_interno",
        url=HOME_URL,
        capabilities=["branch_table", "buy_sell", "usd_pyg", "brl_pyg", "declared_update_ts", "json_endpoint"],
        limitations=[
            "endpoint JSON não documentado (/api/board, usado pelo SPA); pode mudar sem aviso",
            "cotação de balcão indicativa; valor efetivo depende do montante e da filial",
            "Paraná Country (Hernandarias) fica sem cidade (city=None)",
        ],
        cities=["CDE", "ASU"],
        currencies=["USD", "BRL", "PYG"],
        poll_interval_s=300,
        allowed_domains=["www.bonanzacambios.com.py"],
    )
    stale_after = timedelta(hours=36)

    async def fetch(self, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        out = await http_get(API_BOARD, headers=default_headers(ACCEPT_JSON, {"Referer": HOME_URL}))
        if not out.ok:
            return out.failure(self.info.id)
        return self.parse(out.text, captured_at=captured_at, url=out.url)

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:  # noqa: ARG002
        kind = payload_kind(raw)
        text = as_text(raw)
        if kind == "empty":
            return error_result("empty payload")
        if kind == "html":
            return error_result("home page is a JS shell (no data); parse() needs the /api/board JSON")
        try:
            data = json.loads(text)
        except ValueError as exc:
            return error_result(f"invalid JSON: {exc}")
        if not isinstance(data, dict) or not isinstance(data.get("sucursales"), list):
            return error_result("JSON has no 'sucursales' list; API changed?")
        declared: datetime | None = None
        if data.get("actualizado"):
            try:
                declared = dtparser.isoparse(str(data["actualizado"]))
            except (ValueError, TypeError):
                pass
        issues: list[str] = []
        quotes: list[QuoteDraft] = []
        for suc in data["sucursales"]:
            if not isinstance(suc, dict):
                continue
            binfo = _branch(suc)
            seen: set[str] = set()
            for row in suc.get("cotizaciones") or []:
                if not isinstance(row, dict):
                    continue
                iso = _iso(row)
                if iso not in CURRENCIES:
                    continue
                buy = positive_or_none(try_parse_decimal(row.get("compra")))
                sell = positive_or_none(try_parse_decimal(row.get("venta")))
                if buy is None and sell is None:
                    issues.append(f"{binfo.name}: {iso} without positive prices")
                    continue
                seen.add(iso)
                quotes.append(
                    QuoteDraft(
                        source_id=self.info.id, base=iso, quote="PYG", buy=buy, sell=sell,  # type: ignore[arg-type]
                        unit_note=f"PYG por 1 {iso}", modality="cash", kind="indicative", channel="physical",
                        city=binfo.city, branch_id=binfo.id, declared_updated_at=declared,
                    )
                )
            for missing in sorted(CURRENCIES - seen):
                issues.append(f"{binfo.name}: missing {missing}")
        evidence = build_evidence(
            source_id=self.info.id, kind="json", url=url, captured_at=captured_at, raw=text, rules=[RULE_JSON],
            excerpt_text=quotes_excerpt(quotes, header=f"actualizado={data.get('actualizado')}"),
        )
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)


adapter = BonanzaAdapter()
