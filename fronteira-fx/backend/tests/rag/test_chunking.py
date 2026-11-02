from __future__ import annotations

import pytest

from fronteira_fx.rag.chunking import chunk_text, count_tokens

DOC = """# Guia
Intro do guia.

## Horários
Seg a sex, 9h às 18h.

### Chaco
Filial central.

## Tarifas
Tarifa zero na promoção.
"""


def test_same_input_gives_same_chunks_in_same_order():
    big = "\n".join(f"linha {i} " + " ".join(f"p{i}_{j}" for j in range(12)) for i in range(120))
    first = chunk_text(big + "\n" + DOC)
    second = chunk_text(big + "\n" + DOC)
    assert first == second
    assert [c.index for c in first] == list(range(len(first)))


def test_headings_become_heading_path_metadata():
    chunks = chunk_text(DOC)
    paths = [c.heading_path for c in chunks]
    assert paths[0] == ("Guia",)
    assert ("Guia", "Horários") in paths
    assert ("Guia", "Horários", "Chaco") in paths
    # "### Chaco" sai do caminho quando aparece "## Tarifas" (nível igual ou superior fecha a seção)
    assert ("Guia", "Tarifas") in paths
    assert ("Guia", "Tarifas", "Chaco") not in paths


def test_heading_lines_are_metadata_not_body_text():
    texts = [c.text for c in chunk_text(DOC)]
    assert all("##" not in t and "# Guia" not in t for t in texts)
    assert any("Seg a sex" in t for t in texts)


def test_token_count_is_word_count_and_is_reported():
    chunks = chunk_text("uma duas três\nquatro cinco")
    assert len(chunks) == 1
    assert chunks[0].tokens == count_tokens(chunks[0].text) == 5


def test_windows_respect_max_tokens_and_overlap_whole_lines():
    lines = [" ".join(f"w{i}_{j}" for j in range(10)) for i in range(30)]
    chunks = chunk_text("\n".join(lines), max_tokens=25, overlap_tokens=10)
    assert len(chunks) > 1
    assert all(c.tokens <= 25 for c in chunks)
    # overlap: a primeira linha da janela seguinte já estava na janela anterior
    for previous, following in zip(chunks, chunks[1:], strict=False):
        assert following.text.split("\n")[0] in previous.text.split("\n")
    # linhas nunca são partidas no meio
    assert all(line in lines for c in chunks for line in c.text.split("\n"))


def test_long_line_is_split_by_words_with_word_overlap():
    text = " ".join(f"p{i}" for i in range(250))
    chunks = chunk_text(text, max_tokens=100, overlap_tokens=20)
    assert [c.tokens for c in chunks] == [100, 100, 90]
    assert chunks[0].text.split()[-1] == "p99"
    assert chunks[1].text.split()[0] == "p80"  # 20 palavras de sobreposição


def test_hash_inside_code_fence_is_not_a_heading():
    text = "# Top\n```\n# not a heading\ncode line\n```\nafter"
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0].heading_path == ("Top",)
    assert "# not a heading" in chunks[0].text


def test_plain_text_has_empty_heading_path():
    chunks = chunk_text("Primeira linha.\n\nSegunda linha.")
    assert len(chunks) == 1
    assert chunks[0].heading_path == ()
    assert chunks[0].text == "Primeira linha.\nSegunda linha."


def test_empty_or_blank_text_gives_no_chunks():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  \n") == []


def test_heading_without_body_gives_no_chunk():
    assert chunk_text("# Só título\n## Subtítulo\n") == []


@pytest.mark.parametrize(
    ("max_tokens", "overlap"),
    [(0, 0), (10, -1), (10, 10), (10, 11)],
)
def test_invalid_window_parameters_are_rejected(max_tokens, overlap):
    with pytest.raises(ValueError):
        chunk_text("texto qualquer", max_tokens=max_tokens, overlap_tokens=overlap)
