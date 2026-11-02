"""Settings: environment names and their deprecated aliases (B9)."""

from __future__ import annotations

import logging

from fronteira_fx.config import Settings
from tests.conftest import make_settings


def test_evidence_dir_default_and_kwarg(monkeypatch):
    monkeypatch.delenv("EVIDENCE_DIR", raising=False)
    monkeypatch.delenv("FX_EVIDENCE_DIR", raising=False)
    assert Settings(_env_file=None).evidence_dir == "./var/evidence"
    assert make_settings(evidence_dir="/x").evidence_dir == "/x"


def test_evidence_dir_reads_canonical_env(monkeypatch, caplog):
    monkeypatch.setenv("EVIDENCE_DIR", "/srv/evidence")
    monkeypatch.delenv("FX_EVIDENCE_DIR", raising=False)
    with caplog.at_level(logging.WARNING, logger="fronteira_fx.config"):
        s = Settings(_env_file=None)
    assert s.evidence_dir == "/srv/evidence"
    assert not caplog.records


def test_fx_evidence_dir_alias_still_works_but_warns(monkeypatch, caplog):
    monkeypatch.delenv("EVIDENCE_DIR", raising=False)
    monkeypatch.setenv("FX_EVIDENCE_DIR", "/legacy/evidence")
    with caplog.at_level(logging.WARNING, logger="fronteira_fx.config"):
        s = Settings(_env_file=None)
    assert s.evidence_dir == "/legacy/evidence"
    assert any("FX_EVIDENCE_DIR" in r.getMessage() and "EVIDENCE_DIR" in r.getMessage() for r in caplog.records)


def test_canonical_env_wins_over_alias(monkeypatch):
    monkeypatch.setenv("EVIDENCE_DIR", "/srv/evidence")
    monkeypatch.setenv("FX_EVIDENCE_DIR", "/legacy/evidence")
    assert Settings(_env_file=None).evidence_dir == "/srv/evidence"


def test_placeholder_secrets_from_env_example_are_refused():
    """SEC-05: `.env.example` ships `TROQUE_ESTA_*` so `docker compose config` validates; booting the api or the
    worker with them unchanged would run with publicly known credentials, so Settings refuses them."""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="API_KEY"):
        make_settings(api_key="TROQUE_ESTA_CHAVE")
    with pytest.raises(ValidationError, match="POSTGRES_PASSWORD"):
        make_settings(database_url="postgresql+psycopg://fx:TROQUE_ESTA_SENHA@postgres:5432/fx")
    assert make_settings(api_key="a" * 64).api_key == "a" * 64
    assert make_settings(api_key=None).api_key is None
