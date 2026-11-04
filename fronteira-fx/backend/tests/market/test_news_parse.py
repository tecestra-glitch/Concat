from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime

import pytest

from fronteira_fx.market.news import FEEDS, FEEDS_BY_ID, FeedFormatError, NewsEntry, parse_feed

from .conftest import read_fixture


def test_rss_infomoney_items_titles_links_and_utc_dates():
    entries = parse_feed(read_fixture("rss_infomoney.xml"))
    assert len(entries) == 3
    first = entries[0]
    assert first.title == "Justiça proíbe Meta de usar conteúdo jornalístico sem autorização"
    assert first.link.startswith("https://www.infomoney.com.br/")
    assert first.published_at == datetime(2026, 11, 4, 0, 41, 45, tzinfo=UTC)


def test_rfc822_date_with_offset_is_converted_to_utc():
    entries = parse_feed(read_fixture("rss_agencia_brasil.xml"))
    assert entries[0].title.startswith("Dólar sobe 0,74%")
    # "Tue, 03 Nov 2026 18:59:00 -0300" → 21:59 UTC
    assert entries[0].published_at == datetime(2026, 11, 3, 21, 59, 0, tzinfo=UTC)


def test_atom_bcb_uses_alternate_link_and_updated_date():
    entries = parse_feed(read_fixture("atom_bcb_copom.xml"))
    assert len(entries) == 2
    assert entries[0].link == "https://www.bcb.gov.br/controleinflacao/comunicadoscopom/21261"
    assert "13,75" in entries[0].title
    # "2026-09-16T18:32:02-03:00" → 21:32:02 UTC
    assert entries[0].published_at == datetime(2026, 9, 16, 21, 32, 2, tzinfo=UTC)


def test_mercopress_rss_english_items():
    entries = parse_feed(read_fixture("rss_mercopress_economy.xml"))
    assert len(entries) == 3
    assert all(e.link.startswith("https://en.mercopress.com/") for e in entries)
    assert entries[0].published_at == datetime(2026, 10, 30, 18, 18, tzinfo=UTC)


@pytest.mark.parametrize("name", ["rss_infomoney_economia_vazio.xml", "rss_infomoney_mercados_vazio.xml"])
def test_empty_infomoney_channels_are_an_empty_list_not_an_error(name):
    assert parse_feed(read_fixture(name)) == []


def test_only_title_link_and_date_are_kept():
    # nenhum campo de texto da matéria (descrição, conteúdo) existe no modelo de saída
    assert [f.name for f in fields(NewsEntry)] == ["title", "link", "published_at"]


def test_doctype_and_entities_are_refused():
    evil = b'<?xml version="1.0"?><!DOCTYPE rss [<!ENTITY x "y">]><rss version="2.0"><channel></channel></rss>'
    with pytest.raises(FeedFormatError, match="DTD"):
        parse_feed(evil)


def test_unknown_document_and_broken_xml_are_refused():
    with pytest.raises(FeedFormatError, match="formato desconhecido"):
        parse_feed(b"<html><body>manutencao</body></html>")
    with pytest.raises(FeedFormatError, match="XML inválido"):
        parse_feed(b"<rss><channel>")


def test_unsafe_links_and_empty_titles_are_skipped():
    xml = (
        '<?xml version="1.0"?><rss version="2.0"><channel>'
        "<item><title>Ruim</title><link>javascript:alert(1)</link></item>"
        "<item><title>   </title><link>https://exemplo.com/vazio</link></item>"
        "<item><title>  Dólar   <b>fecha</b> em alta </title><link>https://exemplo.com/ok</link>"
        "<pubDate>nao e data</pubDate></item>"
        "</channel></rss>"
    ).encode()
    entries = parse_feed(xml)
    assert len(entries) == 1
    assert entries[0].title == "Dólar fecha em alta"  # espaços colapsados; markup vira só texto
    assert entries[0].published_at is None


def test_feed_registry_has_the_confirmed_sources_and_safe_intervals():
    ids = set(FEEDS_BY_ID)
    assert {"infomoney", "infomoney-economia", "infomoney-mercados", "agencia-brasil-economia"} <= ids
    assert {"bcb-copom-comunicados", "bcb-copom-atas", "mercopress-paraguay", "mercopress-economy"} <= ids
    assert len(FEEDS) == len(ids) == 8
    assert all(f.poll_interval_s >= 60 for f in FEEDS)
    assert all(f.url.startswith("https://") for f in FEEDS)
