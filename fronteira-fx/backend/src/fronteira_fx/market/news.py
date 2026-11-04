"""Manchetes de feeds públicos RSS 2.0 e Atom (módulo `market`).

Guarda só título, link, fonte, hora de publicação e hora de captura. Nenhum texto da matéria é guardado (o
InfoMoney reserva direitos). O texto vindo dos feeds é DADO NÃO CONFIÁVEL: a interface escapa tudo e nenhum
modelo o recebe como instrução.

Sondagem: o intervalo por feed começa em `poll_interval_s` e fica no piso de 60 s do agendador
(`watch.scheduler`); a busca usa requisição condicional (ETag / If-Modified-Since, `watch.fetcher`).
"""

from __future__ import annotations

import email.utils
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import NewsItem
from ..services import events as events_svc

MAX_ENTRIES_PER_FEED = 200
MAX_TITLE_CHARS = 300
MAX_LINK_CHARS = 2048
EVENT_NEW_NEWS = "market.news"


class FeedFormatError(ValueError):
    """Feed que não é RSS nem Atom, ou que declara DTD/entidades (recusados por segurança)."""


@dataclass(frozen=True, slots=True)
class FeedSpec:
    feed_id: str
    source: str  # editora: infomoney | agencia-brasil | bcb | mercopress
    label: str
    url: str
    poll_interval_s: int


FEEDS: tuple[FeedSpec, ...] = (
    FeedSpec("infomoney", "infomoney", "InfoMoney", "https://www.infomoney.com.br/feed/", 60),
    FeedSpec(
        "infomoney-economia", "infomoney", "InfoMoney Economia", "https://www.infomoney.com.br/economia/feed/", 60
    ),
    FeedSpec(
        "infomoney-mercados", "infomoney", "InfoMoney Mercados", "https://www.infomoney.com.br/mercados/feed/", 60
    ),
    FeedSpec(
        "agencia-brasil-economia",
        "agencia-brasil",
        "Agência Brasil Economia",
        "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml",
        60,
    ),
    FeedSpec(
        "bcb-copom-comunicados",
        "bcb",
        "BCB Comunicados do Copom",
        "https://www.bcb.gov.br/api/feed/sitebcb/sitefeeds/comunicadoscopom",
        300,
    ),
    FeedSpec(
        "bcb-copom-atas", "bcb", "BCB Atas do Copom", "https://www.bcb.gov.br/api/feed/sitebcb/sitefeeds/atascopom", 300
    ),
    FeedSpec("mercopress-paraguay", "mercopress", "MercoPress Paraguay", "https://en.mercopress.com/rss/paraguay", 300),
    FeedSpec("mercopress-economy", "mercopress", "MercoPress Economy", "https://en.mercopress.com/rss/economy", 300),
)
FEEDS_BY_ID: dict[str, FeedSpec] = {f.feed_id: f for f in FEEDS}
SOURCES: tuple[str, ...] = tuple(sorted({f.source for f in FEEDS}))


@dataclass(frozen=True, slots=True)
class NewsEntry:
    title: str
    link: str
    published_at: datetime | None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(el: ET.Element, name: str) -> str | None:
    for child in el:
        if _local(child.tag) == name:
            text = "".join(child.itertext())  # inclui o texto de tags internas, se houver
            return text if text else None
    return None


def _atom_link(el: ET.Element) -> str | None:
    fallback: str | None = None
    for child in el:
        if _local(child.tag) != "link":
            continue
        href = child.get("href")
        if not href:
            continue
        if child.get("rel") in (None, "", "alternate"):
            return href
        fallback = fallback or href
    return fallback


def _parse_date(raw: str | None, *, rfc822: bool) -> datetime | None:
    if not raw or not raw.strip():
        return None
    try:
        value = email.utils.parsedate_to_datetime(raw.strip()) if rfc822 else datetime.fromisoformat(raw.strip())
    except (TypeError, ValueError):
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _clean_title(raw: str | None) -> str | None:
    if raw is None:
        return None
    title = " ".join(raw.split())[:MAX_TITLE_CHARS]
    return title or None


def _clean_link(raw: str | None) -> str | None:
    if raw is None:
        return None
    link = raw.strip()
    if not (link.startswith("https://") or link.startswith("http://")) or len(link) > MAX_LINK_CHARS:
        return None
    return link


def parse_feed(data: bytes) -> list[NewsEntry]:
    """RSS 2.0 ou Atom → manchetes (título, link, publicação). Feed sem itens devolve lista vazia."""
    upper = data.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise FeedFormatError("feed com DTD ou entidades: recusado")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise FeedFormatError(f"XML inválido: {exc}") from exc
    root_name = _local(root.tag)
    if root_name not in ("rss", "feed", "RDF"):
        raise FeedFormatError(f"formato desconhecido: {root_name}")
    out: list[NewsEntry] = []
    for el in root.iter():
        name = _local(el.tag)
        if name not in ("item", "entry"):
            continue
        title = _clean_title(_child_text(el, "title"))
        if name == "item":
            link = _clean_link(_child_text(el, "link"))
            published = _parse_date(_child_text(el, "pubDate"), rfc822=True)
        else:
            link = _clean_link(_atom_link(el))
            published = _parse_date(_child_text(el, "published") or _child_text(el, "updated"), rfc822=False)
        if title is None or link is None:
            continue
        out.append(NewsEntry(title=title, link=link, published_at=published))
        if len(out) >= MAX_ENTRIES_PER_FEED:
            break
    return out


def ingest(
    session: Session,
    feed: FeedSpec,
    entries: Iterable[NewsEntry],
    *,
    captured_at: datetime,
    data_mode: str,
) -> list[NewsItem]:
    """Grava as manchetes novas (deduplicadas por link) e emite um evento `market.news` por item."""
    entries = list(entries)
    links = [e.link for e in entries]
    known: set[str] = set(session.scalars(select(NewsItem.link).where(NewsItem.link.in_(links)))) if links else set()
    new: list[NewsItem] = []
    for entry in entries:
        if entry.link in known:
            continue
        known.add(entry.link)
        item = NewsItem(
            source=feed.source,
            feed=feed.feed_id,
            title=entry.title,
            link=entry.link,
            published_at=entry.published_at,
            captured_at=captured_at,
            data_mode=data_mode,
        )
        session.add(item)
        new.append(item)
    session.flush()
    for item in new:
        events_svc.append_event(
            session,
            EVENT_NEW_NEWS,
            {
                "id": item.id,
                "source": item.source,
                "feed": item.feed,
                "title": item.title,
                "link": item.link,
                "published_at": item.published_at.isoformat() if item.published_at else None,
                "captured_at": item.captured_at.isoformat(),
            },
            data_mode=data_mode,
            ts=captured_at,
        )
    return new
