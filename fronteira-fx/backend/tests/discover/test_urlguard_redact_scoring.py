"""Offline tests: URL guard, redaction and the quote-likeness score. No network: resolvers are injected."""

from __future__ import annotations

import pytest

from fronteira_fx.discover.redact import scrub_params, scrub_raw, scrub_text, split_headers
from fronteira_fx.discover.scoring import score_text
from fronteira_fx.discover.urlguard import UnsafeUrl, check_public_url

PUBLIC = ["93.184.216.34"]


def _resolver(addresses):
    return lambda host: list(addresses)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "javascript:alert(1)",
        "ftp://example.com/x",
        "http://localhost:8000/",
        "http://api.localhost/",
        "http://127.0.0.1/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/",
        "http://0.0.0.0/",
        "http://user:pw@8.8.8.8/",
        "http://printer.local/",
        "https:///sem-host",
    ],
)
def test_rejects_non_public_urls(url):
    with pytest.raises(UnsafeUrl):
        check_public_url(url, resolver=_resolver(PUBLIC))


def test_accepts_public_ip_literal_without_dns():
    assert check_public_url("http://8.8.8.8/x") == "http://8.8.8.8/x"


def test_accepts_hostname_resolving_to_public_address():
    assert check_public_url("https://example.com/", resolver=_resolver(PUBLIC))


def test_rejects_hostname_with_any_private_address():
    with pytest.raises(UnsafeUrl):
        check_public_url("https://example.com/", resolver=_resolver(["93.184.216.34", "10.1.2.3"]))


def test_rejects_unresolvable_host():
    def boom(host):
        raise OSError("nxdomain")

    with pytest.raises(UnsafeUrl):
        check_public_url("https://nao-existe.example/", resolver=boom)


def test_scrub_text_removes_personal_data_and_tokens():
    text = 'contato ana@exemplo.com.py, CPF 12345678901, {"token": "abc123"}, eyJhbGciOiJI.payload1234.signature99'
    out = scrub_text(text)
    assert "ana@exemplo" not in out and "<email>" in out
    assert "12345678901" not in out and "<numero>" in out
    assert "abc123" not in out and "<redigido>" in out
    assert "eyJhbGci" not in out


def test_scrub_text_keeps_rate_numbers():
    assert "5.944,76" in scrub_text("USD compra 5.944,76 venta 5.980,00")


def test_scrub_raw_keeps_structure():
    raw = '{\n  "compra": "5.800",\n  "email": "a@b.com"\n}'
    out = scrub_raw(raw)
    assert out.count("\n") == raw.count("\n")
    assert "a@b.com" not in out and '"compra": "5.800"' in out


def test_split_headers_drops_session_headers_and_names_them():
    kept, omitted = split_headers(
        {
            "Accept": "application/json",
            "Cookie": "sid=secreto",
            "Authorization": "Bearer x",
            "X-CSRF-Token": "t",
            "Host": "example.com",
            "Referer": "https://example.com/",
        }
    )
    assert kept == {"accept": "application/json", "referer": "https://example.com/"}
    assert omitted == ["authorization", "cookie", "x-csrf-token"]


def test_scrub_params_masks_secret_names_only():
    assert scrub_params({"suc": "villamorra", "api_key": "k", "sessionid": "s"}) == {
        "suc": "villamorra",
        "api_key": "<redigido>",
        "sessionid": "<redigido>",
    }


def test_score_empty_is_zero():
    assert score_text("   ").total == 0


def test_score_quote_board_is_high():
    text = '{"villamorra": [{"bcp": "USD", "compra": "5.800", "venta": "5.920"}, {"bcp": "BRL", "compra": "1.070"}]}'
    s = score_text(text, is_json=True)
    assert s.total >= 55
    assert any("moedas" in r for r in s.reasons) and any("compra" in r for r in s.reasons)


def test_score_unrelated_text_is_zero():
    assert score_text("Bem-vindo ao nosso site, fale conosco.").total == 0


def test_score_currency_without_vocabulary_is_partial():
    s = score_text("USD 7350")
    assert 0 < s.total < 70
