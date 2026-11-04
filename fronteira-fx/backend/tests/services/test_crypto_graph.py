"""U07: nós moeda@local de cripto no grafo, arestas executáveis ou referência, ciclos com lucro líquido após taxas e
slippage. Sem rede: livros e taxas são fixtures pequenas e sanitizadas."""

from __future__ import annotations

import inspect
import re
from datetime import UTC, datetime
from decimal import Decimal

from fronteira_fx.crypto.types import Level, OrderBook, VenueFee
from fronteira_fx.crypto.venues import BinanceVenue
from fronteira_fx.engine.graph import Edge, Graph, celular_graph, find_cycles, node
from fronteira_fx.services import crypto_graph as cg
from fronteira_fx.services.crypto_graph import (
    CryptoMarket,
    CryptoRail,
    crypto_edges,
    find_crypto_alerts,
    is_alertable,
    market_edges,
    rail_edges,
)

D = Decimal
T0 = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
BINANCE_FEE = VenueFee(venue="binance", maker=D("0.0010"), taker=D("0.0010"), source="teste (taxa 0,10% por lado)")
NO_FEE = VenueFee(venue="foxbit", maker=None, taker=None, source="não confirmada")


def book(venue: str, symbol: str, bid: str, ask: str, qty: str = "100") -> OrderBook:
    return OrderBook(
        venue=venue,
        symbol=symbol,
        bids=(Level(D(bid), D(qty)),),
        asks=(Level(D(ask), D(qty)),),
        fetched_at=T0,
    )


def binance_btc_usdt(bid: str, ask: str, qty: str = "100") -> CryptoMarket:
    return CryptoMarket(
        venue="binance", base="BTC", quote="USDT", book=book("binance", "BTCUSDT", bid, ask, qty),
        fee=BINANCE_FEE, target_base=D("1"),
    )


def loop_graph(bid: str, ask: str, fee: VenueFee = BINANCE_FEE, slippage: str = "0") -> Graph:
    market = CryptoMarket(
        venue="binance", base="BTC", quote="USDT", book=book("binance", "BTCUSDT", bid, ask), fee=fee,
        target_base=D("10"),  # 10 BTC a 100 USDT = 1000 USDT, o montante dos testes
    )
    g = Graph()
    g.extend(market_edges([market], slippage_pct=D(slippage)))
    return g


def cycles_usdt(graph: Graph, amount: str = "1000") -> list:
    return find_cycles(graph, {node("USDT", "binance"): D(amount)}, max_len=2, min_roi=None, limit=None)


def test_taxa_binance_010_por_lado_aplicada():
    assert BinanceVenue.default_fee.taker == D("0.0010")
    edges = market_edges([binance_btc_usdt("100", "101")], slippage_pct=D(0))
    buy = next(e for e in edges if e.src == node("USDT", "binance"))
    sell = next(e for e in edges if e.src == node("BTC", "binance"))
    assert buy.fee_pct == D("0.0010") and sell.fee_pct == D("0.0010")
    assert buy.unknown == frozenset() and sell.confidence == "quoted"
    # uma perna: x * (1 - 0,001) * rate; compra de BTC a VWAP 101 com 1000 USDT
    assert buy.apply(D(1000)) == D(1000) * D("0.999") / D(101)


def test_ciclo_lucro_bruto_e_liquido_negativos_rejeitado():
    # compra a 100 e vende a 99: perde antes de qualquer taxa
    graph = loop_graph("99", "100")
    (cyc,) = cycles_usdt(graph)
    assert cyc.gross_gain < 0 and cyc.gain < 0
    assert not is_alertable(cyc)
    assert find_crypto_alerts(graph, {node("USDT", "binance"): D(1000)}, max_len=2) == []


def test_ciclo_lucro_bruto_positivo_mas_liquido_negativo_rejeitado():
    # bruto +0,5%; com 0,80% por perna (taxa Kraken) o líquido fica negativo
    kraken_like = VenueFee(venue="binance", maker=D("0.008"), taker=D("0.008"), source="teste")
    graph = loop_graph("100", "99.5", fee=kraken_like)
    (cyc,) = cycles_usdt(graph, amount="900")  # 10 BTC a 99,5 = 995 USDT: a janela do livro não cobre 1000
    assert cyc.gross_gain > 0 and cyc.gain < 0
    assert not is_alertable(cyc)


def test_ciclo_lucrativo_entra_no_alerta():
    graph = loop_graph("102", "100")
    alerts = find_crypto_alerts(graph, {node("USDT", "binance"): D(1000)}, max_len=2)
    assert len(alerts) == 1 and alerts[0].gain > 0 and alerts[0].executable


def test_slippage_reduz_o_liquido():
    no_slip = cycles_usdt(loop_graph("102", "100", slippage="0"))[0]
    with_slip = cycles_usdt(loop_graph("102", "100", slippage="0.001"))[0]
    assert with_slip.gain < no_slip.gain
    assert with_slip.gross_gain == no_slip.gross_gain  # slippage não mexe no bruto


def test_aresta_referencia_nunca_entra_em_ciclo_executavel():
    graph = loop_graph("102", "100")  # ciclo lucrativo executável
    ref = Edge(node("BTC", "binance"), node("USDT", "binance"), "quote", D("102"), mid_rate=D("102"),
               via="referência de teste", executable=False)
    g = Graph()
    g.extend(graph.edges)
    g.add(ref)
    cycles = cycles_usdt(g)
    flagged = [c for c in cycles if any(not e.executable for e in c.edges)]
    assert flagged, "o ciclo com referência precisa existir no grafo"
    assert all(not c.executable for c in flagged)
    assert all(not is_alertable(c) for c in flagged)
    alerts = find_crypto_alerts(g, {node("USDT", "binance"): D(1000)}, max_len=2)
    assert all(c.executable for c in alerts)


def test_crypto_edges_rejeita_referencia_marcada_como_executavel():
    ref = Edge(node("USDT", "binance"), node("BTC", "binance"), "quote", D("1"), executable=True)
    try:
        crypto_edges([binance_btc_usdt("100", "101")], [], references=[ref])
    except ValueError:
        return
    raise AssertionError("referência com executable=True deveria ser recusada")


def test_custo_desconhecido_vira_incompleto_e_nao_alerta():
    market = CryptoMarket(
        venue="foxbit", base="BTC", quote="BRL", book=book("foxbit", "btcbrl", "100", "102"), fee=NO_FEE,
        target_base=D("1"),
    )
    edges = market_edges([market], slippage_pct=D(0))
    assert edges and all(e.confidence == "incomplete" for e in edges)
    assert all("fees" in e.unknown and "iof" in e.unknown for e in edges)
    g = Graph()
    g.extend(edges)
    for cyc in find_cycles(g, {node("BRL", "foxbit"): D(1000)}, max_len=2, limit=None):
        assert cyc.confidence == "incomplete" and not is_alertable(cyc)


def test_livro_sem_profundidade_para_o_alvo_nao_gera_aresta():
    thin = CryptoMarket(
        venue="binance", base="BTC", quote="USDT", book=book("binance", "BTCUSDT", "100", "101", qty="0.5"),
        fee=BINANCE_FEE, target_base=D("1"),
    )
    assert market_edges([thin]) == []


def test_trilho_com_custo_tempo_e_retencao():
    known = CryptoRail(
        id="btc-teste", src="BTC@binance", dst="BTC@kraken", minutes=30, fee_pct=D("0.0001"),
        fee_fixed=D("0.00002"), retention_hours=24, source="teste",
    )
    (edge,) = rail_edges([known])
    assert edge.minutes == 30 and edge.retention_hours == 24 and edge.confidence == "estimated"
    assert edge.fee_pct == D("0.0001") and edge.executable

    (unknown,) = rail_edges([CryptoRail(id="x", src="USDT@foxbit", dst="USDT@binance", minutes=None,
                                        fee_pct=None, fee_fixed=None, retention_hours=None, source="teste")])
    assert unknown.confidence == "incomplete" and unknown.unknown == frozenset({"fees"})


def test_trilho_de_troca_de_moeda_e_recusado():
    bad = CryptoRail(id="x", src="BRL@brbank", dst="USDT@binance", minutes=1, fee_pct=D(0), fee_fixed=D(0),
                     retention_hours=None, source="teste")
    try:
        rail_edges([bad])
    except ValueError:
        return
    raise AssertionError("trilho com troca de moeda não é trilho")


def test_grafo_com_cripto_no_modo_celular_usa_so_pernas_assistidas():
    from fronteira_fx.services.cycles import build_graph

    extra = crypto_edges([binance_btc_usdt("102", "100")], [], slippage_pct=D(0))
    graph, balances = build_graph([], [], extra_edges=extra)
    assert node("BTC", "binance") in graph.nodes and node("USDT", "binance") in graph.nodes
    cel = celular_graph(graph)
    assert any(e.src == node("USDT", "binance") for e in cel.edges)
    assert all(e.channel in ("assistida", "automatizavel") for e in cel.edges)


def test_grafo_sem_extras_nao_muda():
    from fronteira_fx.services.cycles import build_graph

    graph, balances = build_graph([], [])
    assert not any("binance" in e.via or "foxbit" in e.via for e in graph.edges)
    assert not any(n.endswith(("@binance", "@kraken", "@foxbit")) for n in graph.nodes)


def test_nenhuma_funcao_de_envio_de_ordem_no_modulo():
    public = [name for name, obj in vars(cg).items() if inspect.isfunction(obj) and not name.startswith("_")]
    assert public, "o módulo precisa expor funções"
    forbidden = [n for n in public if re.match(r"^(create|place|cancel|submit|amend|send|withdraw|transfer)", n, re.I)]
    assert forbidden == [], forbidden
    source = inspect.getsource(cg)
    assert not re.search(r"\.post\(|\.request\(|api/v3/order|X-MBX-APIKEY|apiSecret|/sapi/", source)
