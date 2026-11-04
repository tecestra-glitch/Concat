"""Cofre AES-256-GCM e validação de chave só leitura. Sem rede: httpx.MockTransport em todo lugar."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import httpx
import pytest

from fronteira_fx.connections.exchanges import (
    BINANCE_DANGEROUS_FLAGS,
    KRAKEN_REFUSAL,
    ExchangeCheckError,
    check_binance,
    validate_readonly_key,
)
from fronteira_fx.connections.vault import (
    Credentials,
    VaultError,
    VaultUnavailable,
    decrypt,
    encrypt,
    key_hint,
    load_master_key,
    open_credentials,
    seal_credentials,
)

KEY = base64.b64encode(bytes(range(32))).decode()
API_KEY = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789wxyz"
API_SECRET = "SECRET-super-secreto-9876543210"
READ_ONLY = {
    "enableReading": True,
    "enableSpotAndMarginTrading": False,
    "enableMargin": False,
    "enableFutures": False,
    "enableWithdrawals": False,
    "enableInternalTransfer": False,
    "permitsUniversalTransfer": False,
    "enableVanillaOptions": False,
    "enablePortfolioMarginTrading": False,
    "ipRestrict": False,
}
ACCOUNT = {
    "canTrade": False,
    "canWithdraw": False,
    "canDeposit": True,
    "balances": [
        {"asset": "USDT", "free": "120.50", "locked": "0.00"},
        {"asset": "BTC", "free": "0", "locked": "0"},
        {"asset": "BRL", "free": "10", "locked": "2.5"},
    ],
}


def _binance_transport(restrictions: dict | None, account: dict | None = None, status: int = 200, log=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if log is not None:
            log.append(request)
        if request.headers.get("X-MBX-APIKEY") is None:
            return httpx.Response(401, json={"code": -2015})
        if status != 200:
            return httpx.Response(status, json={"msg": "nope"})
        if request.url.path == "/sapi/v1/account/apiRestrictions":
            return httpx.Response(200, json=restrictions or {})
        if request.url.path == "/api/v3/account":
            return httpx.Response(200, json=account or ACCOUNT)
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


# ---------- cofre ----------


def test_seal_and_open_round_trip_and_ciphertext_hides_secret():
    key = load_master_key(KEY)
    creds = Credentials(API_KEY, API_SECRET)
    token = seal_credentials(key, "conn-1", "binance", creds)
    assert API_SECRET not in token and API_KEY not in token
    opened = open_credentials(key, "conn-1", "binance", token)
    assert opened == creds


def test_nonce_is_random_per_seal():
    key = load_master_key(KEY)
    a = seal_credentials(key, "c", "binance", Credentials(API_KEY, API_SECRET))
    b = seal_credentials(key, "c", "binance", Credentials(API_KEY, API_SECRET))
    assert a != b


def test_wrong_master_key_fails_closed():
    token = seal_credentials(load_master_key(KEY), "c", "binance", Credentials(API_KEY, API_SECRET))
    other = load_master_key(base64.b64encode(bytes(range(1, 33))).decode())
    with pytest.raises(VaultError):
        open_credentials(other, "c", "binance", token)


def test_ciphertext_bound_to_connection_and_institution():
    key = load_master_key(KEY)
    token = seal_credentials(key, "conn-1", "binance", Credentials(API_KEY, API_SECRET))
    with pytest.raises(VaultError):
        open_credentials(key, "conn-2", "binance", token)
    with pytest.raises(VaultError):
        open_credentials(key, "conn-1", "kraken", token)


def test_tampered_ciphertext_rejected():
    key = load_master_key(KEY)
    raw = bytearray(base64.b64decode(seal_credentials(key, "c", "binance", Credentials(API_KEY, API_SECRET))))
    raw[-1] ^= 0x01
    with pytest.raises(VaultError):
        decrypt(key, base64.b64encode(bytes(raw)).decode(), b"c|binance")


def test_malformed_token_rejected():
    with pytest.raises(VaultError):
        decrypt(load_master_key(KEY), "!!!", b"x")
    with pytest.raises(VaultError):
        decrypt(load_master_key(KEY), base64.b64encode(b"short").decode(), b"x")


def test_encrypt_primitive_round_trip():
    key = load_master_key(KEY)
    assert decrypt(key, encrypt(key, b"abc", b"aad"), b"aad") == b"abc"


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_vault_off_without_key(raw):
    with pytest.raises(VaultUnavailable, match="desligado"):
        load_master_key(raw)


@pytest.mark.parametrize("raw", ["not base64!!", base64.b64encode(b"x" * 16).decode()])
def test_vault_refuses_malformed_key(raw):
    with pytest.raises(VaultUnavailable, match="32 bytes"):
        load_master_key(raw)


def test_credentials_repr_never_shows_secret():
    text = repr(Credentials(API_KEY, API_SECRET))
    assert API_KEY not in text and API_SECRET not in text


def test_key_hint_is_last_four_only():
    assert key_hint(API_KEY) == "wxyz"
    assert API_KEY not in key_hint(API_KEY)


# ---------- chave só leitura ----------


def test_read_only_binance_key_accepted_and_balances_read():
    check = check_binance(API_KEY, API_SECRET, transport=_binance_transport(READ_ONLY))
    assert check.ok is True
    assert check.reasons == []
    assert {b.asset: str(b.free) for b in check.balances} == {"USDT": "120.50", "BRL": "10"}


@pytest.mark.parametrize("flag", BINANCE_DANGEROUS_FLAGS)
def test_dangerous_binance_flag_refuses_key(flag):
    restrictions = {**READ_ONLY, flag: True}
    calls: list[httpx.Request] = []
    check = check_binance(API_KEY, API_SECRET, transport=_binance_transport(restrictions, log=calls))
    assert check.ok is False
    assert any(flag in r for r in check.reasons)
    # recusada antes de qualquer leitura de saldo
    assert all(c.url.path != "/api/v3/account" for c in calls)


def test_missing_dangerous_flag_fails_closed():
    restrictions = {k: v for k, v in READ_ONLY.items() if k != "enableWithdrawals"}
    check = check_binance(API_KEY, API_SECRET, transport=_binance_transport(restrictions))
    assert check.ok is False
    assert any("enableWithdrawals" in r for r in check.reasons)


def test_key_without_reading_permission_refused():
    check = check_binance(API_KEY, API_SECRET, transport=_binance_transport({**READ_ONLY, "enableReading": False}))
    assert check.ok is False


def test_account_reporting_trade_or_withdraw_refused():
    check = check_binance(
        API_KEY, API_SECRET, transport=_binance_transport(READ_ONLY, {**ACCOUNT, "canWithdraw": True})
    )
    assert check.ok is False
    check = check_binance(API_KEY, API_SECRET, transport=_binance_transport(READ_ONLY, {**ACCOUNT, "canTrade": True}))
    assert check.ok is False


def test_requests_are_signed_and_use_header_not_url_for_key():
    calls: list[httpx.Request] = []
    check_binance(API_KEY, API_SECRET, transport=_binance_transport(READ_ONLY, log=calls))
    assert calls, "deveria chamar a corretora"
    for req in calls:
        assert req.method == "GET"  # nenhuma escrita
        assert API_KEY not in str(req.url)
        assert req.headers["X-MBX-APIKEY"] == API_KEY
        query, sig = str(req.url.query.decode()).rsplit("&signature=", 1)
        expected = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
        assert sig == expected
        assert "order" not in req.url.path and "withdraw" not in req.url.path and "transfer" not in req.url.path


def test_binance_http_rejection_message_has_no_secret():
    with pytest.raises(ExchangeCheckError) as info:
        check_binance(API_KEY, API_SECRET, transport=_binance_transport(None, status=401))
    assert API_SECRET not in str(info.value) and API_KEY not in str(info.value)


def test_binance_status_403_and_500_mapped_to_safe_messages():
    with pytest.raises(ExchangeCheckError, match="recusou"):
        check_binance(API_KEY, API_SECRET, transport=_binance_transport(None, status=403))
    with pytest.raises(ExchangeCheckError, match="respondeu 500"):
        check_binance(API_KEY, API_SECRET, transport=_binance_transport(None, status=500))


def test_network_error_message_hides_signed_url():
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"falhou em {request.url}")

    with pytest.raises(ExchangeCheckError) as info:
        check_binance(API_KEY, API_SECRET, transport=httpx.MockTransport(boom))
    assert "signature" not in str(info.value)
    assert API_SECRET not in str(info.value)
    assert info.value.__cause__ is None  # sem cadeia que exponha a URL assinada


def test_kraken_refused_by_default_with_explanation():
    check = validate_readonly_key("kraken", API_KEY, API_SECRET, transport=_binance_transport(READ_ONLY))
    assert check.ok is False
    assert check.reasons == [KRAKEN_REFUSAL]


def test_unknown_institution_refused_by_default():
    check = validate_readonly_key("bancoX", API_KEY, API_SECRET)
    assert check.ok is False
    assert "recusada por padrão" in check.reasons[0]


def test_binance_dispatch_is_case_insensitive():
    check = validate_readonly_key(" Binance ", API_KEY, API_SECRET, transport=_binance_transport(READ_ONLY))
    assert check.ok is True
    assert json.dumps(check.flags, sort_keys=True)  # flags são só booleanos, sem segredo
