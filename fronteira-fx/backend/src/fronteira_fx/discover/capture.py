"""One headless visit with Playwright: records XHR/fetch/document traffic. No login, no stored cookies.

The context is ephemeral (nothing is written to disk) and is closed at the end. Every request the browser
makes goes through `check_public_url`, so redirects and sub-resources cannot reach private addresses.
Waits are explicit (a fixed time after DOMContentLoaded); `networkidle` is never used because pages keep streams open.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .redact import split_headers
from .urlguard import UnsafeUrl, check_public_url

RECORDED_TYPES = frozenset({"xhr", "fetch", "document"})
MAX_RECORDS = 300
MAX_BODY_BYTES = 1_000_000
MAX_POST_CHARS = 4_000


@dataclass(slots=True)
class Captured:
    method: str
    url: str
    resource_type: str
    request_headers: dict[str, str]          # already split: only replayable headers
    omitted_headers: list[str]               # names only (cookies, tokens...)
    post_data: str | None
    status: int | None = None
    content_type: str | None = None
    body: bytes = b""
    body_truncated: bool = False
    error: str | None = None
    notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CaptureResult:
    final_url: str
    title: str
    requests_seen: int
    blocked_urls: int
    records: list[Captured]


def _proxy_from_env() -> dict[str, str] | None:
    server = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    return {"server": server} if server else None


async def capture(url: str, *, seconds: float, user_agent: str, timeout_ms: int = 30_000) -> CaptureResult:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise RuntimeError("playwright não instalado: rode `uv sync --all-extras --dev`") from exc

    checked: dict[str, bool] = {}

    def public(target: str) -> bool:
        from urllib.parse import urlsplit

        host = urlsplit(target).hostname or ""
        if host not in checked:
            try:
                check_public_url(target)
                checked[host] = True
            except UnsafeUrl:
                checked[host] = False
        return checked[host]

    blocked = 0
    seen = 0
    pairs: list[tuple[Any, Any]] = []  # (request, response) for document/xhr/fetch
    async with async_playwright() as pw:
        # FX_DISCOVER_CHROMIUM: optional path to an already-installed headless Chromium (when the bundled
        # build of the installed Playwright is not in PLAYWRIGHT_BROWSERS_PATH).
        browser = await pw.chromium.launch(
            headless=True,
            proxy=_proxy_from_env(),
            executable_path=os.environ.get("FX_DISCOVER_CHROMIUM") or None,
        )
        try:
            context = await browser.new_context(
                user_agent=user_agent,
                service_workers="block",
                accept_downloads=False,
                locale="es-PY",
            )

            async def guard(route: Any) -> None:
                nonlocal blocked
                if public(route.request.url):
                    await route.continue_()
                else:
                    blocked += 1
                    await route.abort()

            await context.route("**/*", guard)
            page = await context.new_page()

            def on_response(response: Any) -> None:
                nonlocal seen
                req = response.request
                seen += 1
                if req.resource_type in RECORDED_TYPES and len(pairs) < MAX_RECORDS:
                    pairs.append((req, response))

            page.on("response", on_response)
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            await page.wait_for_timeout(int(seconds * 1000))
            title = await page.title()
            final_url = page.url

            records: list[Captured] = []
            for req, resp in pairs:
                headers, omitted = split_headers(dict(req.headers))
                rec = Captured(
                    method=req.method,
                    url=req.url,
                    resource_type=req.resource_type,
                    request_headers=headers,
                    omitted_headers=omitted,
                    post_data=(req.post_data or None) and (req.post_data or "")[:MAX_POST_CHARS],
                    status=resp.status,
                    content_type=(resp.headers.get("content-type") or "").split(";")[0].strip().lower() or None,
                )
                try:
                    body = await resp.body()
                    rec.body_truncated = len(body) > MAX_BODY_BYTES
                    rec.body = body[:MAX_BODY_BYTES]
                except Exception as exc:  # redirects, evicted bodies, aborted requests
                    rec.error = f"corpo indisponível: {type(exc).__name__}"
                records.append(rec)
            await context.close()
        finally:
            await browser.close()
    return CaptureResult(final_url=final_url, title=title, requests_seen=seen, blocked_urls=blocked, records=records)
