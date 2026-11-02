"""Normalização de texto compartilhada pelo RAG: minúsculas, sem acentos, tokens e stopwords.

Sem dependências externas. A mesma normalização é usada na indexação, na busca por palavras-chave,
no hashing de embeddings e no filtro por tag, para que "Horário", "horário" e "horarios" sejam iguais.
"""

from __future__ import annotations

import re
import unicodedata

_TOKEN_RE = re.compile(r"[^\W_]+")

# Stopwords mínimas, já sem acentos (pt-BR e en). Só evitam que palavras de ligação dominem o ranking.
STOPWORDS: frozenset[str] = frozenset(
    {
        "a", "ao", "aos", "as", "com", "como", "da", "das", "de", "do", "dos", "e", "em", "na", "nas",
        "no", "nos", "o", "os", "ou", "para", "pra", "pela", "pelo", "por", "qual", "quais", "quando",
        "que", "quanto", "quantos", "se", "sem", "um", "uma", "umas", "uns", "ser", "the", "of", "and",
        "to", "in", "is", "what", "how", "on", "for",
    }
)  # fmt: skip


def fold(text: str) -> str:
    """Minúsculas e sem acentos: 'Horário' -> 'horario'."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).casefold()


def stem(token: str) -> str:
    """Remoção mínima de plural: 'horarios' -> 'horario', 'tarifas' -> 'tarifa' (sem stemmer completo)."""
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str, *, drop_stopwords: bool = True) -> list[str]:
    """Tokens normalizados (sem acento, sem plural simples, sem stopwords se pedido)."""
    tokens: list[str] = []
    for raw in _TOKEN_RE.findall(fold(text)):
        if drop_stopwords and raw in STOPWORDS:
            continue
        tokens.append(stem(raw))
    return tokens


def normalize_tag(tag: str) -> str:
    """Chave de comparação de tags: sem acento, minúsculas, espaços viram hífen."""
    return "-".join(fold(tag).split())
