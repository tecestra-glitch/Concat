"""Investinglive (RSS 2.0, trecho curto, atribuição) e Fear & Greed (Alternative.me): dedup por guid, piso de 60 s,
o que é guardado, atribuição visível e nenhuma função de ordem. HTTP sempre mockado (respx), sem rede."""

from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx
from sqlalchemy import func, select

from fronteira_fx.market import news as news_mod
from fronteira_fx.market import sentiment as sent_mod
from fronteira_fx.market.news import FEEDS, FEEDS_BY_ID, MAX_EXCERPT_CHARS, FeedSpec, ingest, parse_feed
from fronteira_fx.market.service import MarketPoller, build_scheduler
from fronteira_fx.models import NewsItem, SentimentReading

from .conftest import market_settings, read_fixture

CAPTURED = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
IL = FEEDS_BY_ID["investinglive"]


def _entries():
    return parse_feed(read_fixture("rss_investinglive.xml"), keep_excerpt=True)


# ------------------------------------------------------------------ investinglive: parse e trecho
def test_investinglive_is_rss_2_with_excerpt_and_attribution():
    entries = _entries()
    assert len(entries) == 3
    first = entries[0]
    assert first.guid == "https://investinglive.com/news/exemplo-pmi-servicos/"
    assert first.excerpt == "Anterior 51,7 Esperado 51,5 Texto de exemplo curto."  # HTML removido, sem markup
    assert "<" not in first.excerpt and ">" not in first.excerpt
    assert IL.keep_excerpt is True
    assert "Investinglive.com" in news_mod.attribution_for("investinglive")
    assert "copyright" in news_mod.attribution_for("investinglive").lower()


def test_style_and_script_content_never_reaches_the_excerpt():
    third = _entries()[2]
    assert third.guid == "exemplo-guid-3"
    assert "color" not in third.excerpt  # conteúdo de <style> descartado
    assert "alert" not in third.excerpt  # conteúdo de <script> descartado (o título fica, o código não)


def test_excerpt_is_short_and_cut_at_a_word_with_ellipsis():
    third = _entries()[2]
    assert third.excerpt.endswith("…")
    assert len(third.excerpt) <= MAX_EXCERPT_CHARS + 1
    assert not third.excerpt[:-1].endswith(" ")  # corte em espaço, sem palavra partida no meio


def test_excerpt_is_none_for_feeds_that_do_not_authorize_it():
    entries = parse_feed(read_fixture("rss_infomoney.xml"))  # keep_excerpt=False por padrão
    assert entries and all(e.excerpt is None for e in entries)
    assert FEEDS_BY_ID["infomoney"].keep_excerpt is False


def test_attribution_is_present_for_every_feed_and_demo():
    for feed in FEEDS:
        assert news_mod.attribution_for(feed.feed_id).strip()
    assert "demonstração" in news_mod.attribution_for("demo-ilustrativo").lower()
    assert news_mod.attribution_for(None) == "Fonte não identificada."


# ------------------------------------------------------------------ deduplicação por guid
def test_same_guid_with_another_link_is_stored_once(market_factory):
    entries = _entries()  # itens 1 e 2 têm o mesmo guid, links diferentes
    assert entries[0].guid == entries[1].guid and entries[0].link != entries[1].link
    with market_factory() as s:
        new = ingest(s, IL, entries, captured_at=CAPTURED, data_mode="real")
        s.commit()
    assert len(new) == 2  # o segundo (mesmo guid) foi descartado
    with market_factory() as s:
        guids = sorted(s.scalars(select(NewsItem.guid)))
        assert guids == sorted(["exemplo-guid-3", "https://investinglive.com/news/exemplo-pmi-servicos/"])


def test_second_pass_over_same_guids_stores_nothing(market_factory):
    with market_factory() as s:
        ingest(s, IL, _entries(), captured_at=CAPTURED, data_mode="real")
        s.commit()
    with market_factory() as s:
        assert ingest(s, IL, _entries(), captured_at=CAPTURED, data_mode="real") == []
        s.commit()
    with market_factory() as s:
        assert s.scalar(select(func.count(NewsItem.id))) == 2


def test_guid_is_scoped_to_its_feed_but_link_stays_global(market_factory):
    shared_guid_entry = news_mod.NewsEntry("Mesmo guid", "https://exemplo.com/outra-url", None, guid="g-1")
    with market_factory() as s:
        ingest(s, IL, [shared_guid_entry], captured_at=CAPTURED, data_mode="real")
        s.commit()
    with market_factory() as s:
        # outro feed com o mesmo guid e outro link: não é duplicata pelo guid (guid é por feed)
        other = news_mod.NewsEntry("Outra", "https://exemplo.com/outra-2", None, guid="g-1")
        assert len(ingest(s, FEEDS_BY_ID["infomoney"], [other], captured_at=CAPTURED, data_mode="real")) == 1


def test_stored_row_keeps_only_title_link_dates_guid_and_excerpt(market_factory):
    with market_factory() as s:
        ingest(s, IL, _entries(), captured_at=CAPTURED, data_mode="real")
        s.commit()
    with market_factory() as s:
        row = s.scalars(select(NewsItem).where(NewsItem.guid == "exemplo-guid-3")).one()
        assert row.excerpt and row.excerpt.endswith("…")
        assert row.title.startswith("Exemplo: ata")
        columns = {c.name for c in NewsItem.__table__.columns}
        assert columns == {
            "id", "source", "feed", "title", "link", "guid", "excerpt", "published_at", "captured_at", "data_mode",
        }


# ------------------------------------------------------------------ piso de 60 s
def test_feed_spec_below_the_60_second_floor_is_refused():
    with pytest.raises(ValueError, match="piso de 60 s"):
        FeedSpec("x", "x", "X", "https://exemplo.com/feed", 30)


def test_every_registered_feed_and_the_sentiment_source_poll_at_60s_or_more():
    assert all(f.poll_interval_s >= 60 for f in FEEDS)
    assert sent_mod.FNG_POLL_INTERVAL_S >= 60


def test_scheduler_never_goes_below_60_seconds_even_when_forced():
    scheduler = build_scheduler(lambda: CAPTURED)
    for source in scheduler.sources():
        assert source.min_interval_s >= 60
        assert source.interval_s >= 60
    scheduler.add_source("forcado", 5, manual_interval_s=5)
    forced = next(s for s in scheduler.sources() if s.source_id == "forcado")
    assert forced.interval_s >= 60 and forced.min_interval_s >= 60


@respx.mock
async def test_investinglive_is_not_polled_before_60_seconds(market_factory):
    class Clock:
        now = CAPTURED

        def __call__(self):
            return self.now

    clock = Clock()
    route = respx.get(IL.url).mock(return_value=httpx.Response(200, content=read_fixture("rss_investinglive.xml")))
    poller = MarketPoller(market_factory, market_settings("real"), clock=clock)
    for source in poller.scheduler.sources():
        if source.source_id != "investinglive":
            poller.scheduler.remove_source(source.source_id)
    try:
        assert len(await poller.run_once()) == 1
        clock.now = CAPTURED + timedelta(seconds=59)
        assert await poller.run_once() == []
        clock.now = CAPTURED + timedelta(seconds=60)
        assert len(await poller.run_once()) == 1
    finally:
        await poller.aclose()
    assert route.call_count == 2


# ------------------------------------------------------------------ Fear & Greed
def test_fng_parses_the_latest_reading_with_utc_time():
    draft = sent_mod.parse_fng(read_fixture_json())
    assert draft.index_id == "fng" and draft.value == 34 and draft.classification == "Fear"
    assert draft.observed_at == datetime(2026, 11, 4, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(metadata={"error": "rate limit"}),
        lambda d: d["data"][0].update(value="101"),
        lambda d: d["data"][0].update(value="abc"),
        lambda d: d["data"][0].update(value=True),
        lambda d: d["data"][0].update(timestamp="amanha"),
        lambda d: d["data"][0].update(value_classification="   "),
        lambda d: d.update(data=[]),
        lambda d: d.update(data="nao e lista"),
    ],
)
def test_fng_refuses_malformed_or_errored_answers(mutate):
    data = read_fixture_json()
    mutate(data)
    with pytest.raises(sent_mod.SentimentFormatError):
        sent_mod.parse_fng(data)


def test_fng_is_stored_once_per_observation_and_follows_data_mode(market_factory):
    draft = sent_mod.parse_fng(read_fixture_json())
    with market_factory() as s:
        assert sent_mod.ingest_fng(s, draft, captured_at=CAPTURED, data_mode="real") is True
        assert sent_mod.ingest_fng(s, draft, captured_at=CAPTURED, data_mode="real") is False
        s.commit()
    with market_factory() as s:
        assert s.scalar(select(func.count(SentimentReading.id))) == 1
        assert sent_mod.list_readings(s, "demo", 10) == []
        row = sent_mod.list_readings(s, "real", 10)[0]
        assert row.provider == "alternative.me" and row.value == 34


@respx.mock
async def test_fng_poll_stores_reading_with_attribution_and_waits_an_hour(market_factory):
    class Clock:
        now = CAPTURED

        def __call__(self):
            return self.now

    clock = Clock()
    route = respx.get(sent_mod.FNG_URL).mock(
        return_value=httpx.Response(200, content=read_fixture("fng_alternative.json"))
    )
    poller = MarketPoller(market_factory, market_settings("real"), clock=clock)
    for source in poller.scheduler.sources():
        if source.source_id != sent_mod.FNG_SOURCE:
            poller.scheduler.remove_source(source.source_id)
    try:
        first = await poller.run_once()
        assert first[0].ok and first[0].changed is True
        clock.now = CAPTURED + timedelta(seconds=600)
        assert await poller.run_once() == []  # dentro do intervalo horário
    finally:
        await poller.aclose()
    assert route.call_count == 1
    assert "Alternative.me" in sent_mod.FNG_ATTRIBUTION
    assert "não preço" in sent_mod.FNG_ATTRIBUTION


def read_fixture_json():
    import json

    return json.loads(read_fixture("fng_alternative.json"))


# ------------------------------------------------------------------ nada de envio de ordem
def test_no_order_or_money_movement_function_in_the_market_modules():
    banned = ("order", "ordem", "trade", "send", "transfer", "withdraw", "buy", "sell", "submit", "place")
    root = Path(news_mod.__file__).parent
    for name in ("news.py", "sentiment.py", "service.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert not any(word in node.name.lower() for word in banned), node.name
