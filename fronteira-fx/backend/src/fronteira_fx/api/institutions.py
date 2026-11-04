"""Cadastro de instituições (tag `institutions`): dados versionados em `data/institutions.json`, sem banco.

O prefixo `/v1` vem do `v1_router`. A rota não depende de `data_mode`: o cadastro é o mesmo em qualquer modo.
"""

from __future__ import annotations

from fastapi import APIRouter

from fronteira_fx.services.institutions import Institution, load_institutions

router = APIRouter(tags=["institutions"])


@router.get(
    "/institutions",
    operation_id="list_institutions",
    summary="Institutions where accounts can be opened, with the source of each figure",
)
def list_institutions() -> list[Institution]:
    return list(load_institutions().values())
