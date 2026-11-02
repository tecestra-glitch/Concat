"""Validação do contrato: kinds, textos, tags e TTL."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from fronteira_fx.memory.models import Memory, MemoryCreate, normalize_tags

T0 = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)


def test_create_accepts_contract_body() -> None:
    body = MemoryCreate.model_validate(
        {
            "kind": "decision",
            "text": "não usar Nomad acima de US$ 1.000 sem confirmar IOF",
            "tags": ["nomad"],
            "ttl_days": 30,
        }
    )
    assert body.kind == "decision"
    assert body.tags == ["nomad"]
    assert body.ttl_days == 30


def test_create_defaults_tags_and_ttl() -> None:
    body = MemoryCreate(kind="fact", text="ueno cobra IOF")
    assert body.tags == []
    assert body.ttl_days is None


@pytest.mark.parametrize("kind", ["opinion", "", "Preference"])
def test_create_rejects_unknown_kind(kind: str) -> None:
    with pytest.raises(ValidationError):
        MemoryCreate(kind=kind, text="x")


@pytest.mark.parametrize("text", ["", "   ", "x" * 2001])
def test_create_rejects_blank_or_huge_text(text: str) -> None:
    with pytest.raises(ValidationError):
        MemoryCreate(kind="fact", text=text)


def test_create_strips_text() -> None:
    assert MemoryCreate(kind="fact", text="  ueno  ").text == "ueno"


@pytest.mark.parametrize("ttl", [0, -1, 3651])
def test_create_rejects_bad_ttl(ttl: int) -> None:
    with pytest.raises(ValidationError):
        MemoryCreate(kind="fact", text="x", ttl_days=ttl)


def test_create_rejects_too_many_tags() -> None:
    with pytest.raises(ValidationError):
        MemoryCreate(kind="fact", text="x", tags=[f"t{i}" for i in range(21)])


def test_create_rejects_empty_tag() -> None:
    with pytest.raises(ValidationError):
        MemoryCreate(kind="fact", text="x", tags=["  "])


def test_tags_are_lowercased_and_deduplicated_in_order() -> None:
    body = MemoryCreate(kind="fact", text="x", tags=["UENO", " ueno ", "CDE", "ueno"])
    assert body.tags == ["ueno", "cde"]


def test_normalize_tags_keeps_first_occurrence_order() -> None:
    assert normalize_tags(["b", "A", "a", "b"]) == ["b", "a"]


def test_memory_serializes_to_contract_shape() -> None:
    memory = Memory(
        id="7d9c1f2e-0000-4000-8000-000000000001",
        kind="outcome",
        text="remessa WU CDE->ueno em 2 dias",
        tags=["ueno"],
        created_at=T0,
        expires_at=None,
        source="agent",
    )
    payload = memory.model_dump(mode="json")
    assert list(payload) == ["id", "kind", "text", "tags", "created_at", "expires_at", "source"]
    assert payload["created_at"] == "2026-11-02T12:00:00Z"
    assert payload["expires_at"] is None
