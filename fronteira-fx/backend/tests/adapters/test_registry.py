from __future__ import annotations

import inspect

import pytest

from fronteira_fx.adapters import registry
from fronteira_fx.adapters.base import AdapterInfo

EXPECTED = {
    "chaco", "alberdi", "bonanza", "norte", "bcp", "nomad", "revolut", "westernunion",
    "maxicambios", "myd", "dolarpy",
    "basa", "familiar",
}


def test_ueno_is_retired() -> None:
    # ueno bank entered resolution by the BCP on 2026-11-03: no longer collected or listed.
    assert "ueno" not in registry.ADAPTERS


def test_registry_has_all_adapters() -> None:
    assert set(registry.ADAPTERS) == EXPECTED and len(registry.ADAPTERS) == 13
    assert list(registry.ADAPTERS) == sorted(EXPECTED)  # deterministic order for the API/collector
    for aid, adapter in registry.ADAPTERS.items():
        assert isinstance(adapter.info, AdapterInfo) and adapter.info.id == aid
        assert inspect.iscoroutinefunction(adapter.fetch)
        assert callable(adapter.parse) and not inspect.iscoroutinefunction(adapter.parse)
        assert adapter.info.url.startswith("https://")
        assert adapter.info.allowed_domains, aid
        assert adapter.info.limitations, aid


def test_get_adapter() -> None:
    assert registry.get_adapter("chaco") is registry.ADAPTERS["chaco"]
    with pytest.raises(KeyError, match="unknown adapter"):
        registry.get_adapter("nope")
    assert len(registry.list_adapters()) == len(EXPECTED)
    assert [a.info.id for a in registry.list_adapters()] == sorted(EXPECTED)
