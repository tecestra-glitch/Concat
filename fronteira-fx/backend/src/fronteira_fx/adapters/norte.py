"""Norte Cambios S.A.E.C.A. (https://www.nortecambios.com.py/, Pedro Juan Caballero).

Laravel + Livewire. The home page renders the rate table of the *active* branch
(Pedro Juan Caballero by default) and a ``wire:snapshot`` JSON with
``activeBranchId`` and ``latestUpdate``. The other branches are loaded by a
Livewire call (``POST /livewire/update`` with the page's CSRF token, the component
snapshot and ``setActiveBranch(<id>)``); `fetch()` replays that for the requested
branches, reusing the session cookie of the GET.

TLS: the server sends only its leaf certificate (missing Sectigo intermediate),
so default verification fails. Policy (never silently insecure):

* ``FX_NORTE_CA_BUNDLE=/path/bundle.pem``  -> verify against that bundle (system CAs +
  the Sectigo "Public Server Authentication CA DV R36" intermediate works);
* ``FX_NORTE_INSECURE=1``                   -> verification disabled, flagged in the message;
* otherwise a TLS failure returns ``AdapterStatus.ERROR`` with
  "TLS chain invalid; set FX_NORTE_CA_BUNDLE or allow insecure explicitly".
"""
from __future__ import annotations

import html as htmllib
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any

import httpx
from dateutil import parser as dtparser
from selectolax.lexbor import LexborHTMLParser

from ._common import (
    BranchInfo,
    as_text,
    city_from_text,
    error_result,
    finalize,
    payload_kind,
    quotes_excerpt,
)
from ._http import (
    ACCEPT_JSON,
    DEFAULT_TIMEOUT,
    build_evidence,
    default_headers,
    http_get,
    http_post,
    positive_or_none,
    try_parse_decimal,
    utcnow,
)
from .base import AdapterInfo, AdapterResult, AdapterStatus, QuoteDraft

BASE = "https://www.nortecambios.com.py"
HOME_URL = f"{BASE}/"
LIVEWIRE_URL = f"{BASE}/livewire/update"
COMPONENT_NAME = "rates-board"
TLS_MESSAGE = "TLS chain invalid; set FX_NORTE_CA_BUNDLE or allow insecure explicitly"

RULE_HTML = "norte html v1 (table tbody tr: td[0] last span=ISO, td[1]/td[2] p own text; wire:snapshot latestUpdate)"
RULE_LIVEWIRE = "norte livewire v1 (POST livewire/update setActiveBranch -> components[0].effects.html)"

KNOWN_BRANCHES: dict[str, BranchInfo] = {
    "1": BranchInfo("norte-1", "Pedro Juan Caballero", "PJC", "1"),
    "2": BranchInfo("norte-2", "Asunción", "ASU", "2"),
    "3": BranchInfo("norte-3", "Ciudad del Este", "CDE", "3"),
    "4": BranchInfo("norte-4", "Bella Vista Norte", None, "4"),
    "5": BranchInfo("norte-5", "Capitán Bado", None, "5"),
    "6": BranchInfo("norte-6", "Concepción", None, "6"),
}
DEFAULT_EXTRA_BRANCHES: tuple[str, ...] = ("2", "3")   # ASU, CDE (PJC is the page default)
CURRENCIES: frozenset[str] = frozenset({"USD", "BRL"})

_TAB_RE = re.compile(r"setActiveBranch\((\d+)\)\"[^>]*>\s*([^<]+?)\s*<")
_ISO_RE = re.compile(r"^[A-Z]{3}$")
CROSS_LABEL = "BRL•USD"  # linha do quadro: BRL por 1 USD (cruzamento publicado pela casa)


def tls_verify_setting() -> tuple[bool | str, str | None]:
    """(httpx `verify` value, warning note) from the environment."""
    bundle = os.environ.get("FX_NORTE_CA_BUNDLE", "").strip()
    if bundle:
        return bundle, None
    if os.environ.get("FX_NORTE_INSECURE", "").strip() == "1":
        return False, "TLS verification DISABLED (FX_NORTE_INSECURE=1)"
    return True, None


def _branches_from_html(text: str) -> dict[str, BranchInfo]:
    branches = dict(KNOWN_BRANCHES)
    for bid, name in _TAB_RE.findall(text):
        name = htmllib.unescape(name).strip()
        branches[bid] = BranchInfo(f"norte-{bid}", name, city_from_text(name), bid)
    return branches


def _snapshot(tree: LexborHTMLParser) -> tuple[str | None, dict[str, Any] | None]:
    """Raw (unescaped) snapshot string of the rates-board component and its parsed JSON."""
    for node in tree.css("[wire\\:snapshot]"):
        raw = node.attributes.get("wire:snapshot") or ""
        if f'"name":"{COMPONENT_NAME}"' in raw:
            try:
                return raw, json.loads(raw)
            except ValueError:
                return raw, None
    return None, None


def _parse_rows(tree: LexborHTMLParser) -> tuple[list[tuple[str, Any, Any]], list[str]]:
    rows: list[tuple[str, Any, Any]] = []
    issues: list[str] = []
    for tr in tree.css("table tbody tr"):
        cells = tr.css("td")
        if len(cells) != 3:
            continue
        spans = cells[0].css("span")
        iso = spans[-1].text(strip=True) if spans else cells[0].text(strip=True)
        if not _ISO_RE.match(iso) and iso != CROSS_LABEL:
            continue  # other cross rates like "EUR•USD" or "USD CH" are not used
        buy_p, sell_p = cells[1].css_first("p"), cells[2].css_first("p")
        buy = positive_or_none(try_parse_decimal(buy_p.text(deep=False), "es_PY")) if buy_p else None
        sell = positive_or_none(try_parse_decimal(sell_p.text(deep=False), "es_PY")) if sell_p else None
        if iso in CURRENCIES and buy is None and sell is None:
            issues.append(f"{iso}: no prices in row")
            continue
        rows.append((iso, buy, sell))
    return rows, issues


class NorteAdapter:
    info = AdapterInfo(
        id="norte",
        name="Norte Cambios",
        kind="exchange_house",
        method="html",
        integration="html",
        url=HOME_URL,
        capabilities=["branch_table", "buy_sell", "usd_pyg", "brl_pyg", "declared_update_ts", "livewire_branches"],
        limitations=[
            "cadeia TLS incompleta no servidor: exige FX_NORTE_CA_BUNDLE (CAs do sistema + intermediária "
            "Sectigo DV R36) ou FX_NORTE_INSECURE=1 explícito; sem isso fetch() devolve ERROR",
            "só a filial ativa (Pedro Juan Caballero) vem no HTML; as outras exigem replay Livewire (token/cookie)",
            "cotação de balcão indicativa; valor efetivo depende do montante e da filial",
        ],
        cities=["PJC", "ASU", "CDE"],
        currencies=["USD", "BRL", "PYG"],
        poll_interval_s=300,
        allowed_domains=["www.nortecambios.com.py"],
    )
    stale_after = timedelta(hours=36)

    # ------------------------------------------------------------------ fetch
    async def fetch(self, *, branch_ids: list[str] | None = None, **params: Any) -> AdapterResult:  # noqa: ARG002
        captured_at = utcnow()
        verify, warning = tls_verify_setting()
        notes: list[str] = [warning] if warning else []
        headers = default_headers()
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, verify=verify, follow_redirects=True) as client:
            out = await http_get(HOME_URL, headers=headers, client=client)
            if not out.ok:
                if out.tls_error:
                    return AdapterResult(status=AdapterStatus.ERROR, quotes=[], evidence=None,
                                         message=f"{TLS_MESSAGE} ({out.error})")
                return out.failure(self.info.id)
            result = self.parse(out.text, captured_at=captured_at, url=out.url)
            if result.status in (AdapterStatus.ERROR, AdapterStatus.BLOCKED):
                return result
            # STALE is recomputed by finalize() over all quotes; only carry real issues forward
            issues: list[str] = [result.message] if result.message and result.status != AdapterStatus.STALE else []
            quotes = list(result.quotes)

            tree = LexborHTMLParser(out.text)
            csrf_node = tree.css_first("[data-csrf]")
            token = csrf_node.attributes.get("data-csrf") if csrf_node else None
            snapshot_raw, snapshot = _snapshot(tree)
            active = str((snapshot or {}).get("data", {}).get("activeBranchId", "1"))
            requested = branch_ids or DEFAULT_EXTRA_BRANCHES
            wanted = [str(b) for b in requested if str(b) != active]
            branches = _branches_from_html(out.text)
            if wanted and (not token or not snapshot_raw):
                issues.append("livewire token/snapshot not found; other branches skipped")
                wanted = []
            for bid in wanted:
                body = {
                    "_token": token,
                    "components": [{
                        "snapshot": snapshot_raw,
                        "updates": {},
                        "calls": [{"path": "", "method": "setActiveBranch", "params": [int(bid)]}],
                    }],
                }
                lw = await http_post(
                    LIVEWIRE_URL, json=body, client=client,
                    headers=default_headers(ACCEPT_JSON, {"X-Livewire": "1", "Referer": HOME_URL,
                                                          "Content-Type": "application/json"}),
                )
                if not lw.ok:
                    issues.append(f"branch {bid}: livewire {lw.error}")
                    continue
                sub = self.parse(lw.text, captured_at=captured_at, url=LIVEWIRE_URL, branch_id=bid,
                                 branches=branches)
                if sub.quotes:
                    quotes.extend(sub.quotes)
                if sub.message and sub.status != AdapterStatus.STALE:
                    issues.append(f"branch {bid}: {sub.message}")
        evidence = build_evidence(
            source_id=self.info.id, kind="html", url=HOME_URL, captured_at=captured_at, raw=out.text,
            rules=[RULE_HTML, RULE_LIVEWIRE], excerpt_text=quotes_excerpt(quotes, header="home + livewire branches"),
        )
        return finalize(quotes=quotes, evidence=evidence, issues=issues, notes=notes, captured_at=captured_at,
                        stale_after=self.stale_after)

    # ------------------------------------------------------------------ parse
    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:
        kind = payload_kind(raw)
        text = as_text(raw)
        if kind == "empty":
            return error_result("empty payload")
        branches: dict[str, BranchInfo] = params.get("branches") or dict(KNOWN_BRANCHES)
        forced_branch: str | None = str(params["branch_id"]) if params.get("branch_id") is not None else None
        rules = [RULE_HTML]
        if kind == "json":
            try:
                data = json.loads(text)
                fragment = data["components"][0]["effects"]["html"]
            except (ValueError, KeyError, IndexError, TypeError) as exc:
                return error_result(f"livewire response without components[0].effects.html ({type(exc).__name__})")
            if not isinstance(fragment, str) or not fragment.strip():
                return error_result("livewire response has an empty html effect")
            text = fragment
            rules = [RULE_LIVEWIRE]
        tree = LexborHTMLParser(text)
        if forced_branch is None:
            branches = {**branches, **_branches_from_html(text)}
        snapshot_raw, snapshot = _snapshot(tree)
        data_part = (snapshot or {}).get("data") or {}
        branch_code = forced_branch or str(data_part.get("activeBranchId") or "1")
        binfo = branches.get(branch_code) or BranchInfo(
            f"norte-{branch_code}", f"Sucursal {branch_code}", None, branch_code
        )
        declared: datetime | None = None
        latest = data_part.get("latestUpdate")
        if isinstance(latest, list) and latest:
            latest = latest[0]
        if isinstance(latest, str):
            try:
                declared = dtparser.isoparse(latest)
            except (ValueError, TypeError):
                pass
        rows, issues = _parse_rows(tree)
        if not rows:
            return error_result("rate table not found (table tbody tr with 3 cells); layout changed?")
        quotes: list[QuoteDraft] = []
        seen: set[str] = set()
        for iso, buy, sell in rows:
            if iso == CROSS_LABEL:
                if buy is not None and sell is not None:
                    quotes.append(
                        QuoteDraft(
                            source_id=self.info.id, base="USD", quote="BRL", buy=buy, sell=sell,  # type: ignore[arg-type]
                            unit_note="BRL por 1 USD (cruzado Real•Dólar)", modality="cash", kind="indicative",
                            channel="physical", city=binfo.city, branch_id=binfo.id,
                            context={"board": "cruzado", "pair": "USD x BRL"}, declared_updated_at=declared,
                        )
                    )
                continue
            if iso not in CURRENCIES:
                continue
            seen.add(iso)
            quotes.append(
                QuoteDraft(
                    source_id=self.info.id, base=iso, quote="PYG", buy=buy, sell=sell,  # type: ignore[arg-type]
                    unit_note=f"PYG por 1 {iso}", modality="cash", kind="indicative", channel="physical",
                    city=binfo.city, branch_id=binfo.id, declared_updated_at=declared,
                )
            )
        for missing in sorted(CURRENCIES - seen):
            issues.append(f"{binfo.name}: missing {missing}")
        evidence = build_evidence(
            source_id=self.info.id, kind="html", url=url, captured_at=captured_at, raw=text, rules=rules,
            excerpt_text=quotes_excerpt(quotes, header=f"branch {binfo.name} (id {branch_code})"),
        )
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)


adapter = NorteAdapter()
