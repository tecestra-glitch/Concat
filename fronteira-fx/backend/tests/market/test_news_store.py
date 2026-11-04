from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from fronteira_fx.market.news import EVENT_NEW_NEWS, FEEDS_BY_ID, NewsEntry, ingest, parse_feed
from fronteira_fx.models import NewsItem
from fronteira_fx.services import events as events_svc

from .conftest import read_fixture

CAPTURED = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def test_first_ingest_stores_items_and_emits_one_event_each(market_factory):
    feed = FEEDS_BY_ID["infomoney"]
    entries = parse_feed(read_fixture("rss_infomoney.xml"))
    with market_factory() as s:
        new = ingest(s, feed, entries, captured_at=CAPTURED, data_mode="real")
        s.commit()
    assert len(new) == 3
    with market_factory() as s:
        assert s.scalar(select(func.count(NewsItem.id))) == 3
        events = events_svc.replay(s, 0, data_mode="real")
    assert [e.type for e in events] == [EVENT_NEW_NEWS] * 3
    payload = events[0].payload
    assert set(payload) == {"id", "source", "feed", "title", "link", "published_at", "captured_at"}
    assert payload["source"] == "infomoney" and payload["title"].startswith("Justiça")


def test_second_pass_over_same_links_is_deduplicated(market_factory):
    feed = FEEDS_BY_ID["infomoney"]
    entries = parse_feed(read_fixture("rss_infomoney.xml"))
    with market_factory() as s:
        ingest(s, feed, entries, captured_at=CAPTURED, data_mode="real")
        s.commit()
    with market_factory() as s:
        assert ingest(s, feed, entries, captured_at=CAPTURED, data_mode="real") == []
        s.commit()
    with market_factory() as s:
        assert s.scalar(select(func.count(NewsItem.id))) == 3
        assert len(events_svc.replay(s, 0, data_mode="real")) == 3


def test_same_link_in_another_feed_is_not_stored_twice(market_factory):
    entries = [
        NewsEntry("Copom mantém", "https://exemplo.com/a", None),
        NewsEntry("Copom mantém", "https://exemplo.com/a", None),
    ]
    with market_factory() as s:
        first = ingest(s, FEEDS_BY_ID["infomoney"], entries[:1], captured_at=CAPTURED, data_mode="real")
        second = ingest(s, FEEDS_BY_ID["agencia-brasil-economia"], entries, captured_at=CAPTURED, data_mode="real")
        s.commit()
    assert len(first) == 1 and second == []


def test_events_follow_the_data_mode(market_factory):
    with market_factory() as s:
        ingest(
            s,
            FEEDS_BY_ID["bcb-copom-atas"],
            parse_feed(read_fixture("atom_bcb_atas.xml")),
            captured_at=CAPTURED,
            data_mode="demo",
        )
        s.commit()
    with market_factory() as s:
        assert events_svc.replay(s, 0, data_mode="real") == []
        assert len(events_svc.replay(s, 0, data_mode="demo")) == 2
