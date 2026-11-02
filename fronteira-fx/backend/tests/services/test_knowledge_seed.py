"""B19: the bundled knowledge base (`backend/knowledge/*.md`) is seeded into the RAG corpus, idempotently
(one `Document` per file, keyed by path and sha256), at startup and through `python -m fronteira_fx.cli`."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from fronteira_fx.db import make_engine, make_session_factory
from fronteira_fx.main import create_app
from fronteira_fx.models import Document, DocumentChunk
from fronteira_fx.services.rag import default_knowledge_dir, seed_knowledge
from tests.conftest import make_settings


def _write(directory: Path, name: str, title: str, body: str, *, tags: str = "horario, chaco") -> None:
    directory.mkdir(parents=True, exist_ok=True)
    text = f"---\ntitle: {title}\nsource: https://x.example/{name}\ntags: {tags}\n---\n# {title}\n\n{body}\n"
    (directory / name).write_text(text, encoding="utf-8")


def test_seed_knowledge_is_idempotent_and_replaces_changed_files(tmp_path, db):
    _write(tmp_path, "chaco.md", "Cambios Chaco", "Horário de atendimento: 7h30 às 17h.")
    (tmp_path / "sem-front-matter.md").write_text("# Regras do produto\n\nMicroganho conta.\n", encoding="utf-8")
    (tmp_path / "ignorado.txt").write_text("não é markdown", encoding="utf-8")

    assert seed_knowledge(db, tmp_path, data_mode="real") == {"added": 2, "updated": 0, "unchanged": 0, "skipped": 0}
    docs = {d.title: d for d in db.scalars(select(Document))}
    chaco = docs["Cambios Chaco"]
    assert chaco.source == "https://x.example/chaco.md" and chaco.tags == ["horario", "chaco"]
    assert chaco.meta["path"] == "chaco.md" and len(chaco.meta["sha256"]) == 64 and chaco.data_mode == "real"
    assert chaco.text.startswith("# Cambios Chaco") and "---" not in chaco.text
    bare = docs["Regras do produto"]  # title from the first heading, source from the file name
    assert bare.source == "knowledge/sem-front-matter.md" and bare.tags == []

    # nothing changed: nothing rewritten
    assert seed_knowledge(db, tmp_path, data_mode="real") == {"added": 0, "updated": 0, "unchanged": 2, "skipped": 0}
    assert db.scalar(select(func.count(Document.id))) == 2
    assert db.scalar(select(Document.id).where(Document.title == "Cambios Chaco")) == chaco.id

    # a changed file replaces its document and chunks (no orphans, no duplicates)
    _write(tmp_path, "chaco.md", "Cambios Chaco", "Horário novo: 8h às 18h.")
    assert seed_knowledge(db, tmp_path, data_mode="real") == {"added": 0, "updated": 1, "unchanged": 1, "skipped": 0}
    assert db.scalar(select(func.count(Document.id))) == 2
    new_chaco = db.scalar(select(Document).where(Document.title == "Cambios Chaco"))
    assert new_chaco.id != chaco.id and "8h às 18h" in new_chaco.text and "7h30" not in new_chaco.text
    live_ids = set(db.scalars(select(Document.id)))
    assert set(db.scalars(select(DocumentChunk.document_id))) == live_ids

    # modes never mix: a demo corpus is seeded separately and leaves the real one alone
    assert seed_knowledge(db, tmp_path, data_mode="demo") == {"added": 2, "updated": 0, "unchanged": 0, "skipped": 0}
    assert db.scalar(select(func.count(Document.id)).where(Document.data_mode == "real")) == 2


def test_seed_knowledge_skips_unreadable_files_instead_of_aborting(tmp_path, db, caplog):
    """A bad file in the knowledge dir must never take the API down at startup: it is logged and skipped,
    the good ones are still seeded, and an already seeded document is kept when its new version is unreadable."""
    _write(tmp_path, "chaco.md", "Cambios Chaco", "Horário de atendimento: 7h30 às 17h.")
    (tmp_path / "latin1.md").write_bytes(b"# Caf\xe9 da manh\xe3\n\nn\xe3o \xe9 UTF-8\n")

    with caplog.at_level("WARNING", logger="fronteira_fx.rag"):
        assert seed_knowledge(db, tmp_path, data_mode="real") == {"added": 1, "updated": 0, "unchanged": 0, "skipped": 1}
    assert "latin1.md" in caplog.text
    assert [d.title for d in db.scalars(select(Document))] == ["Cambios Chaco"]

    # the previous version stays when the replacement cannot be read
    (tmp_path / "chaco.md").write_bytes(b"# Caf\xe9\n")
    assert seed_knowledge(db, tmp_path, data_mode="real") == {"added": 0, "updated": 0, "unchanged": 0, "skipped": 2}
    assert [d.title for d in db.scalars(select(Document))] == ["Cambios Chaco"]


def test_fresh_app_answers_horario_from_bundled_knowledge():
    settings = make_settings(seed_knowledge=True)
    app = create_app(settings)
    expected = len(list(default_knowledge_dir().glob("*.md")))
    assert expected >= 11
    with TestClient(app) as c:
        hits = c.get("/v1/rag/search", params={"q": "horario"}).json()
        assert hits and all(h["source"] and h["document_id"] for h in hits)
        docs = c.get("/v1/rag/documents").json()
        assert len(docs) == expected and "Cambios Chaco" in {d["title"] for d in docs}
    with TestClient(app) as c:  # second startup: idempotent
        assert len(c.get("/v1/rag/documents").json()) == expected


def test_startup_seed_can_be_disabled():
    with TestClient(create_app(make_settings(seed_knowledge=False))) as c:
        assert c.get("/v1/rag/documents").json() == []


def test_cli_seed_knowledge(tmp_path, capsys):
    from fronteira_fx.cli import main

    kb = tmp_path / "kb"
    _write(kb, "ueno.md", "ueno", "Atendimento das 8h às 17h.")
    url = f"sqlite:///{tmp_path / 'fx.db'}"
    assert main(["seed-knowledge", "--database-url", url, "--dir", str(kb)]) == 0
    out = capsys.readouterr().out
    assert "1 adicionado" in out and str(kb) in out
    assert main(["seed-knowledge", "--database-url", url, "--dir", str(kb)]) == 0
    assert "1 sem mudança" in capsys.readouterr().out
    with make_session_factory(make_engine(url))() as s:
        assert [d.title for d in s.scalars(select(Document))] == ["ueno"]
