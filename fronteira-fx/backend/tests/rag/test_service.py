from __future__ import annotations

from pathlib import Path

import pytest

from fronteira_fx.rag.embeddings import EMBEDDING_DIM, HashEmbedder
from fronteira_fx.rag.service import RagService, parse_front_matter
from fronteira_fx.rag.store import InMemoryStore

KNOWLEDGE = Path(__file__).resolve().parents[2] / "knowledge"


class CountingEmbedder:
    """Embedder de teste que conta chamadas (para provar que o seed pula arquivos sem mudança)."""

    def __init__(self, dimensions: int = EMBEDDING_DIM) -> None:
        self._inner = HashEmbedder(dimensions)
        self.name = self._inner.name
        self.dimensions = dimensions
        self.calls = 0

    def embed(self, texts):
        self.calls += 1
        return self._inner.embed(texts)


@pytest.fixture
def service() -> RagService:
    return RagService(InMemoryStore(), HashEmbedder())


@pytest.fixture
def seeded() -> RagService:
    svc = RagService(InMemoryStore(), HashEmbedder())
    svc.seed(KNOWLEDGE)
    return svc


# --- add_document and validation ---------------------------------------------------------------


def test_add_document_returns_id_and_chunk_count(service: RagService):
    doc_id, chunks = service.add_document("Doc", "Primeiro parágrafo.\n\nSegundo.", "manual", ["a"])
    assert doc_id
    assert chunks >= 1
    doc = service.get_document(doc_id)
    assert doc is not None
    assert doc.chunk_count == chunks
    assert doc.tags == ("a",)
    assert [d.id for d in service.list_documents()] == [doc_id]


def test_add_document_with_same_id_replaces_it(service: RagService):
    service.add_document("Antigo", "texto antigo", "s", document_id="fixo")
    doc_id, _ = service.add_document("Novo", "texto novo " * 3, "s", document_id="fixo")
    assert doc_id == "fixo"
    assert [d.title for d in service.list_documents()] == ["Novo"]


@pytest.mark.parametrize(
    ("title", "text", "kwargs", "message"),
    [
        ("", "texto", {}, "title"),
        ("   ", "texto", {}, "title"),
        ("T", "   ", {}, "text"),
        ("T" * 301, "texto", {}, "title"),
        ("T", "texto", {"tags": ["x" * 41]}, "tag"),
        ("T", "texto", {"tags": [f"t{i}" for i in range(21)]}, "tags"),
        ("T", "texto", {"document_id": "x" * 65}, "document_id"),
    ],
)
def test_add_document_validates_input(service: RagService, title, text, kwargs, message):
    with pytest.raises(ValueError, match=message):
        service.add_document(title, text, "s", **kwargs)


def test_tags_are_trimmed_and_deduplicated_by_normalised_key(service: RagService):
    doc_id, _ = service.add_document("T", "texto", "s", ["Pix", "pix", "  ", "PIX ", "Remessa"])
    doc = service.get_document(doc_id)
    assert doc is not None
    assert doc.tags == ("Pix", "Remessa")


def test_metadata_is_stored_with_the_document(service: RagService):
    doc_id, _ = service.add_document("T", "texto", "s", metadata={"origem": "teste"})
    doc = service.get_document(doc_id)
    assert doc is not None
    assert dict(doc.metadata) == {"origem": "teste"}


def test_delete_document(service: RagService):
    doc_id, _ = service.add_document("T", "texto", "s")
    assert service.delete_document(doc_id) is True
    assert service.list_documents() == []


# --- search ------------------------------------------------------------------------------------------


def test_search_finds_the_right_document_for_taxa_efetiva(seeded: RagService):
    hits = seeded.search("taxa efetiva", k=3)
    assert hits
    assert hits[0].title == "Glossário do câmbio"
    assert hits[0].source == "interno (glossário do produto)"


def test_search_finds_the_right_document_for_horario_chaco(seeded: RagService):
    hits = seeded.search("horário Chaco", k=3)
    assert hits
    assert hits[0].title == "Cambios Chaco"
    assert hits[0].source == "https://www.cambioschaco.com.py/"
    assert hits[0].score == pytest.approx(1.0)


def test_search_result_shape_matches_contract(seeded: RagService):
    hit = seeded.search("tarifa Western Union", k=1)[0]
    assert hit.document_id == "seed-western-union"
    assert hit.chunk_id.startswith("seed-western-union#")
    assert 0 < hit.score <= 1
    assert len(hit.snippet) <= 300
    assert isinstance(hit.tags, tuple) and "remessa" in hit.tags


def test_search_respects_k(seeded: RagService):
    assert len(seeded.search("horário", k=2)) == 2


def test_search_tag_filter_only_returns_tagged_documents(seeded: RagService):
    hits = seeded.search("horário filial", k=10, tag="pjc")
    assert hits
    assert all("pjc" in hit.tags for hit in hits)
    assert {hit.title for hit in hits} <= {"Cambios Chaco", "Cambios Norte"}


def test_search_with_unknown_tag_returns_nothing(seeded: RagService):
    assert seeded.search("horário", tag="nao-existe") == []


def test_search_on_empty_store_and_empty_query(service: RagService):
    assert service.search("qualquer coisa") == []
    service.add_document("T", "texto", "s")
    assert service.search("   ") == []


def test_search_on_a_document_added_by_hand(service: RagService):
    doc_id, _ = service.add_document("Remessa Paraguai", "O prazo de entrega é de 0 a 4 dias úteis.", "manual")
    hits = service.search("prazo de entrega", k=1)
    assert hits[0].document_id == doc_id
    assert "prazo" in hits[0].snippet


# --- seed --------------------------------------------------------------------------------------------


def test_seed_loads_every_knowledge_file(seeded: RagService):
    ids = {d.id for d in seeded.list_documents()}
    expected = {f"seed-{path.stem}" for path in KNOWLEDGE.glob("*.md")}
    assert ids == expected
    assert len(ids) == 11


def test_seed_is_idempotent_and_skips_unchanged_files():
    embedder = CountingEmbedder()
    svc = RagService(InMemoryStore(), embedder)
    first = svc.seed(KNOWLEDGE)
    assert all(result.changed for result in first)
    calls_after_first = embedder.calls

    second = svc.seed(KNOWLEDGE)
    assert not any(result.changed for result in second)
    assert embedder.calls == calls_after_first  # nenhum arquivo foi reindexado
    assert len(svc.list_documents()) == len(first)


def test_seed_reindexes_only_the_changed_file(tmp_path: Path):
    (tmp_path / "a.md").write_text("# A\nconteúdo a\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\nconteúdo b\n", encoding="utf-8")
    embedder = CountingEmbedder()
    svc = RagService(InMemoryStore(), embedder)
    svc.seed(tmp_path)

    (tmp_path / "b.md").write_text("# B\nconteúdo b mudado\n", encoding="utf-8")
    results = {r.document_id: r.changed for r in svc.seed(tmp_path)}
    assert results == {"seed-a": False, "seed-b": True}


def test_seed_switching_embedder_reindexes_everything(tmp_path: Path):
    (tmp_path / "a.md").write_text("# A\nconteúdo a\n", encoding="utf-8")
    store = InMemoryStore()
    RagService(store, HashEmbedder(EMBEDDING_DIM)).seed(tmp_path)
    new_service = RagService(store, HashEmbedder(128))
    results = new_service.seed(tmp_path)
    assert [r.changed for r in results] == [True]
    # os vetores antigos (outro modelo) não entram na busca vetorial, mas a nova busca funciona
    assert [h.document_id for h in new_service.search("conteúdo", k=1)] == ["seed-a"]


def test_reindex_recomputes_every_document(service: RagService):
    service.add_document("A", "texto a", "s")
    service.add_document("B", "texto b", "s")
    assert service.reindex() == 2
    assert len(service.list_documents()) == 2


def test_seed_uses_front_matter_title_source_and_tags(tmp_path: Path):
    (tmp_path / "fonte.md").write_text(
        "---\ntitle: Título vindo do cabeçalho\nsource: https://exemplo.test/pagina\ntags: pix, remessa\n---\n"
        "# Outro título\ncorpo do documento\n",
        encoding="utf-8",
    )
    svc = RagService(InMemoryStore(), HashEmbedder())
    svc.seed(tmp_path)
    doc = svc.get_document("seed-fonte")
    assert doc is not None
    assert doc.title == "Título vindo do cabeçalho"
    assert doc.source == "https://exemplo.test/pagina"
    assert doc.tags == ("pix", "remessa")
    assert "corpo do documento" in doc.text
    assert "title:" not in doc.text


def test_seed_without_front_matter_uses_first_heading_and_file_name(tmp_path: Path):
    (tmp_path / "sem-cabecalho.md").write_text("# Título pelo H1\ntexto\n", encoding="utf-8")
    svc = RagService(InMemoryStore(), HashEmbedder())
    svc.seed(tmp_path)
    doc = svc.get_document("seed-sem-cabecalho")
    assert doc is not None
    assert doc.title == "Título pelo H1"
    assert doc.source == "knowledge/sem-cabecalho.md"
    assert doc.tags == ()


def test_seed_missing_directory_raises(tmp_path: Path, service: RagService):
    with pytest.raises(FileNotFoundError):
        service.seed(tmp_path / "nao-existe")


def test_parse_front_matter_variants():
    assert parse_front_matter("# Só corpo") == ({}, "# Só corpo")
    meta, body = parse_front_matter("---\nTitle: X\nbad line\n---\nCorpo")
    assert meta == {"title": "X"}
    assert body == "Corpo"
    # bloco sem fechamento não é front matter
    assert parse_front_matter("---\ntitle: X\nCorpo")[0] == {}


GOLDEN = [
    ("taxa efetiva", "seed-glossario"),
    ("horário Chaco", "seed-cambios-chaco"),
    ("tarifa Western Union", "seed-western-union"),
    ("dólar Bonanza horário", "seed-cambios-bonanza"),
    ("IOF", "seed-glossario"),
    ("ROI retorno sobre capital", "seed-glossario"),
    ("certificado TLS Norte", "seed-cambios-norte"),
    ("Revolut markup fim de semana", "seed-revolut"),
    ("cotação de referência Banco Central", "seed-bcp"),
    ("Alberdi Villa Morra", "seed-cambios-alberdi"),
    ("ueno en efectivo balcão", "seed-ueno"),
    ("Nomad spread", "seed-nomad"),
    ("ciclo BRL PYG USD", "seed-glossario"),
    ("microganho digital ranking", "seed-regras-do-produto"),
]


@pytest.mark.parametrize(("query", "expected"), GOLDEN)
def test_golden_queries_hit_expected_document_in_top_3(seeded: RagService, query: str, expected: str):
    """Regressão de qualidade: consultas escritas depois dos documentos (não é avaliação independente)."""
    assert expected in [hit.document_id for hit in seeded.search(query, k=3)]
