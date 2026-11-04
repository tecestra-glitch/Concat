"""Chaves de API (OXR_APP_ID, FRED_API_KEY) vão na query string. Nenhuma delas pode aparecer nos logs nem na repr
das configurações, mesmo com o httpx registrando a URL completa em INFO (transporte mockado, sem rede)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import httpx
import respx

from fronteira_fx.market import macro
from fronteira_fx.market import reference as ref
from fronteira_fx.market.service import MarketPoller

from .test_regional_block import Clock, keyed_settings

T0 = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
OXR_KEY = "chave-oxr-SECRETA-123"
FRED_KEY = "fredkey-SECRETA-456abcdefghijklmnopqrstuv"


@respx.mock
async def test_api_keys_never_reach_the_logs(market_factory, caplog):
    caplog.set_level(logging.INFO)  # o pior caso: o httpx loga a URL em INFO
    respx.get(url__startswith=ref.OXR_URL).mock(return_value=httpx.Response(500))
    respx.get(url__startswith=macro.FRED_URL).mock(return_value=httpx.Response(500))
    settings = keyed_settings(oxr_app_id=OXR_KEY, fred_api_key=FRED_KEY)
    assert OXR_KEY not in repr(settings) and FRED_KEY not in repr(settings)

    clock = Clock(T0)
    poller = MarketPoller(market_factory, settings, clock=clock)
    for source in poller.scheduler.sources():
        if source.source_id not in {ref.OXR_SOURCE, macro.FRED_SOURCE}:
            poller.scheduler.remove_source(source.source_id)
    try:
        results = await poller.run_once()
        clock.now = T0 + timedelta(hours=1)
        results += await poller.run_once()
    finally:
        await poller.aclose()

    assert {r.source_id for r in results} == {ref.OXR_SOURCE, macro.FRED_SOURCE}
    assert len(respx.calls) >= 2
    assert "HTTP Request" in caplog.text  # o httpx de fato registrou as requisições...
    assert OXR_KEY not in caplog.text and FRED_KEY not in caplog.text  # ...e a chave saiu mascarada
    assert all(OXR_KEY not in (r.error or "") and FRED_KEY not in (r.error or "") for r in results)
