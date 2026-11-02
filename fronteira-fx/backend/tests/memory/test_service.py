"""Serviço: TTL com relógio falso, CRUD, validação de limite e formato do resumo em pt-BR."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from fronteira_fx.memory.models import MemoryCreate
from fronteira_fx.memory.service import SUMMARY_ITEM_CHARS, MemoryService

from .conftest import T0, FakeClock


def create(service: MemoryService, kind: str, text: str, **kwargs) -> str:
    return service.remember(MemoryCreate(kind=kind, text=text, **kwargs)).id


def test_remember_fills_id_timestamps_and_source(service: MemoryService, clock: FakeClock) -> None:
    memory = service.remember(MemoryCreate(kind="fact", text="ueno cobra IOF", tags=["Ueno"]), source="agent")
    assert str(uuid.UUID(memory.id)) == memory.id
    assert memory.created_at == T0
    assert memory.expires_at is None
    assert memory.source == "agent"
    assert memory.tags == ["ueno"]


def test_default_source_is_user(service: MemoryService) -> None:
    assert service.remember(MemoryCreate(kind="preference", text="prefere Pix")).source == "user"


def test_ttl_expires_with_fake_clock(service: MemoryService, clock: FakeClock) -> None:
    memory = service.remember(
        MemoryCreate(kind="decision", text="não usar Nomad acima de US$ 1.000 sem confirmar IOF", ttl_days=2)
    )
    assert memory.expires_at == T0 + timedelta(days=2)

    clock.advance(days=1, hours=23, minutes=59)
    assert [m.id for m in service.recall()] == [memory.id]

    clock.advance(minutes=1)
    assert service.recall() == []
    assert service.forget(memory.id) is False
    assert service.purge_expired() == 1
    assert service.purge_expired() == 0


def test_permanent_memory_survives_years(service: MemoryService, clock: FakeClock) -> None:
    memory = service.remember(MemoryCreate(kind="fact", text="Alberdi PJC melhora acima de R$ 25 mil"))
    clock.advance(days=3650)
    assert [m.id for m in service.recall()] == [memory.id]


def test_forget_removes_once(service: MemoryService) -> None:
    memory = service.remember(MemoryCreate(kind="fact", text="ueno cobra IOF"))
    assert service.forget(memory.id) is True
    assert service.recall() == []
    assert service.forget(memory.id) is False


def test_recall_filters_by_kind_tag_and_query(service: MemoryService, clock: FakeClock) -> None:
    create(service, "fact", "ueno cobra IOF no cartão", tags=["ueno"])
    clock.advance(minutes=1)
    nomad = create(service, "decision", "Nomad cartão virtual só com confirmação", tags=["nomad"])
    clock.advance(minutes=1)

    assert [m.id for m in service.recall(kind="decision")] == [nomad]
    assert [m.id for m in service.recall(tag="NOMAD")] == [nomad]
    assert [m.kind for m in service.recall(q="cartão")] == ["decision", "fact"]


def test_blank_query_means_no_query(service: MemoryService) -> None:
    create(service, "fact", "um")
    create(service, "fact", "dois")
    assert len(service.recall(q="   ")) == 2


@pytest.mark.parametrize("limit", [0, 101])
def test_recall_rejects_out_of_range_limit(service: MemoryService, limit: int) -> None:
    with pytest.raises(ValueError):
        service.recall(limit=limit)


def test_summary_block_format(service: MemoryService, clock: FakeClock) -> None:
    create(service, "preference", "Não usar Nomad acima de US$ 1.000 sem confirmar IOF")
    clock.advance(minutes=1)
    create(service, "preference", "Prefere Pix para receber")
    clock.advance(minutes=1)
    create(service, "decision", "Alberdi PJC melhora acima de R$ 25 mil")
    clock.advance(minutes=1)
    create(service, "fact", "ueno cobra IOF no cartão")
    clock.advance(minutes=1)
    create(service, "outcome", "remessa WU CDE->ueno levou 2 dias")

    assert service.summarize() == (
        "Preferências: Prefere Pix para receber; Não usar Nomad acima de US$ 1.000 sem confirmar IOF\n"
        "Decisões: Alberdi PJC melhora acima de R$ 25 mil\n"
        "Fatos: ueno cobra IOF no cartão\n"
        "Resultados: remessa WU CDE->ueno levou 2 dias"
    )


def test_summary_skips_empty_sections_and_is_empty_without_memories(service: MemoryService) -> None:
    assert service.summarize() == ""
    create(service, "fact", "ueno cobra IOF")
    assert service.summarize() == "Fatos: ueno cobra IOF"


def test_summary_limit_is_per_section_and_most_recent_first(service: MemoryService, clock: FakeClock) -> None:
    for i in range(1, 4):
        create(service, "fact", f"fato {i}")
        clock.advance(minutes=1)
    assert service.summarize(limit=2) == "Fatos: fato 3; fato 2"


def test_summary_leaves_out_expired(service: MemoryService, clock: FakeClock) -> None:
    create(service, "outcome", "temporário", ttl_days=1)
    create(service, "outcome", "permanente")
    clock.advance(days=2)
    assert service.summarize() == "Resultados: permanente"


def test_summary_shortens_long_items(service: MemoryService) -> None:
    create(service, "fact", "palavra " * 100)
    line = service.summarize()
    item = line.removeprefix("Fatos: ")
    assert item.endswith("…")
    assert len(item) <= SUMMARY_ITEM_CHARS


def test_summarize_rejects_out_of_range_limit(service: MemoryService) -> None:
    with pytest.raises(ValueError):
        service.summarize(limit=0)
