"""Registry of provider adapters. The collector and the API look adapters up here.

ueno bank is out: it entered resolution by the Banco Central del Paraguay on 2026-11-03. Its adapter module stays
only as history (and for the demo data until that is migrated); it is no longer collected or listed.
"""
from __future__ import annotations

from . import alberdi, bcp, bonanza, chaco, dolarpy, maxicambios, myd, nomad, norte, revolut, westernunion
from .base import Adapter

_ALL: tuple[Adapter, ...] = (
    chaco.adapter,
    alberdi.adapter,
    bonanza.adapter,
    norte.adapter,
    bcp.adapter,
    nomad.adapter,
    revolut.adapter,
    westernunion.adapter,
    maxicambios.adapter,
    myd.adapter,
    dolarpy.adapter,
)

# Sorted by id: the API and the collector enumerate sources in this order, so it must not depend on import order.
ADAPTERS: dict[str, Adapter] = {a.info.id: a for a in sorted(_ALL, key=lambda a: a.info.id)}


def get_adapter(adapter_id: str) -> Adapter:
    try:
        return ADAPTERS[adapter_id]
    except KeyError:
        known = ", ".join(sorted(ADAPTERS))
        raise KeyError(f"unknown adapter {adapter_id!r}; known: {known}") from None


def list_adapters() -> list[Adapter]:
    return list(ADAPTERS.values())
