"""Offline tests for the discovery run (fake capture, mock HTTP), the adapter scaffold and the CLI guards."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from fronteira_fx.discover import cli
from fronteira_fx.discover.capture import Captured, CaptureResult
from fronteira_fx.discover.probe import (
    ThrottleError,
    _safe_url,
    build_candidates,
    check_throttle,
    record_visit,
    replay_once,
    run_discovery,
    skipped_summary,
    to_json_text,
)
from fronteira_fx.discover.redact import split_headers
from fronteira_fx.discover.scaffold import ScaffoldError, scaffold
from fronteira_fx.discover.urlguard import UnsafeUrl

RESOLVER = lambda host: ["93.184.216.34"]  # noqa: E731  (no DNS in tests)

BOARD = b'{"villamorra": [{"bcp": "USD", "compra": "5.800", "venta": "5.920", "contato": "ana@exemplo.com"}]}'


def _rec(url, body=b"", *, ctype="application/json", method="GET", headers=None, post=None, rtype="fetch"):
    # capture.py splits headers before the record exists; mirror that here.
    kept, omitted = split_headers(headers or {"accept": "application/json"})
    return Captured(
        method=method,
        url=url,
        resource_type=rtype,
        request_headers=kept,
        omitted_headers=omitted,
        post_data=post,
        status=200,
        content_type=ctype,
        body=body,
    )


def test_safe_url_masks_secret_query_values():
    out = _safe_url("https://site.example/api?suc=villamorra&token=abc")
    assert "suc=villamorra" in out and "abc" not in out and "<redigido>" in out


def test_build_candidates_filters_analytics_and_binaries_and_ranks():
    recs = [
        _rec("https://site.example/api/board", BOARD),
        _rec("https://www.google-analytics.com/collect", BOARD),
        _rec("https://site.example/logo.png", b"\x89PNG", ctype="image/png", rtype="fetch"),
        _rec("https://site.example/ok", b"Bem-vindo", ctype="text/plain"),
    ]
    cands = build_candidates(recs)
    assert [c["url"] for c in cands][0] == "https://site.example/api/board"
    assert all("google-analytics" not in c["url"] for c in cands)
    assert all(c["content_type"] != "image/png" for c in cands)
    assert cands[0]["rank"] == 1 and cands[0]["score"] > 0
    assert "ana@exemplo" not in json.dumps([c["excerpt"] for c in cands])


def test_replay_once_sends_no_cookie_and_reports_success():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["cookie"] = request.headers.get("cookie")
        return httpx.Response(200, json={"villamorra": [{"bcp": "USD", "compra": "5.800", "venta": "5.920"}]})

    cand = build_candidates([_rec("https://site.example/api/board", BOARD)])[0]
    out = replay_once(cand, resolver=RESOLVER, transport=httpx.MockTransport(handler))
    assert out["works_without_browser"] is True and out["status"] == 200
    assert seen["cookie"] is None


def test_replay_skips_non_ascii_header_values_and_never_raises():
    cand = build_candidates([_rec("https://site.example/api/board", BOARD,
                                  headers={"accept": "application/json", "x-note": "Asunción"})])[0]
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["x-note"] = request.headers.get("x-note")
        return httpx.Response(200, content=BOARD)

    out = replay_once(cand, resolver=RESOLVER, transport=httpx.MockTransport(handler))
    assert out["works_without_browser"] is True
    assert out["headers_not_replayed"] == ["x-note"] and seen["x-note"] is None


def test_replay_once_reports_blocked_as_failure():
    cand = build_candidates([_rec("https://site.example/api/board", BOARD)])[0]
    out = replay_once(cand, resolver=RESOLVER, transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    assert out["works_without_browser"] is False and out["status"] == 403


def test_replay_refuses_private_target_without_request():
    cand = build_candidates([_rec("http://10.0.0.2/api", BOARD)])[0]
    out = replay_once(cand, resolver=RESOLVER, transport=httpx.MockTransport(lambda r: pytest.fail("no request")))
    assert out["works_without_browser"] is False and "recusada" in out["error"]


def _fake_capture(records):
    async def capture_fn(url, *, seconds, user_agent):
        return CaptureResult(final_url=url, title="Tablero", requests_seen=len(records), blocked_urls=0,
                             records=records)

    return capture_fn


async def test_run_discovery_report_is_clean_and_throttled(tmp_path: Path):
    state = tmp_path / "visits.json"
    records = [_rec("https://site.example/api/board?token=segredo", BOARD, headers={
        "accept": "application/json", "cookie": "sid=segredo", "x-csrf-token": "t"})]
    replay = httpx.MockTransport(lambda r: httpx.Response(200, content=BOARD))
    report = await run_discovery("https://site.example/", seconds=5, state_file=state, resolver=RESOLVER,
                                 replay_transport=replay, capture_fn=_fake_capture(records))
    text = to_json_text(report)
    assert "segredo" not in text and "sid=" not in text and "ana@exemplo" not in text
    assert "candidates_internal" not in text
    top = report["candidates"][0]
    assert top["omitted_headers"] == ["cookie", "x-csrf-token"]
    assert "x-csrf-token" not in top["required_headers"]
    assert top["replay"]["works_without_browser"] is True
    assert report["tool"] == "fx-discover"

    with pytest.raises(ThrottleError):
        await run_discovery("https://site.example/outra", seconds=5, state_file=state, resolver=RESOLVER,
                            capture_fn=_fake_capture(records))


async def test_run_discovery_refuses_unsafe_url_before_any_visit():
    async def never(url, **kwargs):  # pragma: no cover - must not run
        pytest.fail("visit must not happen")

    with pytest.raises(UnsafeUrl):
        await run_discovery("http://127.0.0.1:8000/", capture_fn=never)


def test_skipped_summary_counts_dropped_xhr_without_urls():
    recs = [
        _rec("https://site.example/api/a", b"", ctype="application/json"),
        _rec("https://site.example/api/b", b"\x00\x01", ctype="application/octet-stream"),
        _rec("https://www.google-analytics.com/c", BOARD),
        _rec("https://site.example/api/ok", BOARD),
    ]
    notes = skipped_summary(recs)
    assert notes == ["respostas XHR/fetch descartadas: 1 analytics, 1 binario, 1 sem corpo"]
    assert "site.example" not in notes[0]


def test_user_agent_is_ascii_so_it_can_be_replayed():
    from fronteira_fx.discover.probe import USER_AGENT

    assert USER_AGENT.isascii()


def test_throttle_is_per_host(tmp_path: Path):
    state = tmp_path / "visits.json"
    record_visit(state, "https://a.example/x", now=1000.0)
    check_throttle(state, "https://b.example/x", now=1001.0)  # other host: fine
    with pytest.raises(ThrottleError):
        check_throttle(state, "https://a.example/y", now=1030.0)
    check_throttle(state, "https://a.example/y", now=1061.0)


def _cand(body: bytes, ctype: str = "application/json"):
    return {
        "method": "GET", "url": "https://site.example/api/board", "content_type": ctype, "score": 80,
        "reasons": ["moedas USD (+10)"], "required_headers": {"accept": "application/json"},
        "replay": {"works_without_browser": True}, "_body": body,
    }


def test_scaffold_writes_unregistered_skeleton_fixture_and_failing_test(tmp_path: Path):
    adapters = tmp_path / "adapters"
    fixtures = tmp_path / "fixtures"
    tests = tmp_path / "tests"
    paths = scaffold("casanova", _cand(BOARD), adapters_dir=adapters, fixtures_dir=fixtures, tests_dir=tests,
                     existing_ids={"chaco"})
    src = paths.adapter.read_text(encoding="utf-8")
    compile(src, str(paths.adapter), "exec")  # syntactically valid python
    assert "id='casanova'" in src and "class CasanovaAdapter" in src and "TODO" in src
    assert "integration='endpoint_interno'" in src and "NÃO REGISTRADO" in src
    fixture = paths.fixture.read_text(encoding="utf-8")
    assert "ana@exemplo" not in fixture and "<email>" in fixture
    test_src = paths.test.read_text(encoding="utf-8")
    assert "assert result.quotes" in test_src and "TODO" in test_src
    assert paths.fixture.name == "casanova.json"


def test_scaffold_refuses_bad_or_existing_ids_and_overwrites(tmp_path: Path):
    kwargs = dict(adapters_dir=tmp_path / "a", fixtures_dir=tmp_path / "f", tests_dir=tmp_path / "t")
    with pytest.raises(ScaffoldError):
        scaffold("Bad Id", _cand(BOARD), existing_ids=set(), **kwargs)
    with pytest.raises(ScaffoldError):
        scaffold("chaco", _cand(BOARD), existing_ids={"chaco"}, **kwargs)
    scaffold("casanova", _cand(BOARD), existing_ids=set(), **kwargs)
    with pytest.raises(ScaffoldError):
        scaffold("casanova", _cand(BOARD), existing_ids=set(), **kwargs)


def test_scaffold_html_candidate_uses_html_integration(tmp_path: Path):
    html = b"<html><table><tr><td>USD</td><td>5.800</td></tr></table></html>"
    paths = scaffold("pagina", _cand(html, "text/html"), adapters_dir=tmp_path / "a", fixtures_dir=tmp_path / "f",
                     tests_dir=tmp_path / "t", existing_ids=set())
    src = paths.adapter.read_text(encoding="utf-8")
    assert "integration='html'" in src and "method='html'" in src and "ACCEPT_HTML" in src
    assert paths.fixture.name == "pagina.html"


def test_cli_refuses_unsafe_url_with_exit_2(capsys):
    assert cli.main(["http://127.0.0.1/"]) == 2
    assert "recusada" in capsys.readouterr().err


def test_cli_parser_defaults():
    args = cli.build_parser().parse_args(["https://site.example/", "--scaffold", "casanova"])
    assert args.seconds == 20.0 and args.scaffold == "casanova" and args.out is None
