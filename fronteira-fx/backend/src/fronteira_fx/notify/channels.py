"""Canais de entrega: `ui` (já gravado), `telegram` (Bot API), `webhook` (HTTP + HMAC) e `email` (SMTP).

Regras de segurança deste módulo:
- segredos (token do bot, segredo do webhook, senha SMTP) vêm só de variáveis de ambiente (`NotifySettings`);
- mensagens de erro são sanitizadas e nunca carregam a URL do Telegram, senha ou segredo;
- o httpx registra cada URL de requisição em INFO: um filtro no logger `httpx` mascara o token do bot
  antes de qualquer handler ver a mensagem.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import smtplib
import ssl
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from email.message import EmailMessage
from typing import Any, Protocol
from urllib.parse import unquote, urlsplit

import httpx

from .rules import AlertEvent, AlertRule

log = logging.getLogger("fronteira_fx.notify")

SIGNATURE_HEADER = "X-Fronteira-Signature"
TIMESTAMP_HEADER = "X-Fronteira-Timestamp"
SIGNATURE_PREFIX = "sha256="
_MAX_ERROR = 300

_registered_secrets: set[str] = set()
_BOT_TOKEN_RE = re.compile(r"/bot[0-9]+:[A-Za-z0-9_-]+")


class ChannelError(Exception):
    """Falha de entrega. A mensagem já vem sanitizada e pode ir para `AlertEvent.error`."""


class Channel(Protocol):
    """Contrato de um canal de entrega. `send` levanta `ChannelError` quando não entregou."""

    name: str

    def send(self, rule: AlertRule, event: AlertEvent) -> None: ...


def redact_text(text: str) -> str:
    """Mascara token de bot do Telegram e qualquer segredo registrado."""
    text = _BOT_TOKEN_RE.sub("/bot***", text)
    for secret in _registered_secrets:
        text = text.replace(secret, "***")
    return text


def register_secret(secret: str | None) -> None:
    if secret:
        _registered_secrets.add(secret)


def _clip_error(text: str, secrets: Iterable[str | None] = ()) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return redact_text(text)[:_MAX_ERROR]


class _RedactingFilter(logging.Filter):
    """Filtro de logger: mascara segredos nos argumentos e na mensagem de cada registro."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(_scrub_arg(arg) for arg in record.args)
        return True


def _scrub_arg(arg: object) -> object:
    if arg is None or isinstance(arg, bool | int | float):
        return arg
    return redact_text(arg if isinstance(arg, str) else str(arg))


for _logger_name in ("httpx", "httpcore"):
    _logger = logging.getLogger(_logger_name)
    if not any(isinstance(f, _RedactingFilter) for f in _logger.filters):
        _logger.addFilter(_RedactingFilter())


class UiChannel:
    """Canal da interface: o disparo já foi gravado no store; o painel lê o histórico."""

    name = "ui"

    def send(self, rule: AlertRule, event: AlertEvent) -> None:
        return None


class TelegramChannel:
    """Envia `sendMessage` pela Bot API. `rule.target` é o chat id (ou @canal)."""

    name = "telegram"

    def __init__(
        self,
        bot_token: str | None,
        *,
        client: httpx.Client | None = None,
        api_base: str = "https://api.telegram.org",
        timeout: float = 10.0,
    ) -> None:
        self._token = (bot_token or "").strip() or None
        register_secret(self._token)
        self._api_base = api_base.rstrip("/")
        self._client = client or httpx.Client(timeout=timeout)

    def __repr__(self) -> str:
        return f"TelegramChannel(configured={self._token is not None})"

    def send(self, rule: AlertRule, event: AlertEvent) -> None:
        if self._token is None:
            raise ChannelError("telegram: FX_TELEGRAM_BOT_TOKEN não configurado")
        if not rule.target:
            raise ChannelError("telegram: a regra não tem chat id")
        url = f"{self._api_base}/bot{self._token}/sendMessage"
        body = {"chat_id": rule.target, "text": event.message, "disable_web_page_preview": True}
        try:
            response = self._client.post(url, json=body)
        except httpx.HTTPError as exc:
            raise ChannelError(f"telegram: falha de rede ({type(exc).__name__})") from None
        data = _json_object(response)
        if response.status_code != 200 or data.get("ok") is not True:
            description = str(data.get("description") or "")[:200]
            detail = f" — {description}" if description else ""
            raise ChannelError(_clip_error(f"telegram: HTTP {response.status_code}{detail}", [self._token]))


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def canonical_json(payload: Any) -> bytes:
    """Serialização determinística usada no corpo do webhook (o receptor verifica estes bytes)."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def sign_webhook(secret: str, timestamp: str, body: bytes) -> str:
    """HMAC-SHA256 sobre `"<timestamp>." + corpo`. Retorna só o hexadecimal."""
    mac = hmac.new(secret.encode("utf-8"), timestamp.encode("ascii") + b"." + body, hashlib.sha256)
    return mac.hexdigest()


def verify_webhook_signature(
    secret: str,
    *,
    body: bytes,
    timestamp: str,
    signature: str,
    max_age_s: int = 300,
    now: float | None = None,
) -> bool:
    """Confere a assinatura de um webhook recebido. Recusa timestamps fora da janela (anti-replay)."""
    if not signature.startswith(SIGNATURE_PREFIX):
        return False
    try:
        sent_at = int(timestamp)
    except ValueError:
        return False
    current = time.time() if now is None else now
    if abs(current - sent_at) > max_age_s:
        return False
    expected = sign_webhook(secret, timestamp, body)
    return hmac.compare_digest(expected, signature[len(SIGNATURE_PREFIX) :])


class WebhookChannel:
    """POST do `AlertEvent` em JSON para `rule.target`, assinado com `FX_WEBHOOK_SECRET` quando definido."""

    name = "webhook"

    def __init__(
        self,
        secret: str | None,
        *,
        client: httpx.Client | None = None,
        timeout: float = 10.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._secret = (secret or "").strip() or None
        register_secret(self._secret)
        self._client = client or httpx.Client(timeout=timeout)
        self._clock = clock

    def __repr__(self) -> str:
        return f"WebhookChannel(signed={self._secret is not None})"

    def send(self, rule: AlertRule, event: AlertEvent) -> None:
        if not rule.target:
            raise ChannelError("webhook: a regra não tem URL de destino")
        body = canonical_json(event.model_dump(mode="json"))
        headers = {"Content-Type": "application/json", "User-Agent": "fronteira-fx-notify/1"}
        if self._secret is not None:
            timestamp = str(int(self._clock()))
            headers[TIMESTAMP_HEADER] = timestamp
            headers[SIGNATURE_HEADER] = SIGNATURE_PREFIX + sign_webhook(self._secret, timestamp, body)
        try:
            response = self._client.post(rule.target, content=body, headers=headers)
        except httpx.HTTPError as exc:
            raise ChannelError(f"webhook: falha de rede ({type(exc).__name__})") from None
        if not 200 <= response.status_code < 300:
            raise ChannelError(f"webhook: o destino respondeu HTTP {response.status_code}")


_SmtpConnect = Callable[[str, int, bool, float], Any]


def _smtp_connect(host: str, port: int, use_ssl: bool, timeout: float) -> Any:
    if use_ssl:
        return smtplib.SMTP_SSL(host, port, timeout=timeout, context=ssl.create_default_context())
    return smtplib.SMTP(host, port, timeout=timeout)


class EmailChannel:
    """E-mail via SMTP. `FX_SMTP_URL`: `smtps://usuario:senha@host:465` (TLS) ou `smtp://...` (STARTTLS)."""

    name = "email"

    def __init__(
        self,
        smtp_url: str | None,
        sender: str | None,
        *,
        connect: _SmtpConnect | None = None,
        timeout: float = 10.0,
    ) -> None:
        self._url = (smtp_url or "").strip() or None
        self._sender = (sender or "").strip() or None
        self._connect: _SmtpConnect = connect or _smtp_connect
        self._timeout = timeout
        if self._url is not None:
            register_secret(unquote(urlsplit(self._url).password or ""))

    def __repr__(self) -> str:
        return f"EmailChannel(configured={self._url is not None and self._sender is not None})"

    def send(self, rule: AlertRule, event: AlertEvent) -> None:
        if self._url is None or self._sender is None:
            raise ChannelError("email: FX_SMTP_URL e FX_SMTP_FROM não configurados")
        if not rule.target:
            raise ChannelError("email: a regra não tem destinatário")
        parts = urlsplit(self._url)
        scheme = parts.scheme.lower()
        if scheme not in ("smtp", "smtps") or not parts.hostname:
            raise ChannelError("email: FX_SMTP_URL deve começar com smtps:// (TLS) ou smtp:// (STARTTLS)")
        use_ssl = scheme == "smtps"
        try:
            port = parts.port or (465 if use_ssl else 587)
        except ValueError:
            raise ChannelError("email: porta inválida em FX_SMTP_URL") from None
        secrets = [unquote(parts.password or "")]
        try:
            message = EmailMessage()
            message["From"] = self._sender
            message["To"] = rule.target
            message["Subject"] = "Fronteira FX: " + " ".join(event.message.split())[:90]
            message.set_content(f"{event.message}\n\n— alerta «{rule.name}» do Fronteira FX")
        except ValueError:
            raise ChannelError("email: cabeçalho inválido (verifique FX_SMTP_FROM)") from None
        try:
            with self._connect(parts.hostname, port, use_ssl, self._timeout) as smtp:
                encrypted = use_ssl
                if not use_ssl:
                    smtp.ehlo()
                    if smtp.has_extn("starttls"):
                        smtp.starttls(context=ssl.create_default_context())
                        smtp.ehlo()
                        encrypted = True
                if parts.username:
                    if not encrypted:
                        raise ChannelError("email: login exige TLS (use smtps:// ou um servidor com STARTTLS)")
                    smtp.login(unquote(parts.username), unquote(parts.password or ""))
                smtp.send_message(message)
        except ChannelError:
            raise
        except (smtplib.SMTPException, OSError, ValueError) as exc:
            code = getattr(exc, "smtp_code", None)
            suffix = f", código {code}" if code else ""
            raise ChannelError(_clip_error(f"email: falha SMTP ({type(exc).__name__}{suffix})", secrets)) from None


@dataclass(frozen=True)
class NotifySettings:
    """Segredos e endereços lidos do ambiente. `repr` nunca mostra valores."""

    telegram_bot_token: str | None = field(default=None, repr=False)
    webhook_secret: str | None = field(default=None, repr=False)
    smtp_url: str | None = field(default=None, repr=False)
    smtp_from: str | None = None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> NotifySettings:
        source: Mapping[str, str] = os.environ if env is None else env

        def read(name: str) -> str | None:
            return (source.get(name) or "").strip() or None

        return cls(
            telegram_bot_token=read("FX_TELEGRAM_BOT_TOKEN"),
            webhook_secret=read("FX_WEBHOOK_SECRET"),
            smtp_url=read("FX_SMTP_URL"),
            smtp_from=read("FX_SMTP_FROM"),
        )


def build_channels(
    settings: NotifySettings | None = None, *, http_client: httpx.Client | None = None
) -> dict[str, Channel]:
    """Canais prontos para o `AlertService`. Canais sem configuração existem, mas registram falha ao enviar."""
    cfg = settings or NotifySettings.from_env()
    if cfg.webhook_secret is None:
        log.info("FX_WEBHOOK_SECRET não definido: webhooks de alerta saem sem assinatura")
    channels: dict[str, Channel] = {
        "ui": UiChannel(),
        "telegram": TelegramChannel(cfg.telegram_bot_token, client=http_client),
        "webhook": WebhookChannel(cfg.webhook_secret, client=http_client),
        "email": EmailChannel(cfg.smtp_url, cfg.smtp_from),
    }
    return channels
