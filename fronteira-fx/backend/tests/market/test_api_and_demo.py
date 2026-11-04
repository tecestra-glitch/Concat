"""Rotas /v1/market/*, semeadura da demonstração e isolamento: referência de mercado nunca vira aresta de ciclo."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fronteira_fx.market.demo import seed_market_demo
from fronteira_fx.models import MarketQuote, NewsItem

from .conftest import market_settings

NEWS_FIXTURE_TIME = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
PKG = Path(__file__).resolve().parents[2] / "src" / "fronteira_fx"


def _news(db, n: int, source: str, hours_ago: int) -> None:
    db.add(
        NewsItem(
            source=source,
            feed=f"{source}-feed",
            title=f"Manchete {n}",
            link=f"https://exemplo.com/{source}/{n}",
            published_at=NEWS_FIXTURE_TIME - timedelta(hours=hours_ago),
            captured_at=NEWS_FIXTURE_TIME,
            data_mode="real",
        )
    )


def test_news_is_newest_first_filterable_and_limited(client, db):
    _news(db, 1, "infomoney", 5)
    _news(db, 2, "bcb", 1)
    _news(db, 3, "infomoney", 2)
    db.flush()
    r = client.get("/v1/market/news")
    assert r.status_code == 200
    titles = [x["title"] for x in r.json()]
    assert titles == ["Manchete 2", "Manchete 3", "Manchete 1"]
    assert {"id", "source", "feed", "title", "link", "published_at", "captured_at", "data_mode"} <= set(r.json()[0])
    only_bcb = client.get("/v1/market/news", params={"source": "bcb"}).json()
    assert [x["title"] for x in only_bcb] == ["Manchete 2"]
    assert len(client.get("/v1/market/news", params={"limit": 2}).json()) == 2
    since = (NEWS_FIXTURE_TIME - timedelta(hours=3)).isoformat()
    recent = client.get("/v1/market/news", params={"since": since}).json()
    assert [x["title"] for x in recent] == ["Manchete 2", "Manchete 3"]
    assert client.get("/v1/market/news", params={"limit": 500}).status_code == 422


def test_quotes_are_reference_only_and_strings_are_decimal(client, db):
    db.add(
        MarketQuote(
            instrument="USDT/BRL",
            label="Dólar cripto (USDT em reais)",
            kind="crypto",
            source="binance",
            price=Decimal("5.5179"),
            change_pct=Decimal("0.876"),
            observed_at=NEWS_FIXTURE_TIME,
            captured_at=NEWS_FIXTURE_TIME,
            data_mode="real",
        )
    )
    db.flush()
    rows = client.get("/v1/market/quotes").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["price"] == "5.5179" and row["change_pct"] == "0.876"
    assert row["executable"] is False
    assert "Não é preço executável" in row["note"]


def test_volatility_without_candles_is_insufficient_data_not_a_number(client):
    rows = client.get("/v1/market/volatility").json()
    assert [r["instrument"] for r in rows] == ["BTC/USDT", "ETH/USDT", "USDT/BRL"]
    for r in rows:
        assert r["status"] == "insufficient_data"
        assert r["regime"] is None and r["alert"] is False and r["ewma_pct_5m"] is None


def test_market_routes_refuse_another_data_mode(client):
    assert client.get("/v1/market/news", params={"data_mode": "demo"}).status_code == 409
    assert client.get("/v1/market/quotes", params={"data_mode": "simulation"}).status_code == 409
    assert client.get("/v1/market/volatility", params={"data_mode": "demo"}).status_code == 409


def test_demo_seed_is_idempotent_and_marked_demo(market_factory):
    settings = market_settings("demo")
    created = seed_market_demo(market_factory, settings, now=NEWS_FIXTURE_TIME)
    assert created > 0
    assert seed_market_demo(market_factory, settings, now=NEWS_FIXTURE_TIME) == 0
    with market_factory() as s:
        news = s.query(NewsItem).all()
        assert len(news) == 6 and {n.source for n in news} == {"demo"}
        assert all(n.link.startswith("https://demo.invalid/") and n.data_mode == "demo" for n in news)
        assert all("Demonstração" in n.title for n in news)


def test_demo_seed_does_nothing_outside_demo_mode(market_factory):
    assert seed_market_demo(market_factory, market_settings("real"), now=NEWS_FIXTURE_TIME) == 0


def test_demo_volatility_is_computed_from_seeded_candles(market_factory):
    from fronteira_fx.market.read import volatility_payloads

    seed_market_demo(market_factory, market_settings("demo"), now=NEWS_FIXTURE_TIME)
    with market_factory() as s:
        rows = volatility_payloads(s, "demo")
    assert [r["status"] for r in rows] == ["ok", "ok", "ok"]
    assert all(r["regime"] in {"normal", "alta", "muito_alta"} for r in rows)


def test_reference_quotes_never_enter_the_graph_or_the_cycle_engine():
    """Regra do projeto: cotação de referência nunca é aresta de ciclo. O grafo e o motor não importam market."""
    offenders = []
    for path in list(PKG.glob("graph/*.py")) + list(PKG.glob("engine/*.py")) + [PKG / "services" / "cycles.py"]:
        text = path.read_text(encoding="utf-8")
        if re.search(r"(from|import)\s+[.\w]*market", text):
            offenders.append(path.name)
    assert offenders == []
