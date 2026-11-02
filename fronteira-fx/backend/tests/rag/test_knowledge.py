"""Garante a forma da base de conhecimento semente (backend/knowledge): seções obrigatórias e marcação honesta."""

from __future__ import annotations

from pathlib import Path

from fronteira_fx.rag.service import parse_front_matter

KNOWLEDGE = Path(__file__).resolve().parents[2] / "knowledge"

PROVIDERS = {
    "western-union",
    "ueno",
    "nomad",
    "revolut",
    "cambios-chaco",
    "cambios-alberdi",
    "cambios-norte",
    "cambios-bonanza",
    "bcp",
}
GENERAL = {"glossario", "regras-do-produto"}
PROVIDER_SECTIONS = [
    "## O que oferece",
    "## Modalidades",
    "## Horários",
    "## Tarifas e limites",
    "## Observações de uso",
]


def _files() -> dict[str, str]:
    return {path.stem: path.read_text(encoding="utf-8") for path in sorted(KNOWLEDGE.glob("*.md"))}


def test_seed_set_is_exactly_the_planned_documents():
    assert set(_files()) == PROVIDERS | GENERAL


def test_every_file_has_front_matter_with_title_source_and_tags():
    for stem, raw in _files().items():
        meta, body = parse_front_matter(raw)
        assert meta.get("title"), stem
        assert meta.get("source"), stem
        assert meta.get("tags"), stem
        assert body.lstrip().startswith("# "), stem


def test_provider_documents_have_the_five_required_sections_in_order():
    files = _files()
    for stem in PROVIDERS:
        _, body = parse_front_matter(files[stem])
        positions = [body.find(section) for section in PROVIDER_SECTIONS]
        assert all(pos >= 0 for pos in positions), (stem, positions)
        assert positions == sorted(positions), stem


def test_provider_documents_cite_an_official_url_in_the_tariffs_section():
    files = _files()
    for stem in PROVIDERS:
        _, body = parse_front_matter(files[stem])
        tariffs = body.split("## Tarifas e limites", 1)[1].split("## Observações de uso", 1)[0]
        assert "https://" in tariffs, stem


def test_unknown_facts_are_marked_as_to_be_confirmed():
    files = _files()
    for stem in PROVIDERS:
        assert "a confirmar" in files[stem], stem


def test_glossary_defines_taxa_efetiva_and_iof_as_pending():
    _, body = parse_front_matter(_files()["glossario"])
    assert "## Taxa efetiva" in body
    iof = body.split("## IOF", 1)[1].split("## ", 1)[0]
    assert "a confirmar" in iof


def test_product_rules_match_the_contract_ranking_rules():
    _, body = parse_front_matter(_files()["regras-do-produto"])
    assert "ganho líquido positivo" in body
    assert "0,01" in body
    assert "incompleta" in body
    assert "Não pode: cotação" in body
