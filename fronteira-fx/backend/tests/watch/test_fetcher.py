from __future__ import annotations

import httpx
import pytest
import respx

from fronteira_fx.watch.fetcher import FetchOutcome, conditional_get, conditional_headers, looks_blocked

URL = "https://fake.example/cotizaciones"


@respx.mock
async def test_200_returns_body_and_validators():
    route = respx.get(URL).mock(return_value=httpx.Response(
        200, text="<html>7350</html>", headers={"ETag": '"abc"', "Last-Modified": "Mon, 02 Nov 2026 12:00:00 GMT"},
    ))
    out = await conditional_get(URL)
    assert isinstance(out, FetchOutcome)
    assert out.ok and out.status_code == 200 and out.body == "<html>7350</html>"
    assert out.etag == '"abc"' and out.last_modified == "Mon, 02 Nov 2026 12:00:00 GMT"
    assert out.not_modified is False and out.error is None and out.elapsed_ms >= 0
    sent = route.calls.last.request.headers
    assert "If-None-Match" not in sent and "If-Modified-Since" not in sent
    assert sent["User-Agent"].startswith("Mozilla/5.0") and "es-PY" in sent["Accept-Language"]


@respx.mock
async def test_validators_are_echoed_and_304_means_not_modified():
    route = respx.get(URL).mock(return_value=httpx.Response(304))
    out = await conditional_get(URL, etag='"abc"', last_modified="Mon, 02 Nov 2026 12:00:00 GMT")
    sent = route.calls.last.request.headers
    assert sent["If-None-Match"] == '"abc"'
    assert sent["If-Modified-Since"] == "Mon, 02 Nov 2026 12:00:00 GMT"
    assert out.ok and out.not_modified is True and out.body is None and out.status_code == 304
    # previous validators are kept when the 304 does not repeat them
    assert out.etag == '"abc"' and out.last_modified == "Mon, 02 Nov 2026 12:00:00 GMT"


@respx.mock
async def test_304_with_new_etag_updates_it():
    respx.get(URL).mock(return_value=httpx.Response(304, headers={"ETag": '"def"'}))
    out = await conditional_get(URL, etag='"abc"')
    assert out.not_modified and out.etag == '"def"'


@respx.mock
async def test_403_is_blocked_not_raised():
    respx.get(URL).mock(return_value=httpx.Response(403, text="Forbidden"))
    out = await conditional_get(URL, etag='"old"')
    assert not out.ok and out.blocked is True and out.status_code == 403
    assert out.error == "HTTP 403: blocked by anti-bot/WAF" and out.body is None
    assert out.etag == '"old"'  # a blocked answer never overwrites validators


@respx.mock
async def test_captcha_page_with_200_is_blocked():
    respx.get(URL).mock(return_value=httpx.Response(200, text="<title>Just a moment...</title> cf-chl"))
    out = await conditional_get(URL)
    assert out.blocked and not out.ok


@respx.mock
async def test_500_is_an_error_with_status_code():
    respx.get(URL).mock(return_value=httpx.Response(503, text="maintenance"))
    out = await conditional_get(URL)
    assert not out.ok and out.blocked is False and out.status_code == 503 and out.error == "HTTP 503"


@respx.mock
async def test_timeout_and_connect_error_become_outcomes():
    respx.get(URL).mock(side_effect=httpx.ReadTimeout("slow"))
    out = await conditional_get(URL, timeout=5)
    assert not out.ok and out.status_code is None and out.error == "timeout after 5s"
    respx.get(URL).mock(side_effect=httpx.ConnectError("refused"))
    out = await conditional_get(URL)
    assert not out.ok and out.error.startswith("ConnectError")


@respx.mock
async def test_oversized_body_is_rejected():
    respx.get(URL).mock(return_value=httpx.Response(200, content=b"x" * 5_000_001))
    out = await conditional_get(URL)
    assert not out.ok and out.error.startswith("body too large")


@respx.mock
async def test_shared_client_and_redirect_follow():
    respx.get(URL).mock(return_value=httpx.Response(302, headers={"Location": URL + "/es"}))
    respx.get(URL + "/es").mock(return_value=httpx.Response(200, text="ok"))
    async with httpx.AsyncClient(follow_redirects=True) as client:
        out = await conditional_get(URL, client=client)
    assert out.ok and out.url == URL + "/es" and out.body == "ok"


def test_helpers():
    assert conditional_headers(None, None) == {}
    assert conditional_headers('"a"', "lm") == {"If-None-Match": '"a"', "If-Modified-Since": "lm"}
    assert looks_blocked(429, "") and looks_blocked(200, "Attention Required! | Cloudflare")
    assert not looks_blocked(200, "<html>cotizaciones</html>") and not looks_blocked(404, "captcha")


@pytest.mark.parametrize("code", [401, 403, 429])
@respx.mock
async def test_all_antibot_codes_are_blocked(code):
    respx.get(URL).mock(return_value=httpx.Response(code))
    assert (await conditional_get(URL)).blocked
