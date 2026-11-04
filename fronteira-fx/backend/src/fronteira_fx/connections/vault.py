"""Cofre de credenciais de corretora: AES-256-GCM com chave mestra em FX_CONNECTIONS_KEY (32 bytes em base64).

Cada segredo é cifrado com um nonce aleatório de 96 bits e com `aad` = id da conexão + instituição, então um
ciphertext não serve para outra conexão. Nada daqui vai para log, exceção ou resposta HTTP.
"""

from __future__ import annotations

import base64
import binascii
import json
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32
NONCE_BYTES = 12
TAG_BYTES = 16
HINT_CHARS = 4


class VaultUnavailable(RuntimeError):
    """Cofre desligado (sem FX_CONNECTIONS_KEY) ou chave mestra malformada. Vira 503 nas rotas."""


class VaultError(ValueError):
    """Ciphertext inválido, alterado ou de outra conexão."""


@dataclass(frozen=True)
class Credentials:
    api_key: str
    api_secret: str

    def __repr__(self) -> str:  # nunca mostrar segredo em repr/log
        return "Credentials(api_key=***, api_secret=***)"


def load_master_key(raw: str | None) -> bytes:
    if raw is None or not raw.strip():
        raise VaultUnavailable("cofre de conexões desligado: defina FX_CONNECTIONS_KEY (openssl rand -base64 32)")
    try:
        key = base64.b64decode(raw.strip(), validate=True)
    except (binascii.Error, ValueError):
        raise VaultUnavailable("FX_CONNECTIONS_KEY inválida: precisa ser 32 bytes em base64") from None
    if len(key) != KEY_BYTES:
        raise VaultUnavailable("FX_CONNECTIONS_KEY inválida: precisa ser 32 bytes em base64")
    return key


def encrypt(key: bytes, plaintext: bytes, aad: bytes) -> str:
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(key).encrypt(nonce, plaintext, aad)
    return base64.b64encode(nonce + sealed).decode("ascii")


def decrypt(key: bytes, token: str, aad: bytes) -> bytes:
    try:
        raw = base64.b64decode(token, validate=True)
    except (binascii.Error, ValueError):
        raise VaultError("cofre: dado cifrado malformado") from None
    if len(raw) < NONCE_BYTES + TAG_BYTES:
        raise VaultError("cofre: dado cifrado malformado")
    try:
        return AESGCM(key).decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], aad)
    except InvalidTag:
        raise VaultError("cofre: decifragem falhou (chave mestra errada ou dado alterado)") from None


def _aad(connection_id: str, institution: str) -> bytes:
    return f"{connection_id}|{institution}".encode()


def seal_credentials(key: bytes, connection_id: str, institution: str, creds: Credentials) -> str:
    payload = json.dumps({"k": creds.api_key, "s": creds.api_secret}, ensure_ascii=False).encode()
    return encrypt(key, payload, _aad(connection_id, institution))


def open_credentials(key: bytes, connection_id: str, institution: str, token: str) -> Credentials:
    data = json.loads(decrypt(key, token, _aad(connection_id, institution)))
    return Credentials(api_key=str(data["k"]), api_secret=str(data["s"]))


def key_hint(api_key: str) -> str:
    """Só os últimos caracteres da chave pública, para o usuário reconhecer qual chave está guardada."""
    return api_key.strip()[-HINT_CHARS:]
