"""Position graph built from the latest quotes and the user's accounts (contract: `/v1/opportunities/cycles`).

Node = `<currency>@<venue>`; venue = source id (digital), `source:city` (exchange houses), account institution,
or `cash:<city>` (cash in one of the six cities: CDE, ASU, PJC, ENC, FOZ, PPO). Edges:
- quotes (base->quote at `buy`, quote->base at `1/sell`), with the spread measured against the mid;
- transfers between accounts and digital venues, and between accounts and exchange houses, priced by the trilhos in
  `data/rails.json` (no rail, or a rail with a null value => `incomplete`, never zero);
- walk-ins between cash and exchange houses in the same city (presencial);
- ATM moves (rail `->cash`, presencial);
- travel between cities (`data/transport.json`), one edge per currency and direction; a route with no cost is
  `incomplete`; a route that crosses the border sets `border` on the leg.

Amount windows (B16): a quote simulated for `amount_base` is valid from that amount up to (not including) the next
tier of the same family (source, branch, city, pair, modality, channel); `min_amount`/`max_amount` in the quote
context are explicit bounds. The search drops an edge whose window does not accept the amount reaching it.
Reference rates (`kind=market_reference` or `modality=reference`) are never edges (B23).

`enrich_cycle` adds what needs the valuation rates (BRL-based): gain in each currency, costs in the start currency,
and `requires_declaration` when a border leg moves more than US$ 10 000 (informs; never blocks).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..adapters.registry import ADAPTERS, discontinued_ids
from ..decimal_utils import ONE, ZERO
from ..engine.graph import Cycle, Edge, Graph, celular_graph, find_cycles, node, node_currency
from ..engine.routes import Confidence
from ..models import Account, Quote
from .logistics import Rail, load_rails, load_transport
from .opportunities import derive_valuation_rates, valuation_quotes
from .quotes import is_reference, latest_quotes

CURRENCIES = ("BRL", "PYG", "USD")
CITIES = ("CDE", "ASU", "PJC", "ENC", "FOZ", "PPO")
DECLARATION_LIMIT_USD = Decimal(10_000)
TRANSFER_MINUTES_UNKNOWN = 240
ATM_MINUTES_UNKNOWN = 60
MINUTES_BY_MODALITY = {"cash": 15, "transfer": 240, "account": 5, "card_debit": 0, "card_credit": 0, "card_virtual": 0}
# smallest money unit: a tier covers [amount_base, next_tier - TIER_STEP] because Edge windows are inclusive
TIER_STEP = Decimal("0.01")
PROBE_AMOUNT = Decimal(1000)
# lugar digital -> endpoint de trilho (`data/rails.json`). Venue fora da tabela não tem trilho conhecido.
ENDPOINT_BY_VENUE = {
    "revolut": "revolut",
    "nomad": "nomad",
    "nubank": "br_bank",
    "brbank": "br_bank",
    "itau": "br_bank",
    "bradesco": "br_bank",
    "caixa": "br_bank",
    "banco_py": "py_bank",
}
DEMO_PREFIX = "demo-"  # fontes do modo demo têm o prefixo; a identidade do lugar é a mesma
# Lado paraguaio: cidades do Paraguai e banco paraguaio. Conversão de BRL fora dele pode ter IOF brasileiro.
PY_CITIES = frozenset({"CDE", "ASU", "PJC", "ENC"})
PY_ENDPOINTS = frozenset({"py_bank"})
# IOF de câmbio incide sobre BRL convertido fora do Paraguai (instituição brasileira, fintech, fonte sem cidade).
# A alíquota não está nos trilhos quando `iof_pct` é null: sem alíquota conhecida a aresta fica `incomplete` com
# IOF desconhecido. O que é paraguaio fica de fora (sem IOF), e nunca vira "zero" por falta de informação.

Window = tuple[Decimal | None, Decimal | None]
Family = tuple[str, str | None, str | None, str, str, str, str]


def account_venue(a: Account) -> str:
    if a.kind == "cash" or (a.location in ("CDE", "ASU", "PJC") and a.institution in ("carteira", "cash")):
        return f"cash:{a.location}"
    return a.institution


def quote_venue(q: Quote) -> str:
    return f"{q.source_id}:{q.city}" if q.channel == "physical" and q.city else q.source_id


def strip_demo(venue: str) -> str:
    return venue.removeprefix(DEMO_PREFIX)


def endpoint_of_venue(venue: str) -> str | None:
    """Endpoint de trilho de um nó de lugar: caixa, casa de câmbio (`fonte:cidade`) ou banco/fintech conhecido."""
    venue = strip_demo(venue)
    if venue.startswith("cash:"):
        return "cash"
    if ":" in venue:
        return "exchange_house"
    return ENDPOINT_BY_VENUE.get(venue)


def valuation_rates(quotes: Iterable[Quote]) -> dict[str, Decimal]:
    """Moeda -> unidades de BRL por 1 unidade (BRL = 1). Base de toda conversão de custo e de ganho."""
    rates = derive_valuation_rates(quotes, "BRL")
    rates["BRL"] = ONE
    return rates


def valuation_dates(quotes: Iterable[Quote]) -> dict[str, datetime]:
    """Currency -> data da cotação que define a taxa de valoração dela (a mesma escolha das taxas)."""
    return {ccy: q.captured_at for ccy, q in valuation_quotes(quotes, "BRL").items() if q.captured_at is not None}


def conversion_date(src: str, dst: str, dates: dict[str, datetime]) -> datetime | None:
    """Data que vale para uma conversão: a mais velha entre as taxas das duas moedas (BRL é a referência, sem data)."""
    ccys = {c for c in (src, dst) if c != "BRL"}
    if not ccys or any(c not in dates for c in ccys):
        return None
    return min(dates[c] for c in ccys)


def convert(amount: Decimal | None, src: str, dst: str, rates: dict[str, Decimal]) -> Decimal | None:
    """`amount` de `src` em `dst` pelas taxas de valoração; None quando alguma moeda não tem taxa."""
    if amount is None:
        return None
    if src == dst:
        return amount
    if src in rates and dst in rates:
        return amount * rates[src] / rates[dst]
    return None


def _fee_terms(q: Quote, src_ccy: str, dst_ccy: str, rate: Decimal) -> tuple[Decimal, Decimal, frozenset[str]]:
    """Return (fee_pct on the input, fee_fixed in dst currency, custos desconhecidos).

    `fees` é desconhecido só quando uma tarifa não tem valor nem percentual, ou quando há tarifa não nula em uma
    terceira moeda que não cabe na aresta. Tarifa zero e percentual são custos conhecidos.
    """
    pct = ZERO
    fixed = ZERO
    unknown = False
    for f in q.fees or []:
        if f.get("pct") is not None:
            pct += Decimal(str(f["pct"]))
        amount = f.get("amount")
        if amount is None:
            if f.get("pct") is None:
                unknown = True
            continue
        amt = Decimal(str(amount))
        if amt == 0:
            continue
        if f.get("currency") == src_ccy:
            fixed += amt * rate
        elif f.get("currency") == dst_ccy:
            fixed += amt
        else:
            unknown = True
    return pct, fixed, frozenset({"fees"}) if unknown else frozenset()


def is_paraguayan_venue(venue: str) -> bool:
    """Lugar do lado paraguaio: caixa ou casa de câmbio numa cidade do Paraguai, banco paraguaio, ou fonte cujas
    cidades estão todas no Paraguai. Qualquer outro lugar (fintech, banco brasileiro, fonte sem cidade) não é."""
    venue = strip_demo(venue)
    if venue.startswith("cash:") or ":" in venue:
        return venue.rsplit(":", 1)[1] in PY_CITIES
    if endpoint_of_venue(venue) in PY_ENDPOINTS:
        return True
    adapter = ADAPTERS.get(venue)
    return adapter is not None and bool(adapter.info.cities) and set(adapter.info.cities) <= PY_CITIES


def iof_applies(venue: str, src_ccy: str, dst_ccy: str) -> bool:
    """True quando converter `src_ccy` em `dst_ccy` nesse lugar pode sofrer IOF (BRL convertido fora do Paraguai).
    Quem responde True e não tem alíquota conhecida fica com IOF desconhecido: a aresta é `incomplete`."""
    if src_ccy != "BRL" or dst_ccy == "BRL" or venue.startswith("cash:"):
        return False  # dinheiro na mão não é conversão de instituição
    return not is_paraguayan_venue(venue)


def live_quotes(quotes: Iterable[Quote], excluded: frozenset[str]) -> list[Quote]:
    """Cotações que ainda valem: sem fonte descontinuada e sem destino em instituição descontinuada. Vale para o
    grafo e para a valoração (taxas BRL), que não podem usar o que o grafo descartou."""
    kept: list[Quote] = []
    for q in quotes:
        if q.source_id in excluded:
            continue
        ctx = q.context or {}
        dst = ctx.get("bank") if ctx.get("receive") == "bank_account" and ctx.get("bank") else None
        if dst in excluded:
            continue
        kept.append(q)
    return kept


def _family(q: Quote) -> Family:
    return (q.source_id, q.branch_id, q.city, q.base, q.quote, q.modality, q.channel)


def _tier_ladders(quotes: Iterable[Quote]) -> dict[Family, list[Decimal]]:
    """Sorted distinct `amount_base` per quote family (the amounts a provider was simulated for)."""
    ladders: dict[Family, set[Decimal]] = {}
    for q in quotes:
        if q.amount_base is not None and not is_reference(q):
            ladders.setdefault(_family(q), set()).add(q.amount_base)
    return {k: sorted(v) for k, v in ladders.items()}


def _ctx_amount(ctx: dict[str, Any], key: str) -> Decimal | None:
    value = ctx.get(key)
    return Decimal(str(value)) if value not in (None, "") else None


def _window(q: Quote, ladders: dict[Family, list[Decimal]]) -> Window:
    """Amount window, in `q.base`, the quote is valid for. Explicit context bounds win; an amount-specific quote
    covers [amount_base, next tier); a generic quote (no amount) is unbounded."""
    ctx = q.context or {}
    lo, hi = _ctx_amount(ctx, "min_amount"), _ctx_amount(ctx, "max_amount")
    if q.amount_base is not None:
        if lo is None:
            lo = q.amount_base
        if hi is None:
            above = [a for a in ladders.get(_family(q), []) if a > q.amount_base]
            hi = above[0] - TIER_STEP if above else None
    return lo, hi


def _scale(window: Window, factor: Decimal) -> Window:
    lo, hi = window
    return (lo * factor if lo is not None else None, hi * factor if hi is not None else None)


def _add_edge(edges: list[Edge], e: Edge) -> None:
    """Toda aresta entra no grafo: alternativas do mesmo par (cartão x espécie, trilho x deslocamento) competem na
    busca, pelo montante que chega a elas, e não aqui, num montante fixo."""
    edges.append(e)


def _economic_key(e: Edge) -> tuple:
    """Identidade econômica da aresta, sem o rótulo (`via`): duas arestas com a mesma chave são a mesma alternativa."""
    return (
        e.src, e.dst, e.kind, e.rate, e.fee_pct, e.fee_fixed, e.iof_pct, e.transport_fixed, e.minutes, e.channel,
        e.confidence, tuple(sorted(e.unknown)), e.border, e.counter, e.min_in, e.max_in, e.mid_rate, e.quoted_at,
        e.evidence_id, e.executable, e.retention_hours, e.slippage_pct,
    )


def _edge_order(e: Edge) -> tuple:
    return (e.src, e.dst, e.kind, e.via, str(e.rate), str(e.min_in), str(e.max_in), str(e.fee_pct), str(e.fee_fixed))


def _rail(rails: dict[str, Rail], src: str | None, dst: str | None, ccy: str, *, converts: bool) -> Rail | None:
    """Trilho de `src` para `dst` que sai em `ccy` (mesma moeda ou conversão). None quando não há."""
    if src is None or dst is None:
        return None
    for r in rails.values():
        if r.from_ == src and r.to == dst and r.currency == ccy and r.converts == converts and r.available:
            return r
    return None


def _rail_terms(
    rail: Rail | None, dst_ccy: str, iof_on: bool, rates: dict[str, Decimal]
) -> tuple[Decimal, Decimal, Decimal, frozenset[str]]:
    """(fee_pct, fee_fixed em dst, iof_pct, custos desconhecidos). Valor null ou trilho ausente é desconhecido,
    nunca zero; os placeholders ZERO guardados nessas categorias não entram como custo conhecido."""
    unknown: set[str] = set()
    pct = ZERO
    fixed = ZERO
    iof = ZERO
    if rail is None:
        unknown.add("fees")
    else:
        if rail.fee_pct is None:
            unknown.add("fees")
        else:
            pct = rail.fee_pct
        if rail.fee_fixed is None:
            unknown.add("fees")
        else:
            converted = convert(rail.fee_fixed.amount, rail.fee_fixed.currency, dst_ccy, rates)
            if converted is None:
                unknown.add("fees")
            else:
                fixed = converted
    # IOF informado no trilho vale sempre (com ou sem conversão); `iof_on` só decide se a falta dele é desconhecida
    if rail is not None and rail.iof_pct is not None:
        iof = rail.iof_pct
    elif iof_on:
        unknown.add("iof")
    return pct, fixed, iof, frozenset(unknown)


def _transfer_edge(
    src: str,
    dst: str,
    src_ccy: str,
    dst_ccy: str,
    *,
    rail: Rail | None,
    iof_on: bool,
    rates: dict[str, Decimal],
    kind: str,
    channel: str,
    via: str,
    unknown_minutes: int,
    quoted_at: datetime | None = None,
) -> Edge | None:
    """Aresta de transferência priceada pelo trilho. Conversão: taxa de valoração, mas o spread do trilho é
    desconhecido, então a aresta é `incomplete`. Sem taxa para converter, não há aresta."""
    captured = rail.rate if rail is not None and src_ccy != dst_ccy else None
    if src_ccy == dst_ccy:
        rate: Decimal | None = ONE
    elif captured is not None and captured > 0:
        rate = captured  # taxa capturada do próprio trilho: o spread já está nela
    else:
        rate = convert(ONE, src_ccy, dst_ccy, rates)
        if rate is None or rate <= 0:
            return None
    pct, fixed, iof, unknown = _rail_terms(rail, dst_ccy, iof_on, rates)
    if src_ccy != dst_ccy and captured is None:
        unknown = unknown | {"spread"}  # sem taxa capturada no trilho: spread desconhecido frente à referência
    return Edge(
        src,
        dst,
        kind,  # type: ignore[arg-type]
        rate,
        fee_pct=pct,
        fee_fixed=fixed,
        minutes=rail.minutes if rail is not None else unknown_minutes,
        via=via,
        confidence="incomplete" if unknown else "estimated",
        min_in=rail.min_amount if rail is not None else None,
        max_in=rail.max_amount if rail is not None else None,
        iof_pct=iof,
        mid_rate=ONE if src_ccy == dst_ccy else None,
        channel=channel,  # type: ignore[arg-type]
        unknown=unknown,
        quoted_at=quoted_at,
    )


def build_graph(
    quotes: Sequence[Quote],
    accounts: Sequence[Account],
    *,
    excluded: frozenset[str] | None = None,
    extra_edges: Sequence[Edge] = (),
) -> tuple[Graph, dict[str, Decimal]]:
    """Grafo de posições. `excluded`: fontes/instituições fora do grafo (por padrão, as descontinuadas, como o ueno,
    que está em resolução desde 03/11/2026): cotação dela, cotação com destino nela e conta nela não entram.
    `extra_edges`: arestas já prontas de outras fontes (ex.: exchanges de cripto, `services/crypto_graph.py`); sem
    elas o grafo sai igual ao de antes."""
    excluded = discontinued_ids() if excluded is None else excluded
    accounts = [a for a in accounts if account_venue(a) not in excluded]
    quotes = live_quotes(quotes, excluded)
    edges: list[Edge] = list(extra_edges)
    balances: dict[str, Decimal] = {}
    account_nodes: dict[str, str] = {}  # node -> venue
    for a in accounts:
        n = node(a.currency, account_venue(a))
        balances[n] = balances.get(n, ZERO) + (a.balance_free or ZERO)
        account_nodes[n] = account_venue(a)

    rates = valuation_rates(quotes)
    dates = valuation_dates(quotes)
    rails = {r.id: r for r in load_rails().values()}
    digital_venues: dict[str, set[str]] = {}  # venue -> currencies present
    physical_venues: dict[str, tuple[str, set[str]]] = {}  # venue -> (city, currencies)
    ladders = _tier_ladders(quotes)
    # contas digitais são lugares digitais mesmo sem cotação própria: entram para receber transferências
    for a in accounts:
        venue = account_venue(a)
        if not venue.startswith("cash:"):
            digital_venues.setdefault(venue, set()).add(a.currency)
    for q in quotes:
        if is_reference(q):
            continue
        venue = quote_venue(q)
        minutes = MINUTES_BY_MODALITY.get(q.modality, 30)
        channel = "presencial" if q.channel == "physical" else "assistida"
        ctx = q.context or {}
        dst_venue = ctx.get("bank") if ctx.get("receive") == "bank_account" and ctx.get("bank") else venue
        if dst_venue in excluded:
            continue
        if q.channel == "physical" and q.city:
            physical_venues.setdefault(venue, (q.city, set()))[1].update({q.base, q.quote})
        else:
            digital_venues.setdefault(venue, set()).update({q.base, q.quote} if dst_venue == venue else {q.base})
            if dst_venue != venue:
                digital_venues.setdefault(dst_venue, set()).add(q.quote)
        via = f"{q.source_id} {q.modality}" + (f" @{q.city}" if q.city else "")
        window = _window(q, ladders)  # in q.base, the input of the buy leg
        mid = (q.buy + q.sell) / 2 if q.buy and q.sell and q.buy > 0 and q.sell > 0 else None
        base_conf: Confidence = "quoted" if q.kind == "executable" else "estimated"
        if q.buy is not None and q.buy > 0:
            pct, fixed, unknown = _fee_terms(q, q.base, q.quote, q.buy)
            # sem taxa de referência (só compra ou só venda) o spread fica null, mas a taxa cotada é o preço total
            unknown = set(unknown) | ({"iof"} if iof_applies(venue, q.base, q.quote) else set())
            lo, hi = window
            _add_edge(
                edges,
                Edge(
                    node(q.base, venue),
                    node(q.quote, dst_venue),
                    "quote",
                    q.buy,
                    fee_pct=pct,
                    fee_fixed=fixed,
                    minutes=minutes,
                    via=f"{via} (compra {q.buy})",
                    confidence="incomplete" if unknown else base_conf,
                    unknown=frozenset(unknown),
                    evidence_id=q.evidence_id,
                    quoted_at=q.captured_at,
                    executable=q.kind == "executable",  # cotação indicativa (estimated) não é preço firme
                    min_in=lo,
                    max_in=hi,
                    mid_rate=mid,
                    channel=channel,  # type: ignore[arg-type]
                ),
            )
        if q.sell is not None and q.sell > 0 and dst_venue == venue:
            rate = ONE / q.sell
            pct, fixed, unknown = _fee_terms(q, q.quote, q.base, rate)
            unknown = set(unknown) | ({"iof"} if iof_applies(venue, q.quote, q.base) else set())
            lo, hi = _scale(window, q.sell)  # the sell leg is fed in q.quote: amount_base * sell
            _add_edge(
                edges,
                Edge(
                    node(q.quote, venue),
                    node(q.base, venue),
                    "quote",
                    rate,
                    fee_pct=pct,
                    fee_fixed=fixed,
                    minutes=minutes,
                    via=f"{via} (venda {q.sell})",
                    confidence="incomplete" if unknown else base_conf,
                    unknown=frozenset(unknown),
                    evidence_id=q.evidence_id,
                    quoted_at=q.captured_at,
                    executable=q.kind == "executable",  # cotação indicativa (estimated) não é preço firme
                    min_in=lo,
                    max_in=hi,
                    mid_rate=ONE / mid if mid else None,
                    channel=channel,  # type: ignore[arg-type]
                ),
            )

    # contas digitais <-> lugares digitais: transferência priceada pelo trilho (sem trilho = incomplete)
    for n, venue in account_nodes.items():
        if venue.startswith("cash:"):
            continue
        ccy = node_currency(n)
        ep_src = endpoint_of_venue(venue)
        for dv, currencies in digital_venues.items():
            if dv == venue:
                continue
            ep_dst = endpoint_of_venue(dv)
            if ccy in currencies:
                rail_out = _rail(rails, ep_src, ep_dst, ccy, converts=False)
                rail_in = _rail(rails, ep_dst, ep_src, ccy, converts=False)
                legs_digital = (
                    (n, node(ccy, dv), rail_out, ep_src, f"transferência {venue}→{dv}"),
                    (node(ccy, dv), n, rail_in, ep_dst, f"resgate {dv}→{venue}"),
                )
                for src, dst, rail_src, _ep, label in legs_digital:
                    edge = _transfer_edge(
                        src,
                        dst,
                        ccy,
                        ccy,
                        rail=rail_src,
                        iof_on=False,  # mesma moeda: não é conversão
                        rates=rates,
                        kind="transfer",
                        channel="assistida",
                        via=label,
                        unknown_minutes=TRANSFER_MINUTES_UNKNOWN,
                    )
                    if edge is not None:
                        _add_edge(edges, edge)
            # conversão por trilho (ex.: BRL de banco brasileiro para USD na Nomad): spread desconhecido
            for rail in rails.values():
                if not rail.converts or rail.currency != ccy or rail.from_ != ep_src or rail.to != ep_dst:
                    continue
                out = rail.out_currency
                if out not in currencies:
                    continue
                edge = _transfer_edge(
                    n,
                    node(out, dv),
                    ccy,
                    out,
                    rail=rail,
                    iof_on=iof_applies(venue, ccy, out),
                    rates=rates,
                    kind="transfer",
                    channel="assistida",
                    via=f"conversão {venue}→{dv} ({rail.id})",
                    unknown_minutes=TRANSFER_MINUTES_UNKNOWN,
                    quoted_at=conversion_date(ccy, out, dates),
                )
                if edge is not None:
                    _add_edge(edges, edge)

    # contas <-> casas de câmbio na mesma moeda: só quando há trilho (SIPAP/depósito); sem trilho não há aresta
    for n, venue in account_nodes.items():
        if venue.startswith("cash:"):
            continue
        ccy = node_currency(n)
        ep_src = endpoint_of_venue(venue)
        for pv, (_city, currencies) in physical_venues.items():
            if ccy not in currencies:
                continue
            rail_out = _rail(rails, ep_src, "exchange_house", ccy, converts=False)
            rail_in = _rail(rails, "exchange_house", ep_src, ccy, converts=False)
            if rail_out is None and rail_in is None:
                continue
            for src, dst, rail_leg, label in (
                (n, node(ccy, pv), rail_out, f"transferência {venue}→{pv}"),
                (node(ccy, pv), n, rail_in, f"transferência {pv}→{venue}"),
            ):
                edge = _transfer_edge(
                    src,
                    dst,
                    ccy,
                    ccy,
                    rail=rail_leg,
                    iof_on=False,  # mesma moeda: não é conversão
                    rates=rates,
                    kind="transfer",
                    channel="assistida",
                    via=label,
                    unknown_minutes=TRANSFER_MINUTES_UNKNOWN,
                )
                if edge is not None:
                    _add_edge(edges, edge)

    # casas de câmbio <-> caixa na mesma cidade (balcão, presencial)
    cities = set()
    for venue, (city, currencies) in physical_venues.items():
        cities.add(city)
        for ccy in currencies:
            cash = node(ccy, f"cash:{city}")
            _add_edge(
                edges,
                Edge(cash, node(ccy, venue), "deposit", ONE, ZERO, ZERO, 20, f"balcão {venue}", "estimated",
                     mid_rate=ONE, counter=True),
            )
            _add_edge(
                edges,
                Edge(node(ccy, venue), cash, "withdraw", ONE, ZERO, ZERO, 0, f"balcão {venue}", "estimated",
                     mid_rate=ONE, counter=True),
            )

    # contas digitais <-> caixa (saque/depósito em ATM): trilho `->cash`; sem trilho, incomplete
    for n, venue in account_nodes.items():
        if venue.startswith("cash:"):
            continue
        ccy = node_currency(n)
        ep_src = endpoint_of_venue(venue)
        for city in CITIES:
            cash = node(ccy, f"cash:{city}")
            withdraw = _transfer_edge(
                n,
                cash,
                ccy,
                ccy,
                rail=_rail(rails, ep_src, "cash", ccy, converts=False),
                iof_on=False,  # mesma moeda
                rates=rates,
                kind="withdraw",
                channel="presencial",
                via=f"saque ATM {venue} em {city}",
                unknown_minutes=ATM_MINUTES_UNKNOWN,
            )
            if withdraw is not None:  # mesma moeda: sempre existe (sem trilho, incomplete)
                _add_edge(edges, withdraw)
            _add_edge(
                edges,
                Edge(
                    cash,
                    n,
                    "deposit",
                    ONE,
                    minutes=ATM_MINUTES_UNKNOWN,
                    via=f"depósito em {venue} em {city} (não validado)",
                    confidence="incomplete",
                    channel="presencial",
                    mid_rate=ONE,
                    unknown=frozenset({"fees"}),  # depósito em ATM não validado: tarifa desconhecida
                ),
            )

    # deslocamento entre cidades (presencial): uma aresta por moeda e sentido; custo null = incomplete
    for route in load_transport().values():
        pairs = [(route.from_city, route.to_city)]
        if route.symmetric:
            pairs.append((route.to_city, route.from_city))
        for a, b in pairs:
            for ccy in CURRENCIES:
                transport = ZERO
                unknown: frozenset[str] = frozenset()
                if route.cost is None:
                    unknown = frozenset({"transport"})
                else:
                    converted = convert(route.cost.amount, route.cost.currency, ccy, rates)
                    if converted is None:
                        unknown = frozenset({"transport"})
                    else:
                        transport = converted
                _add_edge(
                    edges,
                    Edge(
                        node(ccy, f"cash:{a}"),
                        node(ccy, f"cash:{b}"),
                        "travel",
                        ONE,
                        minutes=route.minutes,
                        via=f"deslocamento {a}→{b} ({route.mode})",
                        confidence="incomplete" if unknown else "estimated",
                        transport_fixed=transport,
                        mid_rate=ONE,
                        channel="presencial",
                        border=route.border,
                        unknown=unknown,
                    ),
                )

    g = Graph()
    seen: set[tuple] = set()
    for e in sorted(edges, key=_edge_order):
        # duplicata exata (mesmos nós e mesmos números, só o rótulo muda, p.ex. transferência x resgate do mesmo trilho)
        key = _economic_key(e)
        if key in seen:
            continue
        seen.add(key)
        g.add(e)
    return g, balances


def enrich_cycle(cycle: Cycle, rates: dict[str, Decimal]) -> Cycle:
    """Ganho em cada moeda, custos na moeda de partida e aviso de declaração (taxas de valoração BRL)."""
    start_ccy = node_currency(cycle.start)
    gain_by_currency = {c: convert(cycle.gain, start_ccy, c, rates) for c in CURRENCIES}

    costs: dict[str, Decimal | None] = {}
    for key in ("spread", "fees", "iof", "transport"):
        total: Decimal | None = ZERO
        for leg in cycle.legs:
            value = getattr(leg.costs, key)
            converted = convert(value, node_currency(leg.src), start_ccy, rates)
            if value is None or converted is None or total is None:
                total = None
            else:
                total += converted
        costs[key] = total

    requires = False
    if any(leg.border for leg in cycle.legs):
        in_usd = convert(cycle.amount_in, start_ccy, "USD", rates)
        requires = in_usd is None or in_usd > DECLARATION_LIMIT_USD
    return replace(cycle, gain_by_currency=gain_by_currency, costs=costs, requires_declaration=requires)


def notional_balances(graph: Graph, rates: dict[str, Decimal], notional_brl: Decimal) -> dict[str, Decimal]:
    """Saldo simulado quando não há conta cadastrada: cada nó do grafo parte do equivalente a `notional_brl` na
    moeda dele (pela taxa de valoração BRL). Moeda sem taxa fica de fora (nunca chuta câmbio)."""
    out: dict[str, Decimal] = {}
    for n in sorted(graph.nodes):
        rate = rates.get(node_currency(n))
        if rate is not None and rate > 0:
            out[n] = (notional_brl / rate).quantize(Decimal("0.01"))
    return out


def _rotation_key(cycle: Cycle) -> tuple[tuple[str, str, str], ...]:
    """O mesmo ciclo visto de outro ponto de partida (A→B→C→A e B→C→A→B) tem a mesma chave."""
    legs = [(e.src, e.dst, e.via) for e in cycle.edges]
    i = legs.index(min(legs))
    return tuple(legs[i:] + legs[:i])


def find_cycles_for(
    session: Session,
    *,
    data_mode: str,
    max_len: int = 4,
    min_roi: Decimal | None = None,
    start: str | None = None,
    limit: int | None = 200,
    lookback_s: int = 7 * 86400,
    mode: str = "todos",
    notional_brl: Decimal | None = None,
) -> list[dict[str, Any]]:
    """Cycles as contract dicts (D1), each tagged with the `data_mode` they were computed from.
    `limit` None: sem corte. `mode` \"celular\": só ciclos com todas as pernas assistidas ou automatizáveis.
    `notional_brl`: só quando NÃO há saldo cadastrado, cada nó parte do equivalente a esse valor em reais (simulação;
    a mesma volta vista de outro nó conta uma vez só, a de maior ROI). Com saldo cadastrado o valor é ignorado."""
    # uma vez só: o grafo e a valoração (taxas BRL) usam as mesmas cotações vivas
    quotes = live_quotes(latest_quotes(session, data_mode=data_mode, lookback_s=lookback_s), discontinued_ids())
    accounts = list(session.scalars(select(Account).where(Account.data_mode == data_mode)))
    graph, balances = build_graph(quotes, accounts)
    if mode == "celular":
        graph = celular_graph(graph)
    rates = valuation_rates(quotes)
    simulated = False
    if notional_brl is not None and notional_brl > 0 and not any(v > 0 for v in balances.values()):
        simulated = True
        balances = notional_balances(graph, rates, notional_brl)
    if start:
        balances = {k: v for k, v in balances.items() if k == start}
    cycles = find_cycles(graph, balances, max_len=max_len, min_roi=min_roi, limit=None if simulated else limit)
    if simulated:
        seen: set[tuple[tuple[str, str, str], ...]] = set()
        unique: list[Cycle] = []
        for c in cycles:  # já vem do melhor ROI para o pior: fica a primeira vista de cada volta
            key = _rotation_key(c)
            if key not in seen:
                seen.add(key)
                unique.append(c)
        cycles = unique if limit is None else unique[:limit]
    return [{**enrich_cycle(c, rates).to_dict(), "data_mode": data_mode} for c in cycles]
