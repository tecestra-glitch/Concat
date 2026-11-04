"""Scappini Câmbio, Foz do Iguaçu (https://scappinicambio.com.br/).

Next.js site, server-rendered. The "Câmbio do dia" section holds one table:
``Dólar | - | USD | 5,05 | 5,70`` and ``Guarani | - | PYG | 1.240 | 1.040``, plus the paragraph
"Data da última atualização: dd/mm/yyyy, HH:MM:SS" (America/Sao_Paulo). Both branches (Matriz, Muffato JK) publish
the same table, so one set of quotes is emitted for the house.

Conventions: USD in BRL per USD, buy = first figure ("compra"), sell = second ("venda").
PYG is written as guaranis por R$ 1 with inverted labels: buy = the lower figure, sell = the higher one.
robots.txt allows "/" and disallows only /admin and /api/.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from selectolax.lexbor import LexborHTMLParser

from ._common import as_text, error_result, finalize, payload_kind, quotes_excerpt
from ._http import (
    ACCEPT_HTML,
    TZ_SAO_PAULO,
    build_evidence,
    default_headers,
    http_get,
    try_parse_decimal,
    utcnow,
)
from .base import AdapterInfo, AdapterResult, AdapterStatus, QuoteDraft
from .icambio import BRL_PYG_RANGE, USD_BRL_RANGE

URL = "https://scappinicambio.com.br/"
RULE = "scappini html v1 ('Câmbio do dia' table: code USD/PYG then compra/venda; p 'Data da última atualização')"
BRANCH_ID = "scappini-foz"
CITY = "FOZ"
_UPDATED_RE = re.compile(r"(\d{2}/\d{2}/\d{4}),?\s*(\d{1,2}:\d{2}(?::\d{2})?)")


def _declared(tree: LexborHTMLParser, issues: list[str]) -> datetime | None:
    for p in tree.css("p"):
        text = p.text(strip=True)
        if "atualização" not in text.lower():
            continue
        m = _UPDATED_RE.search(text)
        if m:
            hhmm = m.group(2)
            fmt = "%d/%m/%Y %H:%M:%S" if hhmm.count(":") == 2 else "%d/%m/%Y %H:%M"
            try:
                return datetime.strptime(f"{m.group(1)} {hhmm}", fmt).replace(tzinfo=TZ_SAO_PAULO)
            except ValueError:
                break
    issues.append("'Data da última atualização' not found or unreadable")
    return None


def _code_index(tokens: list[str], code: str) -> int | None:
    """Cell carrying the ISO code: 'USD' or 'Dólar-USD' (name and code share one cell on the site)."""
    for i, tok in enumerate(tokens):
        if tok == code or tok.endswith(f"-{code}"):
            return i
    return None


def _is_rates_table(table) -> bool:
    """The rates table is the one whose rows carry both the USD and the PYG code."""
    tokens = [c.text(strip=True) for tr in table.css("tr") for c in tr.css("td, th")]
    return _code_index(tokens, "USD") is not None and _code_index(tokens, "PYG") is not None


def _figures(tr_tokens: list[str], code_index: int) -> list[Decimal]:
    out: list[Decimal] = []
    for tok in tr_tokens[code_index + 1:]:
        value = try_parse_decimal(tok, "pt_BR") if tok and tok != "-" else None
        if value is not None and value > 0:
            out.append(value)
        if len(out) == 2:
            break
    return out


class ScappiniAdapter:
    # html page: the collector does the conditional GET on info.url, the adapter only parses
    conditional_get = True

    info = AdapterInfo(
        id="scappini",
        name="Scappini Câmbio",
        kind="exchange_house",
        method="html",
        url=URL,
        capabilities=["buy_sell", "usd_brl", "brl_pyg", "declared_update_ts", "board_foz"],
        limitations=[
            "uma tabela para a casa (Matriz e Muffato JK publicam os mesmos valores)",
            "PYG escrito como guaranis por R$ 1 com rótulos invertidos (tratado no parser)",
            "cotação de balcão indicativa; o site pede confirmação no atendimento",
            "o HTML da seção pode mudar de layout (ERROR se a tabela sumir)",
        ],
        cities=[CITY],
        currencies=["USD", "BRL", "PYG"],
        poll_interval_s=300,
        allowed_domains=["scappinicambio.com.br"],
    )
    stale_after = timedelta(hours=72)

    async def fetch(self, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        page = await http_get(URL, headers=default_headers(ACCEPT_HTML))
        if not page.ok:
            return page.failure(self.info.id)
        return self.parse(page.text, captured_at=captured_at, url=page.url)

    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:  # noqa: ARG002
        kind = payload_kind(raw)
        if kind == "empty":
            return error_result("empty payload")
        if kind == "json":
            return error_result("JSON payload; expected the HTML page")
        text = as_text(raw)
        tree = LexborHTMLParser(text)
        evidence = build_evidence(source_id=self.info.id, kind="html", url=url, captured_at=captured_at,
                                  raw=text, rules=[RULE])
        table = next((t for t in tree.css("table") if _is_rates_table(t)), None)
        if table is None:
            return AdapterResult(status=AdapterStatus.ERROR, quotes=[], evidence=evidence,
                                 message="'Câmbio do dia' table not found (layout changed?)")
        issues: list[str] = []
        declared = _declared(tree, issues)
        quotes: list[QuoteDraft] = []
        for tr in table.css("tr"):
            tokens = [c.text(strip=True) for c in tr.css("td, th")]
            for code in ("USD", "PYG"):
                idx = _code_index(tokens, code)
                if idx is None:
                    continue
                figs = _figures(tokens, idx)
                if len(figs) < 2:
                    issues.append(f"{code}: missing figures")
                    continue
                quote = self._quote(code, figs[0], figs[1], declared)
                if quote is None:
                    issues.append(f"{code}: implausible values {figs[0]}/{figs[1]}")
                    continue
                quotes.append(quote)
        if not any(q.base == "USD" for q in quotes):
            issues.append("missing USD row")
        if not any(q.quote == "PYG" for q in quotes):
            issues.append("missing PYG row")
        evidence.excerpt = quotes_excerpt(quotes, header="scappini 'Câmbio do dia'")
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after, empty_message="no USD or PYG rows parsed")

    def _quote(self, code: str, compra: Decimal, venda: Decimal, declared: datetime | None) -> QuoteDraft | None:
        if code == "USD":
            if not (USD_BRL_RANGE[0] <= compra <= USD_BRL_RANGE[1] and USD_BRL_RANGE[0] <= venda <= USD_BRL_RANGE[1]):
                return None
            return QuoteDraft(
                source_id=self.info.id, base="USD", quote="BRL", buy=compra, sell=venda, unit_note="BRL por 1 USD",
                modality="cash", kind="indicative", channel="physical", city=CITY, branch_id=BRANCH_ID,
                context={"board": "cambio_do_dia", "label_convention": "direct"}, declared_updated_at=declared,
            )
        # guaranis por R$ 1 com rótulos invertidos: a "compra" maior é o que o cliente paga para ter R$ 1
        buy, sell = venda, compra
        if not (BRL_PYG_RANGE[0] <= buy <= BRL_PYG_RANGE[1] and BRL_PYG_RANGE[0] <= sell <= BRL_PYG_RANGE[1]):
            return None
        return QuoteDraft(
            source_id=self.info.id, base="BRL", quote="PYG", buy=buy, sell=sell,
            unit_note="PYG por 1 BRL (site escreve guaranis por R$ 1 com rótulos invertidos)",
            modality="cash", kind="indicative", channel="physical", city=CITY, branch_id=BRANCH_ID,
            context={"board": "cambio_do_dia", "label_convention": "inverted_pyg"}, declared_updated_at=declared,
        )


adapter = ScappiniAdapter()
