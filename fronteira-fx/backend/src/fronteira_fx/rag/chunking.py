"""Divisão determinística de Markdown e texto puro em trechos (chunks) para indexação.

Regras:
1. Títulos Markdown (`#` a `######`) abrem uma seção nova; cada trecho guarda o caminho de títulos
   (`heading_path`, ex.: ("Tarifas", "Western Union")). Linhas dentro de cercas de código não são títulos.
2. Dentro de cada seção, as linhas são empacotadas em janelas de até `max_tokens` (padrão 400).
   Linhas nunca são partidas no meio (tabelas e listas ficam inteiras); uma linha maior que a janela
   é repartida por palavras com sobreposição.
3. Entre janelas consecutivas da mesma seção repete-se o final da anterior, até `overlap_tokens`
   (padrão 60), para que um dado na fronteira não fique sem contexto.

"Token" aqui é aproximado por palavra separada por espaço: não há tokenizador do modelo no projeto.
A função é pura: a mesma entrada produz sempre a mesma saída, na mesma ordem.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

DEFAULT_MAX_TOKENS = 400
DEFAULT_OVERLAP_TOKENS = 60

_HEADING_RE = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*$")
_FENCE_RE = re.compile(r"^[ \t]*(```|~~~)")
_CLOSING_HASHES_RE = re.compile(r"[ \t]+#+$")


@dataclass(frozen=True, slots=True)
class Chunk:
    index: int
    text: str
    heading_path: tuple[str, ...]
    tokens: int


@dataclass(frozen=True, slots=True)
class _Section:
    heading_path: tuple[str, ...]
    lines: tuple[str, ...]


def validate_window(max_tokens: int, overlap_tokens: int) -> None:
    if max_tokens < 1:
        raise ValueError("max_tokens deve ser >= 1")
    if not 0 <= overlap_tokens < max_tokens:
        raise ValueError("overlap_tokens deve estar entre 0 e max_tokens - 1")


def count_tokens(text: str) -> int:
    return len(text.split())


def chunk_text(
    text: str,
    *,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    overlap_tokens: int = DEFAULT_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Divide Markdown ou texto puro em trechos com caminho de títulos."""
    validate_window(max_tokens, overlap_tokens)
    chunks: list[Chunk] = []
    for section in _sections(text):
        for piece in _pack(section.lines, max_tokens, overlap_tokens):
            chunks.append(Chunk(len(chunks), piece, section.heading_path, count_tokens(piece)))
    return chunks


def _sections(text: str) -> list[_Section]:
    sections: list[_Section] = []
    path: list[tuple[int, str]] = []  # stack of (level, title)
    current_path: tuple[str, ...] = ()
    lines: list[str] = []
    fence: str | None = None

    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.rstrip()
        stripped = line.strip()

        if fence is not None:
            # dentro de código: preserva a linha (com indentação) e só fecha com a mesma cerca
            if stripped:
                lines.append(line)
            if stripped.startswith(fence):
                fence = None
            continue

        fence_match = _FENCE_RE.match(line)
        if fence_match:
            fence = fence_match.group(1)
            if stripped:
                lines.append(line)
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            if lines:
                sections.append(_Section(current_path, tuple(lines)))
                lines = []
            level = len(heading.group(1))
            title = _CLOSING_HASHES_RE.sub("", heading.group(2)).strip()
            path = [(lvl, name) for lvl, name in path if lvl < level] + [(level, title)]
            current_path = tuple(name for _, name in path)
            continue

        if stripped:
            lines.append(stripped)

    if lines:
        sections.append(_Section(current_path, tuple(lines)))
    return sections


def _pack(lines: tuple[str, ...], max_tokens: int, overlap_tokens: int) -> list[str]:
    units: list[str] = []
    for line in lines:
        words = line.split()
        if len(words) <= max_tokens:
            units.append(line)
        else:
            units.extend(" ".join(window) for window in _word_windows(words, max_tokens, overlap_tokens))

    pieces: list[str] = []
    current: list[str] = []
    current_tokens = 0
    for unit in units:
        size = count_tokens(unit)
        if current and current_tokens + size > max_tokens:
            pieces.append("\n".join(current))
            current, current_tokens = _overlap_tail(current, overlap_tokens, size, max_tokens)
        current.append(unit)
        current_tokens += size
    if current:
        pieces.append("\n".join(current))
    return pieces


def _word_windows(words: list[str], max_tokens: int, overlap_tokens: int) -> list[list[str]]:
    step = max_tokens - overlap_tokens
    windows: list[list[str]] = []
    start = 0
    while True:
        windows.append(words[start : start + max_tokens])
        if start + max_tokens >= len(words):
            return windows
        start += step


def _overlap_tail(units: list[str], overlap_tokens: int, incoming: int, max_tokens: int) -> tuple[list[str], int]:
    """Últimas linhas da janela anterior (até `overlap_tokens`) que cabem junto da linha que chega."""
    tail: list[str] = []
    total = 0
    for unit in reversed(units):
        size = count_tokens(unit)
        if total + size > overlap_tokens:
            break
        tail.insert(0, unit)
        total += size
    while tail and total + incoming > max_tokens:
        total -= count_tokens(tail.pop(0))
    return tail, total
