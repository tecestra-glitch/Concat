"""Rotas /v1/connections com TestClient e corretora simulada (httpx.MockTransport). Nenhuma chamada de rede real."""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Iterator
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from fronteira_fx.config import Settings
from fronteira_fx.main import create_app
from fronteira_fx.models import Connection, StatementEntry
from tests.conftest import make_settings
from tests.connections.test_vault_and_exchanges import API_KEY, API_SECRET, READ_ONLY, _binance_transport

SERVICE_KEY = "svc-test-key-0123456789abcdef"
VAULT_KEY = base64.b64encode(bytes(range(32))).decode()
H = {"X-API-Key": SERVICE_KEY}


def _app(**overrides):
    settings = make_settings(api_key=SERVICE_KEY, FX_CONNECTIONS_KEY=VAULT_KEY, **overrides)
    app = create_app(settings)
    app.state.exchange_transport = _binance_transport(READ_ONLY)
    return app


@pytest.fixture
def api(request) -> Iterator[tuple[TestClient, object]]:
    app = _app()
    with TestClient(app) as client:
        yield client, app


def _readonly_body(**extra):
    body = {
        "institution": "binance",
        "label": "Binance leitura",
        "kind": "readonly_key",
        "api_key": API_KEY,
        "api_secret": API_SECRET,
    }
    body.update(extra)
    return body


def _no_secret_in(text: str) -> None:
    assert API_KEY not in text
    assert API_SECRET not in text


def _make_account(client: TestClient, currency: str = "BRL") -> str:
    r = client.post(
        "/v1/accounts",
        headers=H,
        json={"institution": "Bradesco", "label": "Conta manual", "currency": currency, "kind": "bank"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ---------- acesso ----------


def test_routes_refused_without_api_key_configured():
    app = create_app(make_settings(api_key=None, FX_CONNECTIONS_KEY=VAULT_KEY))
    with TestClient(app) as client:
        r = client.get("/v1/connections")
    assert r.status_code == 503
    assert "API_KEY" in r.json()["detail"]


def test_routes_require_api_key(api):
    client, _ = api
    assert client.get("/v1/connections").status_code == 401
    assert client.get("/v1/connections", headers={"X-API-Key": "errada"}).status_code == 401
    assert client.get("/v1/connections", headers={"Authorization": f"Bearer {SERVICE_KEY}"}).status_code == 200


def test_vault_off_without_connections_key():
    app = create_app(make_settings(api_key=SERVICE_KEY, FX_CONNECTIONS_KEY=None))
    app.state.exchange_transport = _binance_transport(READ_ONLY)
    with TestClient(app) as client:
        assert client.get("/v1/connections", headers=H).status_code == 200
        r = client.post("/v1/connections", headers=H, json=_readonly_body())
        assert r.status_code == 503
        assert "FX_CONNECTIONS_KEY" in r.json()["detail"]
        r = client.post("/v1/connections/validate-key", headers=H, json=_readonly_body())
        assert r.status_code == 503


def test_placeholder_connections_key_refused():
    with pytest.raises(ValidationError, match="placeholder"):
        Settings(_env_file=None, database_url="sqlite://", FX_CONNECTIONS_KEY="TROQUE_ESTA_CHAVE")


# ---------- chave ----------


def test_create_readonly_stores_encrypted_and_returns_no_secret(api, caplog):
    client, app = api
    caplog.set_level(logging.DEBUG)
    r = client.post("/v1/connections", headers=H, json=_readonly_body())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["key_hint"] == API_KEY[-4:]
    assert body["status"] == "active" and body["kind"] == "readonly_key"
    assert [(b["asset"], Decimal(b["free"]), Decimal(b["locked"])) for b in body["balances"]] == [
        ("USDT", Decimal("120.5"), Decimal(0)),
        ("BRL", Decimal(10), Decimal("2.5")),
    ]
    _no_secret_in(r.text)
    _no_secret_in(caplog.text)

    with app.state.session_factory() as db:
        row = db.scalars(select(Connection)).one()
        assert row.ciphertext and API_SECRET not in row.ciphertext and API_KEY not in row.ciphertext

    listed = client.get("/v1/connections", headers=H)
    assert listed.status_code == 200
    _no_secret_in(listed.text)


def test_dangerous_key_refused_without_storing(api, caplog):
    client, app = api
    client.app.state.exchange_transport = _binance_transport({**READ_ONLY, "enableWithdrawals": True})
    caplog.set_level(logging.DEBUG)
    r = client.post("/v1/connections", headers=H, json=_readonly_body())
    assert r.status_code == 422
    assert "enableWithdrawals" in r.json()["detail"]
    _no_secret_in(r.text)
    _no_secret_in(caplog.text)
    assert client.get("/v1/connections", headers=H).json() == []


def test_kraken_refused_by_default(api):
    client, _ = api
    r = client.post("/v1/connections", headers=H, json=_readonly_body(institution="kraken"))
    assert r.status_code == 422
    assert "Kraken" in r.json()["detail"]


def test_validation_error_never_echoes_secret(api):
    client, _ = api
    r = client.post("/v1/connections", headers=H, json=_readonly_body(institution="ruim com espaço"))
    assert r.status_code == 422
    _no_secret_in(r.text)


def test_validate_key_endpoint_reports_without_storing(api):
    client, _ = api
    client.app.state.exchange_transport = _binance_transport({**READ_ONLY, "enableMargin": True})
    r = client.post(
        "/v1/connections/validate-key",
        headers=H,
        json={"institution": "binance", "api_key": API_KEY, "api_secret": API_SECRET},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is False
    assert r.json()["flags"]["enableMargin"] is True
    _no_secret_in(r.text)
    assert client.get("/v1/connections", headers=H).json() == []


def test_sync_reruns_permissions_and_marks_error_when_key_becomes_dangerous(api):
    client, _ = api
    created = client.post("/v1/connections", headers=H, json=_readonly_body()).json()
    cid = created["id"]

    client.app.state.exchange_transport = _binance_transport({**READ_ONLY, "enableFutures": True})
    r = client.post(f"/v1/connections/{cid}/sync", headers=H)
    assert r.status_code == 200
    assert r.json()["status"] == "error"
    assert "enableFutures" in r.json()["last_error"]
    _no_secret_in(r.text)

    client.app.state.exchange_transport = _binance_transport(READ_ONLY)
    r = client.post(f"/v1/connections/{cid}/sync", headers=H)
    assert r.json()["status"] == "active" and r.json()["last_error"] is None


def test_sync_with_wrong_master_key_is_503(api):
    client, app = api
    cid = client.post("/v1/connections", headers=H, json=_readonly_body()).json()["id"]
    app.state.settings.connections_key = base64.b64encode(bytes(range(1, 33))).decode()
    r = client.post(f"/v1/connections/{cid}/sync", headers=H)
    assert r.status_code == 503
    _no_secret_in(r.text)


def test_delete_removes_connection_and_entries_keeps_account(api):
    client, app = api
    account_id = _make_account(client)
    sid = client.post(
        "/v1/connections",
        headers=H,
        json={"institution": "banco-x", "label": "Extrato", "kind": "statement", "account_id": account_id},
    ).json()["id"]
    csv = "Data,Descrição,Valor,Moeda\n2026-11-03,pix,10,BRL\n"
    r = client.post(
        f"/v1/connections/{sid}/statement",
        headers=H,
        json={"format": "csv", "content": csv, "mapping": {"date": "Data", "description": "Descrição", "amount": "Valor", "currency": "Moeda"}},
    )
    assert r.status_code == 200, r.text
    assert client.delete(f"/v1/connections/{sid}", headers=H).status_code == 204
    assert client.delete(f"/v1/connections/{sid}", headers=H).status_code == 404
    with app.state.session_factory() as db:
        assert db.scalars(select(StatementEntry)).all() == []
    accounts = client.get("/v1/accounts").json()
    assert any(a["id"] == account_id for a in accounts)


# ---------- extrato ----------


CSV_BODY = {
    "format": "csv",
    "content": "Data,Descrição,Valor,Moeda\n2026-11-03,PIX recebido,\"1.200,50\",BRL\n2026-11-04,Tarifa,-12,BRL\n",
    "mapping": {"date": "Data", "description": "Descrição", "amount": "Valor", "currency": "Moeda"},
}


def _statement_connection(client: TestClient, account_id: str | None) -> str:
    body = {"institution": "banco-x", "label": "Extrato", "kind": "statement"}
    if account_id:
        body["account_id"] = account_id
    r = client.post("/v1/connections", headers=H, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_csv_import_is_idempotent_and_updates_manual_balance(api):
    client, _ = api
    account_id = _make_account(client)
    cid = _statement_connection(client, account_id)

    first = client.post(f"/v1/connections/{cid}/statement", headers=H, json=CSV_BODY)
    assert first.status_code == 200, first.text
    assert first.json()["imported"] == 2 and first.json()["duplicates"] == 0
    assert Decimal(first.json()["balance_delta"]) == Decimal("1188.50")
    assert Decimal(first.json()["account_balance_free"]) == Decimal("1188.50")

    again = client.post(f"/v1/connections/{cid}/statement", headers=H, json=CSV_BODY)
    assert again.json()["imported"] == 0 and again.json()["duplicates"] == 2
    accounts = {a["id"]: a for a in client.get("/v1/accounts").json()}
    assert Decimal(accounts[account_id]["balance_free"]) == Decimal("1188.50")


def test_currency_mismatch_with_account_refused_nothing_written(api):
    client, app = api
    account_id = _make_account(client, currency="USD")
    cid = _statement_connection(client, account_id)
    r = client.post(f"/v1/connections/{cid}/statement", headers=H, json=CSV_BODY)
    assert r.status_code == 422
    assert "BRL" in r.json()["detail"]
    with app.state.session_factory() as db:
        assert db.scalars(select(StatementEntry)).all() == []


def test_ofx_import_via_route(api):
    client, _ = api
    cid = _statement_connection(client, None)
    ofx = (
        "<OFX><CURDEF>USD<BANKTRANLIST><STMTTRN><DTPOSTED>20261103<TRNAMT>5.00<FITID>abc<NAME>x"
        "</STMTTRN></BANKTRANLIST></OFX>"
    )
    r = client.post(f"/v1/connections/{cid}/statement", headers=H, json={"format": "ofx", "content": ofx})
    assert r.status_code == 200, r.text
    assert r.json()["imported"] == 1 and r.json()["account_balance_free"] is None


def test_invalid_statement_returns_line_errors(api):
    client, _ = api
    cid = _statement_connection(client, None)
    bad = {**CSV_BODY, "content": "Data,Descrição,Valor,Moeda\n2026-99-01,x,1,BRL\n"}
    r = client.post(f"/v1/connections/{cid}/statement", headers=H, json=bad)
    assert r.status_code == 422
    assert any("linha 2" in e for e in r.json()["detail"])


def test_csv_without_mapping_refused(api):
    client, _ = api
    cid = _statement_connection(client, None)
    r = client.post(f"/v1/connections/{cid}/statement", headers=H, json={"format": "csv", "content": "a,b\n1,2\n"})
    assert r.status_code == 422


def test_statement_size_limit_refused_without_echo(api):
    client, _ = api
    cid = _statement_connection(client, None)
    huge = "x" * (512 * 1024 + 1)
    r = client.post(f"/v1/connections/{cid}/statement", headers=H, json={"format": "ofx", "content": huge})
    assert r.status_code == 422
    assert len(r.text) < 2000


def test_statement_import_refused_on_readonly_connection(api):
    client, _ = api
    cid = client.post("/v1/connections", headers=H, json=_readonly_body()).json()["id"]
    r = client.post(f"/v1/connections/{cid}/statement", headers=H, json={"format": "ofx", "content": "<OFX>"})
    assert r.status_code == 422


# ---------- Open Finance ----------


def test_openfinance_not_configured_by_default(api):
    client, _ = api
    r = client.post("/v1/connections/openfinance/consent", headers=H)
    assert r.status_code == 503
    assert "não configurado" in r.json()["detail"]
    assert "agregador" in r.json()["detail"]


def test_openfinance_provider_without_credentials_still_not_configured():
    app = _app(FX_OPENFINANCE_PROVIDER="pluggy")
    with TestClient(app) as client:
        r = client.post("/v1/connections/openfinance/consent", headers=H, json={"institution": "itau"})
    assert r.status_code == 503


def test_openfinance_provider_with_credentials_but_not_integrated_is_501():
    app = _app(
        FX_OPENFINANCE_PROVIDER="pluggy",
        FX_OPENFINANCE_CLIENT_ID="id-123",
        FX_OPENFINANCE_CLIENT_SECRET="segredo-456",
    )
    with TestClient(app) as client:
        r = client.post("/v1/connections/openfinance/consent", headers=H, json={"institution": "itau"})
    assert r.status_code == 501
    assert "não integrado" in r.json()["detail"]
    assert "segredo-456" not in r.text


def test_openfinance_consent_rejects_bank_credentials_fields(api):
    client, _ = api
    r = client.post(
        "/v1/connections/openfinance/consent",
        headers=H,
        json={"institution": "itau", "password": "nao-devia-chegar"},
    )
    assert r.status_code == 503  # o corpo extra é ignorado; nada é aceito nem guardado
    assert "nao-devia-chegar" not in r.text


def test_openapi_lists_connection_routes(api):
    _, app = api
    paths = app.openapi()["paths"]
    for route in (
        "/v1/connections",
        "/v1/connections/validate-key",
        "/v1/connections/openfinance/consent",
        "/v1/connections/{connection_id}/sync",
        "/v1/connections/{connection_id}/statement",
        "/v1/connections/{connection_id}",
    ):
        assert route in paths, route
    dumped = json.dumps(app.openapi())
    assert "api_secret" in dumped  # o campo existe no contrato como SecretStr, não como valor
