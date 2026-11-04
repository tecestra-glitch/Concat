"""Serverless mode: settings, engine pooling for the Supabase transaction pooler, and the SSE `retry:` value."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.pool import NullPool, QueuePool

import fronteira_fx.db as db_module
from fronteira_fx.config import Settings
from fronteira_fx.main import create_app
from tests.conftest import make_settings

PG_URL = "postgresql+psycopg://postgres.ref:not-a-real-password@pooler.example:6543/postgres?sslmode=require"


def test_defaults_keep_the_long_running_behaviour(monkeypatch):
    for name in ("FX_SERVERLESS", "SERVERLESS", "CRON_SECRET", "STREAM_RETRY_MS", "COLLECT_BUDGET_S"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert s.serverless is False
    assert s.cron_secret is None and s.cron_secret_enabled is False
    assert s.stream_retry_ms == 1000
    assert s.collect_budget_s == 45


def test_environment_names(monkeypatch):
    monkeypatch.setenv("FX_SERVERLESS", "1")
    monkeypatch.setenv("CRON_SECRET", "segredo-de-teste-nao-usar")
    monkeypatch.setenv("STREAM_RETRY_MS", "30000")
    s = Settings(_env_file=None)
    assert s.serverless is True
    assert s.cron_secret == "segredo-de-teste-nao-usar" and s.cron_secret_enabled is True
    assert s.stream_retry_ms == 30000


def test_blank_cron_secret_counts_as_unset():
    assert make_settings(cron_secret="   ").cron_secret_enabled is False


def test_placeholder_cron_secret_is_refused():
    with pytest.raises(ValidationError, match="CRON_SECRET"):
        make_settings(cron_secret="TROQUE_ESTE_SEGREDO")


def _capture_create_engine(monkeypatch):
    captured = {}

    def fake(url, **kwargs):
        captured.update(kwargs)
        captured["url"] = url
        return object()

    monkeypatch.setattr(db_module, "create_engine", fake)
    return captured


def test_serverless_postgres_uses_nullpool_and_no_prepared_statements(monkeypatch):
    captured = _capture_create_engine(monkeypatch)
    db_module.make_engine(PG_URL, serverless=True)
    assert captured["poolclass"] is NullPool
    assert captured["connect_args"] == {"prepare_threshold": None}


def test_non_serverless_postgres_is_unchanged(monkeypatch):
    captured = _capture_create_engine(monkeypatch)
    db_module.make_engine(PG_URL, serverless=False)
    assert "poolclass" not in captured and "connect_args" not in captured


def test_serverless_sqlite_is_unchanged(tmp_path):
    engine = db_module.make_engine(f"sqlite:///{tmp_path}/fx.db", serverless=True)
    try:
        assert not isinstance(engine.pool, NullPool)
    finally:
        engine.dispose()


def test_real_engine_with_serverless_flag_uses_nullpool():
    engine = db_module.make_engine(PG_URL, serverless=True)
    try:
        assert isinstance(engine.pool, NullPool)
    finally:
        engine.dispose()
    plain = db_module.make_engine(PG_URL)
    try:
        assert isinstance(plain.pool, QueuePool)
    finally:
        plain.dispose()


@pytest.mark.parametrize("retry_ms", [1000, 30000])
def test_sse_first_event_carries_configured_retry(retry_ms):
    app = create_app(make_settings(stream_retry_ms=retry_ms))
    with TestClient(app) as client, client.stream("GET", "/v1/stream") as r:
        head = next(r.iter_text())
    assert f"retry: {retry_ms}" in head
