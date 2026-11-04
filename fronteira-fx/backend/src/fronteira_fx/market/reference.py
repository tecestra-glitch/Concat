"""Referências de câmbio (módulo `market`, unidade U03): Frankfurter (taxas de referência do BCE), PTAX do Banco
Central (série SGS 1, venda) e Open Exchange Rates (só com `OXR_APP_ID`).

Tudo aqui é REFERÊNCIA: `ReferenceQuote.referencia` é sempre verdadeiro e a classe recusa o contrário. Nenhuma
cotação deste módulo é executável, nenhuma é contraparte e nenhuma vira aresta do grafo ou do motor de ciclos.
O BCE não serve para transação; Frankfurter e OXR servem para medir desvio entre fontes.

Orçamento da Open Exchange Rates: o plano gratuito permite 1.000 requisições por mês. O contador fica no banco
(`reference_api_usage`, mês em UTC) e cada chamada é reservada ANTES do HTTP, com um UPDATE condicional. Coleta de
hora em hora gasta cerca de 720 por mês. Com o teto atingido a fonte fica parada até o mês seguinte.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import FxReferenceQuote, ReferenceApiUsage
from .quotes import FeedFormatError, QuoteDraft

OXR_URL = "https://openexchangerates.org/api/latest.json"
OXR_SOURCE = "openexchangerates"
OXR_SYMBOLS: tuple[str, ...] = ("BRL", "PYG", "EUR")  # base USD: o plano gratuito só aceita USD como base
OXR_MONTHLY_LIMIT = 1000  # teto do plano gratuito; o contador nunca passa daqui, qualquer que seja a configuração
OXR_POLL_INTERVAL_S = 3600  # de hora em hora: 24 × 30 = 720 chamadas por mês

FRANKFURTER_SOURCE = "frankfurter"
PTAX_SOURCE = "bcb-ptax-venda"
PTAX_VENDA_DRAFT_INSTRUMENT = "PTAX venda"  # rótulo de `quotes.BCB_SERIES` para a série SGS 1
# cotação diária (BCE, PTAX) cobre fim de semana; cotação mais velha não entra na comparação
REFERENCE_LOOKBACK = timedelta(days=4)


class ReferenceQuote:
    """Cotação de referência com fonte, data observada, data de coleta e `referencia=True`."""

    __slots__ = ("instrument", "source", "price", "observed_at", "collected_at")

    def __init__(
        self,
        instrument: str,
        source: str,
        price: Decimal,
        observed_at: datetime,
        collected_at: datetime,
    ) -> None:
        if price <= 0:
            raise ValueError("preço de referência precisa ser positivo")
        if observed_at.tzinfo is None or collected_at.tzinfo is None:
            raise ValueError("datas de referência precisam de fuso")
        self.instrument = instrument
        self.source = source
        self.price = price
        self.observed_at = observed_at
        self.collected_at = collected_at

    @property
    def referencia(self) -> bool:
        """Sempre verdadeiro e somente leitura: referência nunca é executável."""
        return True

    def __repr__(self) -> str:  # pragma: no cover - depuração
        return f"ReferenceQuote({self.instrument!r}, {self.source!r}, {self.price}, referencia=True)"


@dataclass(frozen=True, slots=True)
class Deviation:
    instrument: str
    source_a: str  # ordem alfabética: a diferença é sempre (a − b) / b
    source_b: str
    price_a: Decimal
    price_b: Decimal
    observed_at_a: datetime
    observed_at_b: datetime
    pct: Decimal
    over: bool  # |pct| estritamente maior que o limite


def deviation_pct(a: Decimal, b: Decimal) -> Decimal:
    """Desvio percentual de `a` em relação a `b`: (a − b) / b × 100."""
    if b <= 0:
        raise ValueError("referência de comparação precisa ser positiva")
    return (a - b) / b * 100


def latest_by_source(quotes: Iterable[ReferenceQuote]) -> dict[str, dict[str, ReferenceQuote]]:
    """instrumento → fonte → cotação mais recente observada."""
    out: dict[str, dict[str, ReferenceQuote]] = {}
    for qt in quotes:
        by_source = out.setdefault(qt.instrument, {})
        cur = by_source.get(qt.source)
        if cur is None or qt.observed_at > cur.observed_at:
            by_source[qt.source] = qt
    return out


def compare(latest: dict[str, dict[str, ReferenceQuote]], threshold_pct: Decimal) -> list[Deviation]:
    """Compara todo par de fontes de um mesmo instrumento. Só marca `over` acima do limite (nunca igual)."""
    out: list[Deviation] = []
    for instrument in sorted(latest):
        by_source = latest[instrument]
        sources = sorted(by_source)
        for i, sa in enumerate(sources):
            for sb in sources[i + 1 :]:
                a, b = by_source[sa], by_source[sb]
                pct = deviation_pct(a.price, b.price)
                out.append(
                    Deviation(
                        instrument=instrument,
                        source_a=sa,
                        source_b=sb,
                        price_a=a.price,
                        price_b=b.price,
                        observed_at_a=a.observed_at,
                        observed_at_b=b.observed_at,
                        pct=pct,
                        over=abs(pct) > threshold_pct,
                    )
                )
    return out


# ------------------------------------------------------------------ parsers (puros, sem rede)
def parse_oxr_latest(data: Any, *, collected_at: datetime) -> list[ReferenceQuote]:
    """Resposta de `/api/latest.json` (base USD). EUR vem como USD→EUR; o par gravado é EUR/USD = 1 ÷ taxa."""
    if not isinstance(data, dict):
        raise FeedFormatError("openexchangerates: esperado um objeto")
    if data.get("base") != "USD":
        raise FeedFormatError("openexchangerates: base diferente de USD")
    rates = data.get("rates")
    if not isinstance(rates, dict):
        raise FeedFormatError("openexchangerates: sem 'rates'")
    try:
        observed = datetime.fromtimestamp(int(data["timestamp"]), tz=UTC)
    except (KeyError, TypeError, ValueError) as exc:
        raise FeedFormatError("openexchangerates: 'timestamp' inválido") from exc
    out: list[ReferenceQuote] = []
    for symbol in OXR_SYMBOLS:
        if symbol not in rates:
            continue
        rate = Decimal(str(rates[symbol]))
        if symbol == "EUR":
            out.append(ReferenceQuote("EUR/USD", OXR_SOURCE, Decimal(1) / rate, observed, collected_at))
        else:
            out.append(ReferenceQuote(f"USD/{symbol}", OXR_SOURCE, rate, observed, collected_at))
    return out


def from_frankfurter_drafts(drafts: Sequence[QuoteDraft], *, collected_at: datetime) -> list[ReferenceQuote]:
    """Converte as cotações `fx_reference` do Frankfurter (já em USD/XXX ou EUR/USD)."""
    return [
        ReferenceQuote(d.instrument, FRANKFURTER_SOURCE, d.price, d.observed_at, collected_at)
        for d in drafts
        if d.kind == "fx_reference" and d.source == FRANKFURTER_SOURCE
    ]


def from_bcb_drafts(drafts: Sequence[QuoteDraft], *, collected_at: datetime) -> list[ReferenceQuote]:
    """Só a PTAX venda (SGS 1) vira referência USD/BRL; a Selic meta não é câmbio."""
    return [
        ReferenceQuote("USD/BRL", PTAX_SOURCE, d.price, d.observed_at, collected_at)
        for d in drafts
        if d.instrument == PTAX_VENDA_DRAFT_INSTRUMENT
    ]


# ------------------------------------------------------------------ orçamento persistido da OXR
def period_of(now: datetime) -> str:
    """Mês de contagem em UTC, por exemplo `2026-11`."""
    return now.astimezone(UTC).strftime("%Y-%m")


def effective_ceiling(source: str, configured: int) -> int:
    """Teto efetivo de chamadas no mês. Para a OXR nunca passa de 1.000, mesmo com configuração maior."""
    cap = max(0, int(configured))
    if source == OXR_SOURCE:
        return min(cap, OXR_MONTHLY_LIMIT)
    return cap


def calls_used(session: Session, source: str, now: datetime) -> int:
    row = session.scalar(
        select(ReferenceApiUsage.calls).where(
            ReferenceApiUsage.source == source, ReferenceApiUsage.period == period_of(now)
        )
    )
    return int(row or 0)


def reserve_call(session: Session, source: str, now: datetime, ceiling: int) -> bool:
    """Reserva uma chamada do mês se ainda couber no teto. Atômico: o UPDATE só incrementa com `calls < teto`.

    Chamada reservada conta mesmo se o HTTP falhar (contagem conservadora). Deve ser commitada antes da requisição.
    """
    cap = effective_ceiling(source, ceiling)
    period = period_of(now)
    row = session.scalar(
        select(ReferenceApiUsage).where(ReferenceApiUsage.source == source, ReferenceApiUsage.period == period)
    )
    if row is None:
        if cap <= 0:
            return False
        row = ReferenceApiUsage(source=source, period=period, calls=0)
        session.add(row)
        session.flush()
    res = session.execute(
        update(ReferenceApiUsage)
        .where(ReferenceApiUsage.id == row.id, ReferenceApiUsage.calls < cap)
        .values(calls=ReferenceApiUsage.calls + 1)
        .execution_options(synchronize_session=False)
    )
    session.flush()
    return res.rowcount == 1


# ------------------------------------------------------------------ persistência e leitura
def upsert_reference_quotes(session: Session, quotes: Sequence[ReferenceQuote], *, data_mode: str) -> int:
    """Grava uma linha por (fonte, instrumento, data observada). Devolve quantas linhas novas entraram."""
    added = 0
    for qt in quotes:
        row = session.scalar(
            select(FxReferenceQuote).where(
                FxReferenceQuote.source == qt.source,
                FxReferenceQuote.instrument == qt.instrument,
                FxReferenceQuote.observed_at == qt.observed_at,
                FxReferenceQuote.data_mode == data_mode,
            )
        )
        if row is None:
            session.add(
                FxReferenceQuote(
                    instrument=qt.instrument,
                    source=qt.source,
                    price=qt.price,
                    observed_at=qt.observed_at,
                    collected_at=qt.collected_at,
                    referencia=True,
                    data_mode=data_mode,
                )
            )
            added += 1
        else:
            row.collected_at = qt.collected_at
    session.flush()
    return added


def recent_references(session: Session, *, now: datetime, data_mode: str) -> list[ReferenceQuote]:
    """Cotações dentro da janela de comparação (`REFERENCE_LOOKBACK`), prontas para `latest_by_source`."""
    rows = session.scalars(
        select(FxReferenceQuote).where(
            FxReferenceQuote.data_mode == data_mode,
            FxReferenceQuote.observed_at >= now - REFERENCE_LOOKBACK,
        )
    ).all()
    return [ReferenceQuote(r.instrument, r.source, r.price, r.observed_at, r.collected_at) for r in rows]


def deviation_event_payload(dev: Deviation, *, threshold_pct: Decimal) -> dict[str, Any]:
    """Payload do alerta: decimais como string; sempre marcado como referência e não executável."""
    return {
        "instrument": dev.instrument,
        "source_a": dev.source_a,
        "price_a": format(dev.price_a, "f"),
        "observed_at_a": dev.observed_at_a.isoformat(),
        "source_b": dev.source_b,
        "price_b": format(dev.price_b, "f"),
        "observed_at_b": dev.observed_at_b.isoformat(),
        "deviation_pct": format(dev.pct.quantize(Decimal("0.0001")), "f"),
        "threshold_pct": format(threshold_pct, "f"),
        "referencia": True,
        "executavel": False,
    }
