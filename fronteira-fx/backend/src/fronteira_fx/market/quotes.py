"""Referências de mercado gratuitas e sem chave (módulo `market`): Binance (cripto), Frankfurter (câmbio de
referência) e SGS do Banco Central (PTAX e Selic).

Tudo aqui é REFERÊNCIA de mercado. Nunca é preço executável e nunca vira aresta de ciclo de arbitragem
(o grafo de posições e o motor de ciclos não importam este módulo).

Parsers puros: recebem o JSON já decodificado (números como `Decimal`, via `parse_float`), sem rede.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .vol import Candle

BINANCE_BASE = (
    "https://data-api.binance.vision"  # dados públicos de mercado (o host de negociação bloqueia algumas regiões)
)
FRANKFURTER_URL = "https://api.frankfurter.dev/v2/rates"
# SGS exige dataInicial e dataFinal (dd/mm/aaaa) desde 26/03/2025; janela curta, sempre dentro de 10 anos.
BCB_SGS_URL = (
    "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados?formato=json&dataInicial={start}&dataFinal={end}"
)
BCB_WINDOW_DAYS = 90  # cobre feriados e séries pouco frequentes (Selic meta); só as duas últimas linhas são usadas


def bcb_window(now: datetime) -> tuple[str, str]:
    """(dataInicial, dataFinal) no formato do SGS, em horário de Brasília."""
    end = now.astimezone(BRT).date()
    start = end - timedelta(days=BCB_WINDOW_DAYS)
    return start.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y")
BRT = timezone(timedelta(hours=-3))

# (símbolo Binance, rótulo, instrumento interno)
BINANCE_SYMBOLS: tuple[tuple[str, str, str], ...] = (
    ("BTCUSDT", "Bitcoin em USDT", "BTC/USDT"),
    ("ETHUSDT", "Ethereum em USDT", "ETH/USDT"),
    ("USDTBRL", "Dólar cripto (USDT em reais)", "USDT/BRL"),
)
FRANKFURTER_QUOTES: tuple[tuple[str, str], ...] = (
    ("BRL", "USD/BRL (BCE via Frankfurter)"),
    ("PYG", "USD/PYG (guarani, via Frankfurter)"),
    ("ARS", "USD/ARS (peso argentino, via Frankfurter)"),
    ("EUR", "EUR/USD (derivado do par USD/EUR)"),
)
# código SGS: (instrumento, rótulo). 1 e 10813: dólar venda e compra (PTAX); 432: meta da Selic.
BCB_SERIES: tuple[tuple[int, str, str], ...] = (
    (1, "PTAX venda", "USD/BRL PTAX venda (SGS 1)"),
    (10813, "PTAX compra", "USD/BRL PTAX compra (SGS 10813)"),
    (432, "Selic meta", "Taxa Selic meta, % a.a. (SGS 432)"),
)


class FeedFormatError(ValueError):
    """Resposta de provedor fora do formato esperado."""


@dataclass(frozen=True, slots=True)
class QuoteDraft:
    instrument: str
    label: str
    kind: str  # crypto | fx_reference | bcb_series
    source: str  # binance | frankfurter | bcb
    price: Decimal
    change_pct: Decimal | None
    observed_at: datetime


def loads_exact(text: str) -> Any:
    """JSON com números como `Decimal` (sem passar por float)."""
    return json.loads(text, parse_float=Decimal)


def _ms(value: int | str) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=UTC)


def parse_ticker_24h(data: Any, labels: dict[str, tuple[str, str]] | None = None) -> list[QuoteDraft]:
    """Resposta de `/api/v3/ticker/24hr?symbols=[...]` (lista de objetos)."""
    if not isinstance(data, list):
        raise FeedFormatError("ticker/24hr: esperada uma lista")
    names = {sym: (label, inst) for sym, label, inst in BINANCE_SYMBOLS} if labels is None else labels
    out: list[QuoteDraft] = []
    for row in data:
        symbol = row.get("symbol")
        if symbol not in names:
            continue
        label, instrument = names[symbol]
        out.append(
            QuoteDraft(
                instrument=instrument,
                label=label,
                kind="crypto",
                source="binance",
                price=Decimal(str(row["lastPrice"])),
                change_pct=Decimal(str(row["priceChangePercent"])),
                observed_at=_ms(row["closeTime"]),
            )
        )
    return out


def parse_klines(data: Any, interval: str, *, now: datetime) -> list[Candle]:
    """Velas da Binance. A última vela pode estar aberta: só as já fechadas (close_time < now) entram."""
    if not isinstance(data, list):
        raise FeedFormatError("klines: esperada uma lista")
    out: list[Candle] = []
    for row in data:
        if not isinstance(row, list) or len(row) < 7:
            raise FeedFormatError("klines: vela malformada")
        open_time = _ms(row[0])
        close_time = _ms(row[6])
        if close_time > now:
            continue
        out.append(
            Candle(
                open_time=open_time,
                close_time=close_time,
                open=Decimal(str(row[1])),
                high=Decimal(str(row[2])),
                low=Decimal(str(row[3])),
                close=Decimal(str(row[4])),
            )
        )
    return out


def parse_frankfurter(data: Any) -> list[QuoteDraft]:
    """Resposta de `/v2/rates?base=USD&quotes=...`: lista de {date, base, quote, rate} (rate é Decimal)."""
    if not isinstance(data, list):
        raise FeedFormatError("frankfurter: esperada uma lista")
    labels = dict(FRANKFURTER_QUOTES)
    out: list[QuoteDraft] = []
    for row in data:
        quote = row.get("quote")
        if quote not in labels or row.get("base") != "USD":
            continue
        rate = Decimal(str(row["rate"]))
        observed = datetime.fromisoformat(row["date"]).replace(tzinfo=UTC)
        if quote == "EUR":
            if rate <= 0:
                continue
            out.append(
                QuoteDraft("EUR/USD", labels[quote], "fx_reference", "frankfurter", Decimal(1) / rate, None, observed)
            )
            continue
        instrument = f"USD/{quote}"
        out.append(QuoteDraft(instrument, labels[quote], "fx_reference", "frankfurter", rate, None, observed))
    return out


def parse_bcb_series(data: Any, instrument: str, label: str) -> QuoteDraft:
    """Série do SGS (`ultimos/N`): a última linha é a referência; a variação vem da penúltima."""
    if not isinstance(data, list) or not data:
        raise FeedFormatError(f"SGS {instrument}: sem valores")
    last = data[-1]
    price = Decimal(str(last["valor"]))
    change: Decimal | None = None
    if len(data) >= 2:
        prev = Decimal(str(data[-2]["valor"]))
        if prev != 0:
            change = (price - prev) / prev * 100
    observed = datetime.strptime(last["data"], "%d/%m/%Y").replace(tzinfo=BRT).astimezone(UTC)
    return QuoteDraft(instrument, label, "bcb_series", "bcb", price, change, observed)
