"""docs/api-contract.md é a fonte da verdade: as cidades que ele lista precisam ser as do enum `City` do backend.

Offline: lê só o arquivo de contrato e o `Literal` de `schemas.City`.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from fronteira_fx.schemas import City

CONTRACT = Path(__file__).resolve().parents[2] / "docs" / "api-contract.md"


def _lines() -> list[str]:
    return CONTRACT.read_text(encoding="utf-8").splitlines()


def test_city_enum_in_contract_matches_backend() -> None:
    enum_lines = [line for line in _lines() if line.startswith("- `City`:")]
    assert len(enum_lines) == 1, "o contrato deve ter exatamente uma linha do enum City"
    documented = set(re.findall(r"`([A-Z]{3})`", enum_lines[0]))
    assert documented == set(get_args(City)), f"contrato lista {sorted(documented)}, backend {get_args(City)}"


def test_every_city_field_in_contract_lists_enc() -> None:
    """Qualquer linha de contrato que enumere cidades de um campo `city`/`City` precisa conter ENC."""
    offenders = [
        f"linha {n}: {line.strip()}"
        for n, line in enumerate(_lines(), start=1)
        if re.search(r'`City`|"city"', line)
        and re.search(r"\bCDE\b", line)
        and re.search(r"\bPJC\b", line)
        and not re.search(r"\bENC\b", line)
    ]
    assert not offenders, "\n".join(offenders)
