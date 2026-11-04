"""Validação de chave de corretora só de leitura, com httpx (sem ccxt) e sem nenhum endpoint de ordem ou saque.

Regra: a chave só é aceita quando a própria corretora confirma que ela não opera, não saca e não transfere.
Corretora sem endpoint de permissões é recusada por padrão. Mensagens de erro nunca carregam chave, assinatura
ou corpo de resposta de terceiros.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlencode

import httpx

BINANCE_BASE_URL = "https://api.binance.com"
HTTP_TIMEOUT_S = 10.0

# Qualquer uma destas ligada (ou ausente) recusa a chave. Ausente conta como ligada: fail closed.
BINANCE_DANGEROUS_FLAGS = (
    "enableSpotAndMarginTrading",
    "enableMargin",
    "enableFutures",
    "enableWithdrawals",
    "enableInternalTransfer",
    "permitsUniversalTransfer",
    "enableVanillaOptions",
    "enablePortfolioMarginTrading",
)
BINANCE_REQUIRED_FLAG = "enableReading"

KRAKEN_REFUSAL = (
    "Kraken não oferece endpoint que mostre as permissões da chave; a chave é recusada por padrão. "
    "Crie uma chave só com 'Query Funds' (sem Trade, Withdraw ou Transfer) e confirme no painel da corretora."
)


class ExchangeCheckError(Exception):
    """Falha ao falar com a corretora. A mensagem é segura para o usuário (sem segredo)."""


@dataclass(frozen=True)
class Balance:
    asset: str
    free: Decimal
    locked: Decimal


@dataclass
class KeyCheck:
    ok: bool
    institution: str
    flags: dict[str, bool | None] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    balances: list[Balance] = field(default_factory=list)


def _binance_signed_get(
    client: httpx.Client, path: str, params: dict[str, str], api_key: str, api_secret: str
) -> dict[str, Any]:
    query = urlencode({**params, "timestamp": str(int(time.time() * 1000)), "recvWindow": "5000"})
    signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    try:
        resp = client.get(f"{path}?{query}&signature={signature}", headers={"X-MBX-APIKEY": api_key})
    except httpx.HTTPError:
        # Sem repr da exceção: a URL dela carrega a assinatura.
        raise ExchangeCheckError("falha de rede ao falar com a corretora") from None
    if resp.status_code in (401, 403):
        raise ExchangeCheckError("corretora recusou a chave (inválida, expirada ou sem permissão de leitura)")
    if resp.status_code != 200:
        raise ExchangeCheckError(f"corretora respondeu {resp.status_code}")
    try:
        data = resp.json()
    except ValueError:
        raise ExchangeCheckError("resposta da corretora não é JSON") from None
    if not isinstance(data, dict):
        raise ExchangeCheckError("resposta da corretora com formato inesperado")
    return data


def _parse_balances(account: dict[str, Any]) -> list[Balance]:
    out: list[Balance] = []
    for item in account.get("balances") or []:
        try:
            free = Decimal(str(item["free"]))
            locked = Decimal(str(item["locked"]))
        except (KeyError, InvalidOperation, TypeError):
            raise ExchangeCheckError("saldo com formato inesperado na resposta da corretora") from None
        if free == 0 and locked == 0:
            continue
        out.append(Balance(asset=str(item.get("asset", "?"))[:16], free=free, locked=locked))
    return out


def check_binance(
    api_key: str,
    api_secret: str,
    *,
    transport: httpx.BaseTransport | None = None,
    base_url: str = BINANCE_BASE_URL,
) -> KeyCheck:
    """Lê as restrições da chave e, se ela for só leitura, o saldo. Nenhum endpoint de ordem é chamado."""
    with httpx.Client(base_url=base_url, timeout=HTTP_TIMEOUT_S, transport=transport) as client:
        restrictions = _binance_signed_get(client, "/sapi/v1/account/apiRestrictions", {}, api_key, api_secret)
        flags: dict[str, bool | None] = {name: _flag(restrictions, name) for name in BINANCE_DANGEROUS_FLAGS}
        flags[BINANCE_REQUIRED_FLAG] = _flag(restrictions, BINANCE_REQUIRED_FLAG)
        reasons: list[str] = []
        for name in BINANCE_DANGEROUS_FLAGS:
            if flags[name] is not False:
                state = "ligado" if flags[name] else "ausente na resposta"
                reasons.append(f"{name} {state}: a chave pode operar, sacar ou transferir")
        if flags[BINANCE_REQUIRED_FLAG] is not True:
            reasons.append(f"{BINANCE_REQUIRED_FLAG} não confirmado: a chave precisa de leitura")
        if reasons:
            return KeyCheck(ok=False, institution="binance", flags=flags, reasons=reasons)

        account = _binance_signed_get(client, "/api/v3/account", {}, api_key, api_secret)
        if account.get("canTrade") is not False or account.get("canWithdraw") is not False:
            reasons.append("a corretora informa que a chave pode operar ou sacar")
            return KeyCheck(ok=False, institution="binance", flags=flags, reasons=reasons)
        return KeyCheck(ok=True, institution="binance", flags=flags, balances=_parse_balances(account))


def _flag(data: dict[str, Any], name: str) -> bool | None:
    value = data.get(name)
    return value if isinstance(value, bool) else None


def validate_readonly_key(
    institution: str,
    api_key: str,
    api_secret: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> KeyCheck:
    slug = institution.strip().lower()
    if slug == "binance":
        return check_binance(api_key, api_secret, transport=transport)
    if slug == "kraken":
        return KeyCheck(ok=False, institution=slug, reasons=[KRAKEN_REFUSAL])
    return KeyCheck(
        ok=False,
        institution=slug,
        reasons=[f"{slug}: sem validação de chave só leitura nesta versão; chave recusada por padrão"],
    )
