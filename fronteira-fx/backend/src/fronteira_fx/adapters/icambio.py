"""Casas de câmbio de Foz que usam a plataforma iCâmbio (Iguassu, Cataratas, Atlas).

One adapter for the platform, parameterised per house (`HOUSES`). Two transports, both verified on 2026-11-03/04:

* ``json`` (Cataratas, Atlas): the widget calls ``GET https://icambio.com.br/Cliente/api/cotacoes.php?tenant=N``
  (tenant 10 = Cataratas, 9 = Atlas) -> ``{"success": true, "data": [{moeda_codigo, valor_compra, valor_venda,
  data_cotacao, ...}]}``. The API is an undocumented internal endpoint of the vendor; no key, no terms page.
* ``html`` (Iguassu): the rates table is rendered server-side in the home page (``table.icambio-table``, rows
  with ``.moeda-codigo``, ``.valor-compra``, ``.valor-venda``; footer ``.ultima-atualizacao``, "Atualizado em:
  dd/mm/yyyy HH:MM").

Conventions (see docs/adapters.md):
* USD rows are quoted in BRL per USD with the usual direction: buy = "compra", sell = "venda".
* Guarani rows (``PYG`` / ``GUA``) are guaranis por R$ 1 with the labels inverted: the "compra" figure is the higher one
  and it is what the client pays to get R$ 1. So buy <- "venda" label, sell <- "compra" label.
* ``USB`` ("Dólar Branco" / notas antigas): no confirmed definition, so it is ignored and the reason is reported.
* Atlas adds IOF 3,5% on the "venda" side: recorded as a `Fee` (per unit, in the quote currency), not in the price.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from ._common import as_text, error_result, finalize, payload_kind, quotes_excerpt
from ._http import (
    ACCEPT_HTML,
    ACCEPT_JSON,
    TZ_SAO_PAULO,
    build_evidence,
    default_headers,
    http_get,
    positive_or_none,
    try_parse_decimal,
    utcnow,
)
from .base import AdapterInfo, AdapterResult, AdapterStatus, EvidenceDraft, Fee, QuoteDraft

API_URL = "https://icambio.com.br/Cliente/api/cotacoes.php"
CITY = "FOZ"
# Sanity bounds: out of range means a broken parse, not a market move.
USD_BRL_RANGE = (Decimal("3"), Decimal("15"))
BRL_PYG_RANGE = (Decimal("500"), Decimal("3000"))
IOF_PCT = Decimal("3.5")
USB_NOTE = "USB (dólar branco / notas antigas) ignorado: definição não confirmada pelo site"


@dataclass(frozen=True, slots=True)
class House:
    id: str
    name: str
    home: str
    transport: str  # "json" | "html"
    tenant: int | None = None
    iof: bool = False
    notes: list[str] = field(default_factory=list)


HOUSES: dict[str, House] = {
    "iguassu": House(
        id="iguassu", name="Iguassu Câmbio", home="https://www.iguassucambio.com.br/", transport="html",
        notes=["tabela renderizada no HTML da home (tenant iCâmbio 7); sem chamada JSON própria"],
    ),
    "cataratas": House(
        id="cataratas", name="Cataratas Câmbio", home="https://cataratascambio.com.br/", transport="json", tenant=10,
    ),
    "atlas": House(
        id="atlas", name="Atlas Câmbio", home="https://www.atlascambio.com.br/", transport="json", tenant=9, iof=True,
    ),
}


_TS_HTML = re.compile(r"(\d{2}/\d{2}/\d{4})\s+(\d{1,2}:\d{2})")


def _sp_naive(value: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(value, fmt).replace(tzinfo=TZ_SAO_PAULO)
    except ValueError:
        return None


def _money(text: Any, locale: str) -> Decimal | None:
    """'R$ 5,05' / 'G$ 1.280' / '5.0500' -> Decimal, None when not a positive number."""
    if text is None:
        return None
    if isinstance(text, str):
        text = text.strip()
    return positive_or_none(try_parse_decimal(text, locale))


class ICambioAdapter:
    def __init__(self, house: House) -> None:
        self.house = house
        self.conditional_get = house.transport == "html"  # html pages: the collector does a conditional GET
        self.info = AdapterInfo(
            id=house.id,
            name=house.name,
            kind="exchange_house",
            method="html" if house.transport == "html" else "official_api",
            url=house.home,
            capabilities=["buy_sell", "usd_brl", "brl_pyg", "declared_update_ts", "board_foz"]
            + (["iof_fee"] if house.iof else []),
            limitations=[
                "plataforma iCâmbio: as três casas de Foz compartilham o sistema (uma falha pode afetar as três)",
                "uma tabela por casa (sem separação por filial); o site não diz qual filial está na tabela",
                "dólar branco (USB) ignorado",
                "Guarani escrito como guaranis por R$ 1, com rótulos invertidos (tratado no parser)",
                "cotação de balcão indicativa; valor final pode variar no atendimento",
                "endpoint JSON é interno do fornecedor, sem contrato público (sem chave)" if house.transport == "json"
                else "tabela no HTML da home; o layout pode mudar",
            ]
            + house.notes,
            cities=[CITY],
            currencies=["USD", "BRL", "PYG"],
            poll_interval_s=300,
            allowed_domains=[_host(house.home), "icambio.com.br"] if house.transport == "json" else [_host(house.home)],
        )
        self.stale_after = timedelta(hours=72)  # no weekend updates

    async def fetch(self, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        if self.house.transport == "json":
            url = f"{API_URL}?tenant={self.house.tenant}"
            res = await http_get(url, headers=default_headers(ACCEPT_JSON))
        else:
            url = self.house.home
            res = await http_get(url, headers=default_headers(ACCEPT_HTML))
        if not res.ok:
            return res.failure(self.info.id)
        return self.parse(res.text, captured_at=captured_at, url=res.url)

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:  # noqa: ARG002
        kind = payload_kind(raw)
        if kind == "empty":
            return error_result("empty payload")
        if self.house.transport == "json":
            if kind != "json":
                return error_result("expected the iCâmbio JSON API")
            return self._parse_json(as_text(raw), captured_at=captured_at, url=url)
        if kind == "json":
            return error_result("JSON payload; expected the home page HTML")
        return self._parse_html(as_text(raw), captured_at=captured_at, url=url)

    # ------------------------------------------------------------------ JSON (Cataratas, Atlas)
    def _parse_json(self, text: str, *, captured_at: datetime, url: str) -> AdapterResult:
        try:
            doc = json.loads(text)
        except ValueError:
            return error_result("invalid JSON from iCâmbio API")
        if not isinstance(doc, dict) or doc.get("success") is not True or not isinstance(doc.get("data"), list):
            return error_result("iCâmbio API returned no data")
        rows: list[tuple[str, str | None, str | None, datetime | None]] = []
        for row in doc["data"]:
            if not isinstance(row, dict):
                continue
            code = str(row.get("moeda_codigo") or "").upper()
            declared = _sp_naive(str(row.get("data_cotacao") or ""), "%Y-%m-%d %H:%M:%S")
            rows.append((code, row.get("valor_compra"), row.get("valor_venda"), declared))
        evidence = build_evidence(
            source_id=self.info.id, kind="json", url=url, captured_at=captured_at, raw=text,
            rules=[f"icambio json v1 (cotacoes.php tenant={self.house.tenant}: moeda_codigo/valor_compra/valor_venda)"],
        )
        return self._build(rows, captured_at=captured_at, evidence=evidence, locale="en_US",
                           source_label=f"{self.house.name} iCâmbio tenant {self.house.tenant}")

    # ------------------------------------------------------------------ HTML (Iguassu)
    def _parse_html(self, text: str, *, captured_at: datetime, url: str) -> AdapterResult:
        tree = LexborHTMLParser(text)
        table = tree.css_first("table.icambio-table")
        evidence = build_evidence(
            source_id=self.info.id, kind="html", url=url, captured_at=captured_at, raw=text,
            rules=["icambio html v1 (table.icambio-table cells .moeda-codigo, .valor-compra, .valor-venda; footer)"],
        )
        if table is None:
            return AdapterResult(status=AdapterStatus.ERROR, quotes=[], evidence=evidence,
                                 message="widget table table.icambio-table not found (layout changed?)")
        declared = None
        footer = tree.css_first(".ultima-atualizacao")
        if footer is not None:
            m = _TS_HTML.search(footer.text(strip=True))
            if m:
                declared = _sp_naive(f"{m.group(1)} {m.group(2)}", "%d/%m/%Y %H:%M")
        rows: list[tuple[str, str | None, str | None, datetime | None]] = []
        for tr in table.css("tbody tr"):
            code_node = tr.css_first(".moeda-codigo")
            buy_node = tr.css_first(".valor-compra")
            sell_node = tr.css_first(".valor-venda")
            if code_node is None:
                continue
            rows.append((code_node.text(strip=True).upper(),
                         buy_node.text(strip=True) if buy_node else None,
                         sell_node.text(strip=True) if sell_node else None,
                         declared))
        return self._build(rows, captured_at=captured_at, evidence=evidence, locale="pt_BR",
                           source_label=f"{self.house.name} widget iCâmbio (home)")

    # ------------------------------------------------------------------ shared mapping
    def _build(self, rows, *, captured_at: datetime, evidence: EvidenceDraft, locale: str,
               source_label: str) -> AdapterResult:
        issues: list[str] = []
        notes: list[str] = []
        quotes: list[QuoteDraft] = []
        seen: set[str] = set()
        for code, raw_compra, raw_venda, declared in rows:
            if code == "USB":
                notes.append(USB_NOTE)
                continue
            if code not in ("USD", "PYG", "GUA"):
                continue  # outside BRL/USD/PYG
            key = "PYG" if code in ("PYG", "GUA") else code
            if key in seen:
                continue
            compra = _money(raw_compra, locale)
            venda = _money(raw_venda, locale)
            if compra is None or venda is None:
                issues.append(f"{code}: missing or non-positive price")
                continue
            if key == "USD":
                quote = self._usd(compra, venda, declared)
            else:
                quote = self._pyg(compra, venda, declared)
            if quote is None:
                issues.append(f"{code}: implausible values {compra}/{venda}")
                continue
            seen.add(key)
            quotes.append(quote)
        for missing in sorted({"USD", "PYG"} - seen):
            issues.append(f"missing {missing} row")
        evidence.excerpt = quotes_excerpt(quotes, header=source_label)
        return finalize(quotes=quotes, evidence=evidence, issues=issues, notes=notes, captured_at=captured_at,
                        stale_after=self.stale_after, empty_message="no USD or PYG rows parsed")

    def _usd(self, compra: Decimal, venda: Decimal, declared: datetime | None) -> QuoteDraft | None:
        if not (USD_BRL_RANGE[0] <= compra <= USD_BRL_RANGE[1] and USD_BRL_RANGE[0] <= venda <= USD_BRL_RANGE[1]):
            return None
        fees = []
        if self.house.iof:
            fees.append(_iof(venda, "BRL"))
        return QuoteDraft(
            source_id=self.info.id, base="USD", quote="BRL", buy=compra, sell=venda, unit_note="BRL por 1 USD",
            modality="cash", kind="indicative", channel="physical", city=CITY, branch_id=f"{self.house.id}-foz",
            context={"board": "icambio", "label_convention": "direct"}, fees=fees, declared_updated_at=declared,
        )

    def _pyg(self, compra_label: Decimal, venda_label: Decimal, declared: datetime | None) -> QuoteDraft | None:
        # PYG rows are guaranis por R$ 1 with inverted labels: the house's buy is the lower figure ("venda" label)
        buy, sell = venda_label, compra_label
        if not (BRL_PYG_RANGE[0] <= buy <= BRL_PYG_RANGE[1] and BRL_PYG_RANGE[0] <= sell <= BRL_PYG_RANGE[1]):
            return None
        fees = []
        if self.house.iof:
            # IOF incide sobre o valor em BRL: 3,5% de R$ 1 por unidade da moeda-base (BRL), não em guaranis
            fees.append(_iof_brl_notional())
        return QuoteDraft(
            source_id=self.info.id, base="BRL", quote="PYG", buy=buy, sell=sell,
            unit_note="PYG por 1 BRL (site escreve guaranis por R$ 1 com rótulos invertidos)",
            modality="cash", kind="indicative", channel="physical", city=CITY, branch_id=f"{self.house.id}-foz",
            context={"board": "icambio", "label_convention": "inverted_pyg"}, fees=fees,
            declared_updated_at=declared,
        )


def _iof(venda: Decimal, currency: str) -> Fee:
    amount = (venda * IOF_PCT / Decimal(100)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return Fee(label="IOF +3,5% sobre a venda (por unidade)", amount=amount, currency=currency)  # type: ignore[arg-type]


def _iof_brl_notional() -> Fee:
    """IOF de 3,5% sobre R$ 1 (moeda-base do par BRL/PYG): 0,0350 BRL por unidade."""
    amount = (IOF_PCT / Decimal(100)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    return Fee(label="IOF +3,5% sobre o valor em BRL (por R$ 1)", amount=amount, currency="BRL")


def _host(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).hostname or ""


ADAPTERS: dict[str, ICambioAdapter] = {hid: ICambioAdapter(h) for hid, h in HOUSES.items()}
