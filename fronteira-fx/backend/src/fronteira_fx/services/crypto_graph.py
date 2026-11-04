"""Nós moeda@local de exchanges de cripto no grafo de posições (USDT@binance, BTC@kraken, BRL@foxbit).

Cada par negociado numa exchange vira duas arestas `quote`, uma por sentido, priceadas pelo VWAP do tamanho alvo do
livro (`crypto.vwap`), com a taxa taker da exchange aplicada por perna (`fee_pct`) e um slippage configurável
(`slippage_pct`, `FX_CRYPTO_SLIPPAGE_PCT`). Taxa não confirmada (`None`) ou IOF não conhecido (BRL convertido, Res. BCB
521) deixam a aresta `incomplete`, nunca zero. Livro sem profundidade para o alvo não gera aresta.

Trilhos entre nós (banco para exchange, exchange para exchange) entram como `CryptoRail`: custo, tempo e janela de
retenção. Campo `None` = não confirmado (custo desconhecido ou tempo sem fonte, `incomplete`).

Toda aresta daqui é `executable=True` (livro ao vivo, nenhuma ordem enviada). Referências (câmbio de valoração) são
`executable=False` e nunca entram num ciclo alertável. Este módulo só lê e calcula: não há função de envio de ordem,
saque ou transferência, e um teste garante isso.

Alerta: `find_crypto_alerts` só devolve ciclo executável, incompleto (custo desconhecido) fora, com lucro bruto e
líquido positivos depois das taxas e do slippage. Somente alerta.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from ..config import get_settings
from ..crypto.types import OrderBook, VenueFee
from ..crypto.vwap import vwap_for_target
from ..engine.graph import Cycle, Edge, Graph, find_cycles, node, node_currency

ZERO = Decimal(0)
ONE = Decimal(1)
TRADE_MINUTES = 1  # tempo de uma troca manual no app da exchange (premissa)
RAIL_MINUTES_UNKNOWN = 240  # mesmo placeholder das transferências sem trilho (cycles.TRANSFER_MINUTES_UNKNOWN)


@dataclass(frozen=True, slots=True)
class CryptoMarket:
    """Um par negociado numa exchange, com o livro lido (somente leitura) e a taxa dela.

    `target_base`: tamanho alvo em moeda base. O ganho é calculado pelo VWAP desse tamanho; quantias maiores caem
    fora da janela da aresta (`max_in`) e não entram no ciclo."""

    venue: str
    base: str
    quote: str
    book: OrderBook
    fee: VenueFee
    target_base: Decimal


@dataclass(frozen=True, slots=True)
class CryptoRail:
    """Trilho de transferência de uma moeda entre dois nós. Campo `None` = não confirmado."""

    id: str
    src: str  # nó de origem, ex.: BRL@brbank
    dst: str  # nó de destino, ex.: BRL@foxbit
    minutes: int | None
    fee_pct: Decimal | None
    fee_fixed: Decimal | None  # na moeda do nó de origem
    retention_hours: int | None
    source: str


# Trilhos conhecidos do plano triangulador. Sem tarifa confirmada, o custo fica desconhecido (incomplete). O IOF da
# Res. BCB 521 não entra aqui: é cobrado nas trocas em BRL (ver `_trade_edge`) e a alíquota está em aberto.
DEFAULT_CRYPTO_RAILS: tuple[CryptoRail, ...] = (
    CryptoRail(
        id="brl-brbank-foxbit",
        src="BRL@brbank",
        dst="BRL@foxbit",
        minutes=None,
        fee_pct=None,
        fee_fixed=None,
        retention_hours=None,
        source="tarifa do banco e da Foxbit não confirmadas (plano triangulador, U07)",
    ),
    CryptoRail(
        id="usdt-foxbit-binance",
        src="USDT@foxbit",
        dst="USDT@binance",
        minutes=None,
        fee_pct=None,
        fee_fixed=None,
        retention_hours=None,
        source="taxa de rede não confirmada (plano triangulador, U07)",
    ),
)


def default_slippage() -> Decimal:
    return get_settings().crypto_slippage_pct


def _mid(book: OrderBook) -> Decimal | None:
    bids = [lvl.price for lvl in book.bids if lvl.qty > ZERO and lvl.price > ZERO]
    asks = [lvl.price for lvl in book.asks if lvl.qty > ZERO and lvl.price > ZERO]
    if not bids or not asks:
        return None
    return (max(bids) + min(asks)) / 2


def _trade_edge(market: CryptoMarket, side: str, slippage: Decimal) -> Edge | None:
    book = market.book
    fill = vwap_for_target(book, side, market.target_base, market.fee)  # type: ignore[arg-type]
    if not fill.complete or fill.vwap is None or fill.vwap <= ZERO:
        return None  # livro sem profundidade para o alvo: sem aresta, nunca preço inventado
    mid = _mid(book)
    unknown: set[str] = set()
    if market.fee.taker is None:
        unknown.add("fees")
    if market.base == "BRL" or market.quote == "BRL":
        unknown.add("iof")  # troca BRL x cripto é câmbio (Res. BCB 521); alíquota de IOF não confirmada
    fee_pct = market.fee.taker if market.fee.taker is not None else ZERO
    if side == "buy":  # gasta quote, recebe base; VWAP em quote por base
        src, dst = node(market.quote, market.venue), node(market.base, market.venue)
        rate = ONE / fill.vwap
        max_in = fill.vwap * market.target_base
        mid_rate = ONE / mid if mid else None
    else:  # gasta base, recebe quote; VWAP em quote por base
        src, dst = node(market.base, market.venue), node(market.quote, market.venue)
        rate = fill.vwap
        max_in = market.target_base
        mid_rate = mid
    return Edge(
        src,
        dst,
        "quote",
        rate,
        fee_pct=fee_pct,
        minutes=TRADE_MINUTES,
        via=f"{market.venue} {side} {market.base}/{market.quote} (VWAP {market.target_base})",
        confidence="incomplete" if unknown else "quoted",
        quoted_at=book.fetched_at,
        max_in=max_in,
        mid_rate=mid_rate,
        channel="assistida",  # o dono faz a troca no app; nada é enviado daqui
        unknown=frozenset(unknown),
        executable=True,
        slippage_pct=slippage,
        iof_pct=ZERO,
    )


def market_edges(markets: Iterable[CryptoMarket], *, slippage_pct: Decimal | None = None) -> list[Edge]:
    """Duas arestas por par com profundidade (compra e venda), taxa taker por perna e slippage."""
    slip = default_slippage() if slippage_pct is None else slippage_pct
    out: list[Edge] = []
    for market in markets:
        if market.target_base <= ZERO:
            raise ValueError(f"tamanho alvo inválido em {market.venue} {market.base}/{market.quote}")
        for side in ("buy", "sell"):
            edge = _trade_edge(market, side, slip)
            if edge is not None:
                out.append(edge)
    return out


def rail_edges(rails: Iterable[CryptoRail]) -> list[Edge]:
    """Uma aresta `transfer` por trilho: custo (None = desconhecido), tempo e janela de retenção."""
    out: list[Edge] = []
    for rail in rails:
        if node_currency(rail.src) != node_currency(rail.dst):
            raise ValueError(f"trilho {rail.id} troca de moeda; conversão não é trilho")
        unknown: set[str] = set()
        if rail.fee_pct is None or rail.fee_fixed is None:
            unknown.add("fees")
        out.append(
            Edge(
                rail.src,
                rail.dst,
                "transfer",
                ONE,
                fee_pct=rail.fee_pct if rail.fee_pct is not None else ZERO,
                fee_fixed=rail.fee_fixed if rail.fee_fixed is not None else ZERO,
                minutes=rail.minutes if rail.minutes is not None else RAIL_MINUTES_UNKNOWN,
                via=f"trilho {rail.id}",
                confidence="incomplete" if unknown or rail.minutes is None else "estimated",
                mid_rate=ONE,
                channel="assistida",
                unknown=frozenset(unknown),
                executable=True,
                retention_hours=rail.retention_hours,
            )
        )
    return out


def crypto_edges(
    markets: Iterable[CryptoMarket],
    rails: Iterable[CryptoRail] = DEFAULT_CRYPTO_RAILS,
    *,
    slippage_pct: Decimal | None = None,
    references: Sequence[Edge] = (),
) -> list[Edge]:
    """Arestas de cripto prontas para `build_graph(extra_edges=...)`. `references` (câmbio de valoração) entram
    marcadas como não executáveis: podem aparecer num ciclo, mas esse ciclo nunca é alertável."""
    edges = market_edges(markets, slippage_pct=slippage_pct) + rail_edges(rails)
    for ref in references:
        if ref.executable:
            raise ValueError(f"referência {ref.via} precisa de executable=False")
        edges.append(ref)
    return edges


def is_alertable(cycle: Cycle) -> bool:
    """Regra do alerta: executável (sem referência), lucro bruto e líquido positivos, custo completo."""
    return cycle.executable and cycle.gross_gain > ZERO and cycle.gain > ZERO and cycle.confidence != "incomplete"


def find_crypto_alerts(
    graph: Graph, balances: Mapping[str, Decimal], *, max_len: int = 4, limit: int | None = 50
) -> list[Cycle]:
    """Ciclos alertáveis a partir dos saldos estacionados, do melhor ROI líquido para o pior. Somente alerta."""
    cycles = find_cycles(graph, balances, max_len=max_len, min_roi=None, limit=None)
    alerts = [c for c in cycles if is_alertable(c)]
    return alerts if limit is None else alerts[:limit]
