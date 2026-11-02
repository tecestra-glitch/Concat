from __future__ import annotations

import json
import logging
import smtplib
from typing import Any

import httpx
import pytest
import respx

from fronteira_fx.notify.channels import (
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    ChannelError,
    EmailChannel,
    NotifySettings,
    TelegramChannel,
    UiChannel,
    WebhookChannel,
    build_channels,
    sign_webhook,
    verify_webhook_signature,
)
from tests.notify.support import NOW, make_event, make_rule

TOKEN = "123456:SECRET-TOKEN-XYZ"
TG_URL = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
WEBHOOK_URL = "https://hooks.example.com/fx"
WEBHOOK_SECRET = "webhook-secret-987"


# --- telegram --------------------------------------------------------------------------------


def _tg_rule(**overrides: Any):
    return make_rule(channel="telegram", target="-1001234567890", **overrides)


def test_telegram_success_posts_send_message_with_chat_and_text():
    event = make_event("telegram")
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(TG_URL).mock(return_value=httpx.Response(200, json={"ok": True, "result": {}}))
        TelegramChannel(TOKEN).send(_tg_rule(), event)
    body = json.loads(route.calls.last.request.content)
    assert body == {"chat_id": "-1001234567890", "text": event.message, "disable_web_page_preview": True}


def test_telegram_4xx_is_undelivered_with_description_and_no_token():
    with respx.mock as mock:
        mock.post(TG_URL).mock(
            return_value=httpx.Response(400, json={"ok": False, "error_code": 400, "description": "Bad Request: chat not found"})
        )
        with pytest.raises(ChannelError) as info:
            TelegramChannel(TOKEN).send(_tg_rule(), make_event("telegram"))
    message = str(info.value)
    assert "HTTP 400" in message and "chat not found" in message
    assert "SECRET-TOKEN-XYZ" not in message and "123456" not in message


def test_telegram_non_json_error_body_still_reports_status():
    with respx.mock as mock:
        mock.post(TG_URL).mock(return_value=httpx.Response(502, text="<html>bad gateway</html>"))
        with pytest.raises(ChannelError, match="HTTP 502"):
            TelegramChannel(TOKEN).send(_tg_rule(), make_event("telegram"))


def test_telegram_network_failure_is_sanitized():
    with respx.mock as mock:
        mock.post(TG_URL).mock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(ChannelError) as info:
            TelegramChannel(TOKEN).send(_tg_rule(), make_event("telegram"))
    assert str(info.value) == "telegram: falha de rede (ConnectError)"


def test_telegram_without_token_fails_gracefully_without_network():
    with respx.mock(assert_all_called=False) as mock:
        route = mock.post(url__regex=r".*sendMessage").mock(return_value=httpx.Response(200, json={"ok": True}))
        with pytest.raises(ChannelError, match="FX_TELEGRAM_BOT_TOKEN"):
            TelegramChannel(None).send(_tg_rule(), make_event("telegram"))
    assert not route.called


def test_telegram_token_never_reaches_logs(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)
    with respx.mock as mock:
        mock.post(TG_URL).mock(return_value=httpx.Response(200, json={"ok": True}))
        TelegramChannel(TOKEN).send(_tg_rule(), make_event("telegram"))
    assert "HTTP Request" in caplog.text  # o httpx registrou a requisição...
    assert "SECRET-TOKEN-XYZ" not in caplog.text  # ...mas sem o token
    assert "123456:" not in caplog.text


def test_telegram_repr_hides_token():
    assert TOKEN not in repr(TelegramChannel(TOKEN))


# --- webhook ---------------------------------------------------------------------------------


def _webhook_rule():
    return make_rule(channel="webhook", target=WEBHOOK_URL)


def test_webhook_sends_signed_canonical_json_that_verifies():
    event = make_event("webhook")
    ts = str(int(NOW.timestamp()))
    with respx.mock as mock:
        route = mock.post(WEBHOOK_URL).mock(return_value=httpx.Response(204))
        WebhookChannel(WEBHOOK_SECRET, clock=lambda: float(ts)).send(_webhook_rule(), event)
    request = route.calls.last.request
    body = request.content
    assert json.loads(body)["message"] == event.message
    assert request.headers[TIMESTAMP_HEADER] == ts
    signature = request.headers[SIGNATURE_HEADER]
    assert signature == "sha256=" + sign_webhook(WEBHOOK_SECRET, ts, body)
    assert verify_webhook_signature(WEBHOOK_SECRET, body=body, timestamp=ts, signature=signature, now=float(ts))


def test_webhook_verification_rejects_wrong_secret_tampering_replay_and_bad_format():
    ts = str(int(NOW.timestamp()))
    body = b'{"message":"ok"}'
    good = "sha256=" + sign_webhook(WEBHOOK_SECRET, ts, body)
    now = float(ts)
    assert verify_webhook_signature(WEBHOOK_SECRET, body=body, timestamp=ts, signature=good, now=now)
    assert not verify_webhook_signature("outro", body=body, timestamp=ts, signature=good, now=now)
    assert not verify_webhook_signature(WEBHOOK_SECRET, body=body + b" ", timestamp=ts, signature=good, now=now)
    assert not verify_webhook_signature(WEBHOOK_SECRET, body=body, timestamp=ts, signature=good, now=now + 301)
    assert not verify_webhook_signature(WEBHOOK_SECRET, body=body, timestamp=ts, signature=good.upper(), now=now)
    assert not verify_webhook_signature(WEBHOOK_SECRET, body=body, timestamp=ts, signature=good[7:], now=now)
    assert not verify_webhook_signature(WEBHOOK_SECRET, body=body, timestamp="nao-e-int", signature=good, now=now)


def test_webhook_without_secret_sends_no_signature_headers():
    with respx.mock as mock:
        route = mock.post(WEBHOOK_URL).mock(return_value=httpx.Response(200))
        WebhookChannel(None).send(_webhook_rule(), make_event("webhook"))
    assert SIGNATURE_HEADER not in route.calls.last.request.headers
    assert TIMESTAMP_HEADER not in route.calls.last.request.headers


def test_webhook_non_2xx_and_network_errors_are_undelivered():
    with respx.mock as mock:
        mock.post(WEBHOOK_URL).mock(return_value=httpx.Response(500))
        with pytest.raises(ChannelError, match="HTTP 500"):
            WebhookChannel(WEBHOOK_SECRET).send(_webhook_rule(), make_event("webhook"))
    with respx.mock as mock:
        mock.post(WEBHOOK_URL).mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(ChannelError, match="ReadTimeout"):
            WebhookChannel(WEBHOOK_SECRET).send(_webhook_rule(), make_event("webhook"))


def test_webhook_secret_never_reaches_logs_or_errors(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.INFO)
    with respx.mock as mock:
        mock.post(WEBHOOK_URL).mock(return_value=httpx.Response(418))
        with pytest.raises(ChannelError) as info:
            WebhookChannel(WEBHOOK_SECRET).send(_webhook_rule(), make_event("webhook"))
    assert WEBHOOK_SECRET not in str(info.value)
    assert WEBHOOK_SECRET not in caplog.text


# --- email -----------------------------------------------------------------------------------


class FakeSMTP:
    def __init__(self, *, offer_starttls: bool = True, login_error: Exception | None = None) -> None:
        self.offer_starttls = offer_starttls
        self.login_error = login_error
        self.calls: list[tuple[Any, ...]] = []
        self.sent: list[Any] = []

    def __enter__(self) -> FakeSMTP:
        return self

    def __exit__(self, *exc: object) -> bool:
        self.calls.append(("quit",))
        return False

    def ehlo(self) -> None:
        self.calls.append(("ehlo",))

    def has_extn(self, name: str) -> bool:
        return self.offer_starttls and name == "starttls"

    def starttls(self, context: Any = None) -> None:
        self.calls.append(("starttls",))

    def login(self, user: str, password: str) -> None:
        self.calls.append(("login", user, password))
        if self.login_error is not None:
            raise self.login_error

    def send_message(self, message: Any) -> None:
        self.sent.append(message)


def _connect_to(fake: FakeSMTP):
    seen: dict[str, Any] = {}

    def connect(host: str, port: int, use_ssl: bool, timeout: float) -> FakeSMTP:
        seen.update(host=host, port=port, use_ssl=use_ssl)
        return fake

    return connect, seen


def _email_rule():
    return make_rule(channel="email", target="voce@example.com", name="ciclo")


def test_email_starttls_login_and_message_headers():
    fake = FakeSMTP()
    connect, seen = _connect_to(fake)
    channel = EmailChannel("smtp://fx%40mail:p%40ss@smtp.example.com", "Fronteira <fx@example.com>", connect=connect)
    channel.send(_email_rule(), make_event("email", "Ciclo X: +R$ 1,00"))
    assert seen == {"host": "smtp.example.com", "port": 587, "use_ssl": False}
    assert ("starttls",) in fake.calls and fake.calls.index(("starttls",)) < fake.calls.index(
        ("login", "fx@mail", "p@ss")
    )
    message = fake.sent[0]
    assert message["To"] == "voce@example.com"
    assert message["From"] == "Fronteira <fx@example.com>"
    assert message["Subject"] == "Fronteira FX: Ciclo X: +R$ 1,00"
    assert "alerta «ciclo»" in message.get_content()


def test_email_smtps_uses_ssl_on_465_without_starttls():
    fake = FakeSMTP()
    connect, seen = _connect_to(fake)
    EmailChannel("smtps://fx:pw@smtp.example.com", "fx@example.com", connect=connect).send(_email_rule(), make_event())
    assert seen == {"host": "smtp.example.com", "port": 465, "use_ssl": True}
    assert ("starttls",) not in fake.calls
    assert ("login", "fx", "pw") in fake.calls


def test_email_refuses_login_over_plain_connection():
    fake = FakeSMTP(offer_starttls=False)
    connect, _ = _connect_to(fake)
    channel = EmailChannel("smtp://fx:pw@smtp.example.com", "fx@example.com", connect=connect)
    with pytest.raises(ChannelError, match="exige TLS"):
        channel.send(_email_rule(), make_event())
    assert not any(call[0] == "login" for call in fake.calls)
    assert fake.sent == []


def test_email_unset_settings_skip_gracefully():
    with pytest.raises(ChannelError, match="FX_SMTP_URL e FX_SMTP_FROM não configurados"):
        EmailChannel(None, None).send(_email_rule(), make_event())
    with pytest.raises(ChannelError, match="não configurados"):
        EmailChannel("smtp://h", None).send(_email_rule(), make_event())


def test_email_bad_scheme_and_bad_port_are_reported():
    with pytest.raises(ChannelError, match="smtps://"):
        EmailChannel("http://h", "fx@example.com", connect=_connect_to(FakeSMTP())[0]).send(_email_rule(), make_event())
    with pytest.raises(ChannelError, match="porta inválida"):
        EmailChannel("smtp://h:99999x", "fx@example.com", connect=_connect_to(FakeSMTP())[0]).send(
            _email_rule(), make_event()
        )


def test_email_smtp_error_is_sanitized_and_password_free():
    error = smtplib.SMTPAuthenticationError(535, b"5.7.8 bad credentials for p@ss")
    fake = FakeSMTP(login_error=error)
    connect, _ = _connect_to(fake)
    channel = EmailChannel("smtp://fx:p%40ss@smtp.example.com", "fx@example.com", connect=connect)
    with pytest.raises(ChannelError) as info:
        channel.send(_email_rule(), make_event())
    message = str(info.value)
    assert message == "email: falha SMTP (SMTPAuthenticationError, código 535)"
    assert "p@ss" not in message and "bad credentials" not in message


# --- ui, settings, factory -------------------------------------------------------------------


def test_ui_channel_is_a_no_op_because_the_event_is_stored():
    assert UiChannel().send(make_rule(), make_event()) is None


def test_notify_settings_read_env_and_hide_secrets_in_repr():
    env = {
        "FX_TELEGRAM_BOT_TOKEN": f"  {TOKEN} ",
        "FX_WEBHOOK_SECRET": WEBHOOK_SECRET,
        "FX_SMTP_URL": "smtps://fx:pw@smtp.example.com",
        "FX_SMTP_FROM": "fx@example.com",
        "FX_EMPTY": "",
    }
    settings = NotifySettings.from_env(env)
    assert settings.telegram_bot_token == TOKEN
    assert settings.smtp_from == "fx@example.com"
    text = repr(settings)
    assert TOKEN not in text and WEBHOOK_SECRET not in text and "pw@" not in text


def test_build_channels_returns_all_four_with_unset_ones_failing_safely():
    channels = build_channels(NotifySettings(), http_client=httpx.Client())
    assert set(channels) == {"ui", "telegram", "webhook", "email"}
    with pytest.raises(ChannelError, match="FX_TELEGRAM_BOT_TOKEN"):
        channels["telegram"].send(_tg_rule(), make_event("telegram"))
    channels["ui"].send(make_rule(), make_event())  # não levanta
