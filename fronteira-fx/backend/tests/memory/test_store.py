"""Armazenamentos (InMemoryStore e SqlStore, mesma suíte): CRUD, TTL, ranking e filtros."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fronteira_fx.memory.models import Memory, MemoryKind, MemorySource
from fronteira_fx.memory.store import MemoryStore, fold, query_tokens, select_memories, tokens

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def mem(
    memory_id: str,
    text: str,
    *,
    kind: MemoryKind = "fact",
    tags: tuple[str, ...] = (),
    created: datetime = T0,
    expires: datetime | None = None,
    source: MemorySource = "user",
) -> Memory:
    return Memory(
        id=memory_id,
        kind=kind,
        text=text,
        tags=list(tags),
        created_at=created,
        expires_at=expires,
        source=source,
    )


def ids(memories: list[Memory]) -> list[str]:
    return [m.id for m in memories]


# --- CRUD -------------------------------------------------------------------------------------------


def test_add_then_get_roundtrips_fields(store: MemoryStore) -> None:
    original = mem("a", "Cartão ueno tem IOF", kind="fact", tags=("ueno", "cartão"), source="agent")
    store.add(original)
    loaded = store.get("a", now=T0)
    assert loaded == original
    assert loaded is not None and loaded.created_at.tzinfo is not None


def test_get_unknown_returns_none(store: MemoryStore) -> None:
    assert store.get("nope", now=T0) is None


def test_delete_removes_and_reports(store: MemoryStore) -> None:
    store.add(mem("a", "x"))
    assert store.delete("a", now=T0) is True
    assert store.get("a", now=T0) is None
    assert store.delete("a", now=T0) is False


def test_delete_ignores_expired_entries(store: MemoryStore) -> None:
    store.add(mem("a", "x", expires=T0 + timedelta(hours=1)))
    assert store.delete("a", now=T0 + timedelta(hours=2)) is False


# --- TTL --------------------------------------------------------------------------------------------


def test_expiry_boundary_is_exclusive(store: MemoryStore) -> None:
    expires = T0 + timedelta(days=1)
    store.add(mem("a", "x", expires=expires))
    assert store.get("a", now=expires - timedelta(seconds=1)) is not None
    assert store.get("a", now=expires) is None


def test_expired_hidden_from_recall_and_purged(store: MemoryStore) -> None:
    store.add(mem("keep", "permanente", created=T0))
    store.add(mem("short", "temporária", created=T0 + timedelta(minutes=1), expires=T0 + timedelta(hours=1)))
    store.add(mem("later", "outra temporária", created=T0 + timedelta(minutes=2), expires=T0 + timedelta(hours=2)))

    at = T0 + timedelta(minutes=90)
    assert ids(store.recall(now=at)) == ["later", "keep"]
    assert store.purge_expired(now=at) == 1
    assert store.purge_expired(now=at) == 0
    assert ids(store.recall(now=T0 + timedelta(hours=3))) == ["keep"]


def test_purge_keeps_permanent_entries(store: MemoryStore) -> None:
    store.add(mem("a", "x"))
    assert store.purge_expired(now=T0 + timedelta(days=3650)) == 0
    assert store.get("a", now=T0 + timedelta(days=3650)) is not None


# --- recall: ordering, ranking, filters -------------------------------------------------------------


def test_recall_without_query_is_most_recent_first(store: MemoryStore) -> None:
    store.add(mem("a", "primeira", created=T0))
    store.add(mem("b", "segunda", created=T0 + timedelta(minutes=1)))
    store.add(mem("c", "terceira", created=T0 + timedelta(minutes=2)))
    assert ids(store.recall(now=T0 + timedelta(minutes=3))) == ["c", "b", "a"]
    assert ids(store.recall(limit=2, now=T0 + timedelta(minutes=3))) == ["c", "b"]


def test_query_ranks_matching_text_and_tags_above_recent_noise(store: MemoryStore) -> None:
    # 'ueno' é a mais antiga; sem ranking, a Nomad (mais nova) sairia primeiro.
    store.add(mem("ueno", "Ueno cobra IOF no cartão de crédito", tags=("ueno",), created=T0))
    store.add(mem("nomad", "Nomad cartão virtual sem IOF", tags=("nomad",), created=T0 + timedelta(minutes=1)))
    store.add(
        mem("alberdi", "Alberdi PJC melhora acima de R$ 25 mil", tags=("alberdi",), created=T0 + timedelta(minutes=2))
    )

    found = store.recall(q="ueno cartão", now=T0 + timedelta(minutes=3))
    assert ids(found) == ["ueno", "nomad"]


def test_equal_scores_break_ties_by_recency(store: MemoryStore) -> None:
    store.add(mem("old", "saldo ueno em dólar", created=T0))
    store.add(mem("new", "saldo ueno em real", created=T0 + timedelta(minutes=1)))
    assert ids(store.recall(q="saldo ueno", now=T0 + timedelta(minutes=2))) == ["new", "old"]


def test_query_is_case_and_accent_insensitive(store: MemoryStore) -> None:
    store.add(mem("a", "Cartão de crédito da Ueno"))
    assert ids(store.recall(q="CARTAO", now=T0)) == ["a"]
    assert ids(store.recall(q="ueno", now=T0)) == ["a"]


def test_query_without_matches_returns_nothing(store: MemoryStore) -> None:
    store.add(mem("a", "Alberdi PJC melhora acima de R$ 25 mil"))
    assert store.recall(q="western", now=T0) == []


def test_stopwords_do_not_count_when_other_terms_exist(store: MemoryStore) -> None:
    store.add(mem("taxa", "taxa do cartão"))
    store.add(mem("tarifa", "tarifa de saque"))
    assert ids(store.recall(q="cartão de crédito", now=T0)) == ["taxa"]


def test_kind_filter(store: MemoryStore) -> None:
    store.add(mem("p", "prefere Pix", kind="preference", created=T0))
    store.add(mem("d", "usar ueno", kind="decision", created=T0 + timedelta(minutes=1)))
    store.add(mem("f", "ueno cobra IOF", kind="fact", created=T0 + timedelta(minutes=2)))
    assert ids(store.recall(kind="decision", now=T0 + timedelta(minutes=3))) == ["d"]
    assert ids(store.recall(q="ueno", kind="fact", now=T0 + timedelta(minutes=3))) == ["f"]


def test_tag_filter_is_case_insensitive_and_exact(store: MemoryStore) -> None:
    store.add(mem("u", "saldo", tags=("ueno", "cde")))
    store.add(mem("n", "saldo", tags=("nomad",)))
    assert ids(store.recall(tag="UENO", now=T0)) == ["u"]
    assert store.recall(tag="ue", now=T0) == []


def test_tag_and_query_combine(store: MemoryStore) -> None:
    store.add(mem("u", "IOF do cartão", tags=("ueno",)))
    store.add(mem("n", "IOF do cartão", tags=("nomad",)))
    assert ids(store.recall(q="iof", tag="nomad", now=T0)) == ["n"]


def test_limit_applies_after_ranking(store: MemoryStore) -> None:
    for i in range(5):
        store.add(mem(f"x{i}", "ueno", created=T0 + timedelta(minutes=i)))
    store.add(mem("best", "ueno cartão cartão", created=T0))
    assert ids(store.recall(q="ueno cartão", limit=1, now=T0 + timedelta(minutes=10)))[0] == "best"


# --- pure helpers -----------------------------------------------------------------------------------


def test_fold_removes_case_and_accents() -> None:
    assert fold("Cartão Crédito") == "cartao credito"


def test_tokens_split_on_punctuation() -> None:
    assert tokens("US$ 1.000, sem IOF!") == {"us", "1", "000", "sem", "iof"}


def test_query_tokens_drop_stopwords_unless_only_stopwords() -> None:
    assert query_tokens("cartão de crédito") == {"cartao", "credito"}
    assert query_tokens("de") == {"de"}


def test_select_memories_without_query_honours_limit() -> None:
    items = [mem(f"m{i}", "x", created=T0 + timedelta(minutes=i)) for i in range(3)]
    assert ids(select_memories(items, limit=2)) == ["m2", "m1"]
