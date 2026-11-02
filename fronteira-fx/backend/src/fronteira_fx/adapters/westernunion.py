"""Western Union — BR -> PY price simulator (https://www.westernunion.com/br/pt/web/send-money/start).

Browser-only: the page is an Angular SPA whose quote (receive amount, fee,
exchange rate, delivery time, promo) only appears after choosing the destination
country, typing the amount and picking a receive method + payment method. The
price itself comes from ``POST /wuconnect/prices/catalog`` with a browser
fingerprint, so there is no reproducible plain-HTTP request; `fetch()` drives
headless Chromium through Playwright (optional extra ``browser``) with explicit
waits on specific elements (never ``networkidle``) and stores a full-page
screenshot under ``backend/var/evidence/`` (gitignored) as evidence.

Flow observed 2026-11-02 (pt-BR):
  1. ``button[amplitude-id="tile-country-selection"]`` with text "Paraguai"
  2. ``#txtSendAmount`` (BRL), ``#wu-currency-select`` (PYG/USD), ``#txtReceiveAmount``
  3. receive tiles ``[amplitude-id="tile-fundsout-ba"]`` (Conta Bancaria) /
     ``[amplitude-id="tile-fundsout-ag"]`` (Receber em dinheiro em uma loja)
  4. payment tile ``[amplitude-id="tile-fundsin-wupay"]`` ("PIX ou transferência bancária")
  5. summary text: "1.00 BRL = 1,080.3741 PYG", "Taxa de transferência + 0.00 BRL",
     "100% de desconto 45.00 BRL", "Tempo de atendimento: 0-4 Dias úteis".

Every quote is amount- and context-dependent. The context (origin, destination,
currencies, amount, payment, receive, bank, channel, promo) is stored in
``QuoteDraft.context`` and never mixed between scenarios.

`parse()` is pure: it takes the JSON "scenario" document that `fetch()` extracts
from the page (or the historical test fixture) and returns the quotes. Payloads
flagged ``historical`` are never reported as OK: they come back STALE.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any, Literal

from dateutil import parser as dtparser

from ._common import as_text, error_result, finalize, payload_kind, quotes_excerpt
from ._http import USER_AGENT, build_evidence, sha256_hex, try_parse_decimal, utcnow
from .base import AdapterInfo, AdapterResult, AdapterStatus, Fee, QuoteDraft

START_URL = "https://www.westernunion.com/br/pt/web/send-money/start"
RULE_JSON = "westernunion scenario v1 (receive_amount_pyg / amount_brl = PYG por 1 BRL; fee/delivery/promo in context)"
RULE_BROWSER = (
    "westernunion browser v1 (tile Paraguai > #txtSendAmount > tile-fundsout-* > tile-fundsin-* > "
    "#txtReceiveAmount + resumo)"
)

Payment = Literal["pix", "bank_transfer", "card"]
Receive = Literal["bank_account", "cash_pickup"]

# Stable hooks first (amplitude-id / element ids), visible pt-BR labels as fallback.
RECEIVE_TILES: dict[str, tuple[str, ...]] = {
    "bank_account": ('[amplitude-id="tile-fundsout-ba"]', "#fundsOut_BA"),
    "cash_pickup": ('[amplitude-id="tile-fundsout-ag"]', "#fundsOut_AG"),
}
RECEIVE_LABELS: dict[str, tuple[str, ...]] = {
    "bank_account": ("conta bancaria", "conta bancária", "bank account"),
    "cash_pickup": ("receber em dinheiro", "em uma loja", "cash pickup"),
}
PAYMENT_TILES: dict[str, tuple[str, ...]] = {
    "pix": ('[amplitude-id="tile-fundsin-wupay"]', "#fundsIn_WUPay"),
    "bank_transfer": ('[amplitude-id="tile-fundsin-wupay"]', "#fundsIn_WUPay"),
    "card": ('[amplitude-id="tile-fundsin-cc"]', '[amplitude-id="tile-fundsin-dc"]',
             '[amplitude-id^="tile-fundsin-c"]'),
}
PAYMENT_LABELS: dict[str, tuple[str, ...]] = {
    "pix": ("pix",),
    "bank_transfer": ("transferência bancária", "transferencia bancaria", "bank transfer"),
    "card": ("cartão", "cartao", "card"),
}
SELECTORS = {
    "country_tile": 'button[amplitude-id="tile-country-selection"]',
    "send_amount": "#txtSendAmount",
    "receive_amount": "#txtReceiveAmount",
    "currency_select": "#wu-currency-select",
    "cookie_close": "button.onetrust-close-btn-handler, #onetrust-accept-btn-handler",
}
_Q4 = Decimal("0.0001")
_FEE_RE = re.compile(r"(?:taxa\s+de\s+transfer[êe]ncia|tarifa)\d*[^0-9]{0,20}?([0-9][0-9.,]*)\s*BRL", re.I)
_LIST_FEE_RE = re.compile(r"\d+\s?%\s+(?:de\s+)?desconto\s+([0-9][0-9.,]*)\s*BRL", re.I)
_RATE_RE = re.compile(r"1[.,]00\s*BRL\s*=\s*([0-9][0-9.,]*)\s*(?:PYG|Paraguay)", re.I)
_DELIVERY_RE = re.compile(
    r"(em\s+minutos|minutos|\d+\s*[–-]\s*\d+\s+dias?\s+[úu]teis|\d+\s+dias?\s+[úu]te(?:is|il)|mesmo\s+dia|"
    r"pr[óo]ximo\s+dia\s+[úu]til)",
    re.I,
)
_PROMO_RE = re.compile(
    r"(\d+\s?%\s+(?:de\s+)?desconto(?:\s+(?:na\s+)?tarifa)?(?:\s+[0-9][0-9.,]*\s*BRL)?|tarifa\s+zero[^|]{0,40})", re.I
)
_BLOCK_WORDS = ("access denied", "captcha", "unusual traffic", "pardon our interruption", "request blocked")


def evidence_dir() -> Path:
    override = os.environ.get("FX_EVIDENCE_DIR", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "var" / "evidence"


def _chromium_executable() -> str | None:
    """Explicit path from FX_PW_CHROMIUM, else the pre-provisioned binary when present."""
    for candidate in (os.environ.get("FX_PW_CHROMIUM", "").strip(), "/opt/pw-browsers/chromium"):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def extract_summary(body_text: str) -> dict[str, Any]:
    """Pull fee / rate / delivery / promo out of the page's visible text (pure, testable)."""
    text = re.sub(r"\s+", " ", body_text)
    out: dict[str, Any] = {}
    m = _FEE_RE.search(text)
    out["fee_brl"] = str(try_parse_decimal(m.group(1))) if m and try_parse_decimal(m.group(1)) is not None else None
    m = _LIST_FEE_RE.search(text)
    out["fee_before_discount_brl"] = str(try_parse_decimal(m.group(1))) if m else None
    m = _RATE_RE.search(text)
    out["exchange_rate"] = m.group(1) if m else None
    summary = text[text.find("RESUMO"):] if "RESUMO" in text else text
    m = _DELIVERY_RE.search(summary) or _DELIVERY_RE.search(text)
    out["delivery"] = m.group(1).strip() if m else None
    m = _PROMO_RE.search(text)
    out["promo"] = m.group(1).strip() if m else None
    out["summary_text"] = summary[:1500]
    return out


class WesternUnionAdapter:
    info = AdapterInfo(
        id="westernunion",
        name="Western Union (BR → PY)",
        kind="remittance",
        method="browser",
        url=START_URL,
        capabilities=["simulator_brl_pyg", "amount_dependent", "receive_methods", "fees", "delivery_time", "promo",
                      "screenshot_evidence"],
        limitations=[
            "só via navegador (Playwright, extra `browser`); o preço vem de POST wuconnect/prices/catalog com "
            "fingerprint, sem request HTTP reproduzível",
            "cotação indicativa do simulador público; o valor final é confirmado só no checkout logado",
            "cada combinação (montante, pagamento, recebimento, banco, promo) é um contexto distinto; nunca misturar",
            "seletores do SPA podem mudar: falhas devolvem DEGRADED/BLOCKED com o motivo, nunca números inventados",
            "pix e bank_transfer compartilham o mesmo tile ('PIX ou transferência bancária'); cartão só se o tile "
            "existir",
        ],
        cities=[],
        currencies=["BRL", "PYG"],
        poll_interval_s=1800,
        allowed_domains=["www.westernunion.com"],
    )
    stale_after = timedelta(hours=6)
    step_timeout_ms = 30_000

    # ------------------------------------------------------------------ parse (pure)
    def parse(self, raw: str | bytes, *, captured_at: datetime, url: str, **params: Any) -> AdapterResult:
        if payload_kind(raw) == "empty":
            return error_result("empty payload")
        text = as_text(raw)
        if payload_kind(raw) == "html":
            return AdapterResult(status=AdapterStatus.DEGRADED, quotes=[], evidence=None,
                                 message="HTML payload: the WU quote only exists after browser interaction; "
                                         "parse() needs the scenario JSON extracted by fetch()")
        try:
            data = json.loads(text)
        except ValueError as exc:
            return error_result(f"invalid JSON: {exc}")
        scenarios: list[dict[str, Any]]
        historical = False
        note = ""
        if isinstance(data, dict) and isinstance(data.get("scenarios"), list):
            scenarios = [s for s in data["scenarios"] if isinstance(s, dict)]
            historical = bool(data.get("historical"))
            note = str(data.get("note") or "")
        elif isinstance(data, dict) and "receive_amount_pyg" in data:
            scenarios = [data]
            historical = bool(data.get("historical"))
            note = str(data.get("note") or "")
        elif isinstance(data, list):
            scenarios = [s for s in data if isinstance(s, dict)]
        else:
            return error_result("JSON is not a WU scenario document")
        if any(k in note.lower() for k in ("historical", "histórico", "historico")):
            historical = True
        if not scenarios:
            return error_result("no scenarios in payload")

        issues: list[str] = []
        quotes: list[QuoteDraft] = []
        doc_captured = data.get("captured_at") if isinstance(data, dict) else None
        for sc in scenarios:
            amount = try_parse_decimal(sc.get("amount_brl"))
            received = try_parse_decimal(sc.get("receive_amount_pyg"))
            if amount is None or amount <= 0 or received is None or received <= 0:
                issues.append(f"scenario {sc.get('receive')}/{sc.get('payment')}: missing amount or receive value")
                continue
            if bool(sc.get("historical")):
                historical = True
            receive = str(sc.get("receive") or "")
            payment = str(sc.get("payment") or "")
            if receive not in RECEIVE_TILES:
                issues.append(f"unknown receive method {receive!r}")
            if payment not in PAYMENT_TILES:
                issues.append(f"unknown payment method {payment!r}")
            rate = (received / amount).quantize(_Q4, rounding=ROUND_HALF_EVEN)
            fee_amount = try_parse_decimal(sc.get("fee_brl"))
            fees = [Fee(label="tarifa", amount=fee_amount, currency="BRL")] if fee_amount is not None else []
            declared: datetime | None = None
            for value in (sc.get("declared_at"), sc.get("captured_at"), doc_captured):
                if value:
                    try:
                        declared = dtparser.isoparse(str(value))
                        break
                    except (ValueError, TypeError):
                        continue
            context = {
                "origin": str(sc.get("origin") or "BR"),
                "destination": str(sc.get("destination") or "PY"),
                "send_currency": str(sc.get("send_currency") or "BRL"),
                "receive_currency": str(sc.get("receive_currency") or "PYG"),
                "amount_brl": str(amount),
                "payment": payment,
                "receive": receive,
                "bank": sc.get("bank"),
                "channel": str(sc.get("channel") or "web"),
                "promo": sc.get("promo"),
                "delivery": sc.get("delivery"),
                "exchange_rate_shown": sc.get("exchange_rate"),
                "fee_before_discount_brl": sc.get("fee_before_discount_brl"),
            }
            quotes.append(
                QuoteDraft(
                    source_id=self.info.id, base="BRL", quote="PYG", buy=rate, sell=None,
                    unit_note="PYG por 1 BRL (efetivo: PYG recebidos / BRL enviados; tarifa à parte em fees)",
                    modality="transfer" if receive == "bank_account" else "cash",
                    kind="indicative", channel="digital", city=None, amount_base=amount, context=context, fees=fees,
                    declared_updated_at=declared or (None if historical else captured_at),
                )
            )
        screenshot_path: str | None = params.get("screenshot_path")
        screenshot_bytes: bytes | None = params.get("screenshot_bytes")
        evidence = build_evidence(
            source_id=self.info.id, kind="screenshot" if screenshot_path else "json", url=url, captured_at=captured_at,
            raw=screenshot_bytes if screenshot_bytes is not None else text,
            rules=[RULE_BROWSER, RULE_JSON] if screenshot_path else [RULE_JSON],
            excerpt_text=quotes_excerpt(quotes, header=f"{len(scenarios)} scenario(s); note={note or '-'}"),
            raw_path=screenshot_path,
        )
        if not quotes:
            return error_result("; ".join(issues) or "no usable scenarios", evidence)
        if historical:
            msg = "historical fixture data; never current"
            return AdapterResult(status=AdapterStatus.STALE, quotes=quotes, evidence=evidence,
                                 message="; ".join([msg, *issues]))
        return finalize(quotes=quotes, evidence=evidence, issues=issues, captured_at=captured_at,
                        stale_after=self.stale_after)

    # ------------------------------------------------------------------ fetch (Playwright)
    async def fetch(self, *, amount_brl: str | int | Decimal = "5000", payment: Payment = "pix",
                    receive: Receive = "bank_account", bank: str | None = None, promo: str | None = None,
                    headless: bool = True, **params: Any) -> AdapterResult:
        captured_at = utcnow()
        amount = try_parse_decimal(amount_brl)
        if amount is None or amount <= 0:
            return error_result(f"invalid amount_brl {amount_brl!r}")
        if receive not in RECEIVE_TILES or payment not in PAYMENT_TILES:
            return error_result(f"unsupported receive={receive!r} / payment={payment!r}")
        try:
            from playwright.async_api import TimeoutError as PWTimeout
            from playwright.async_api import async_playwright
        except ImportError:
            return AdapterResult(status=AdapterStatus.DEGRADED, quotes=[], evidence=None,
                                 message="playwright not installed; run `uv sync --extra browser` "
                                         "(no numbers produced)")

        out_dir = evidence_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = captured_at.strftime("%Y%m%dT%H%M%SZ")
        shot_path = out_dir / f"wu_{stamp}_{amount}_{payment}_{receive}.png"
        trail: list[str] = []
        scenario: dict[str, Any] = {
            "origin": "BR", "destination": "PY", "send_currency": "BRL", "receive_currency": "PYG",
            "amount_brl": str(amount), "payment": payment, "receive": receive, "bank": bank, "channel": "web",
            "promo": promo, "captured_at": captured_at.isoformat(),
        }

        async def fail(status: AdapterStatus, reason: str, page: Any | None) -> AdapterResult:
            path_note = ""
            if page is not None:
                try:
                    await page.screenshot(path=str(shot_path), full_page=True)
                    path_note = f"; screenshot={shot_path}"
                except Exception as exc:  # noqa: BLE001 - evidence is best effort
                    path_note = f"; screenshot failed: {exc}"
            return AdapterResult(status=status, quotes=[], evidence=None,
                                 message=f"{reason}{path_note}; steps: {' > '.join(trail)}")

        async with async_playwright() as pw:
            try:
                browser = await pw.chromium.launch(headless=headless)
            except Exception as first:  # noqa: BLE001
                exe = _chromium_executable()
                if not exe:
                    return AdapterResult(status=AdapterStatus.DEGRADED, quotes=[], evidence=None,
                                         message=f"chromium launch failed ({str(first)[:120]}); set FX_PW_CHROMIUM")
                browser = await pw.chromium.launch(headless=headless, executable_path=exe)
            page = None
            try:
                context = await browser.new_context(locale="pt-BR", user_agent=USER_AGENT,
                                                    viewport={"width": 1280, "height": 2400})
                page = await context.new_page()
                resp = await page.goto(START_URL, wait_until="domcontentloaded", timeout=60_000)
                status = resp.status if resp else None
                trail.append(f"goto={status}")
                if status in (403, 429, 503):
                    return await fail(AdapterStatus.BLOCKED, f"HTTP {status} on start page (anti-bot)", page)

                async def click_first(selectors: tuple[str, ...], labels: tuple[str, ...], what: str) -> bool:
                    for i, sel in enumerate(selectors):
                        loc = page.locator(sel).first
                        try:
                            await loc.wait_for(timeout=self.step_timeout_ms if i == 0 else 2_000)
                            await loc.click()
                            trail.append(f"{what}:{sel}")
                            return True
                        except PWTimeout:
                            continue
                    for label in labels:
                        loc = page.get_by_text(re.compile(re.escape(label), re.I)).first
                        try:
                            await loc.wait_for(timeout=2_000)
                            await loc.click()
                            trail.append(f"{what}:text={label}")
                            return True
                        except PWTimeout:
                            continue
                    return False

                # 1) destination country
                tile = page.locator(SELECTORS["country_tile"], has_text="Paraguai").first
                try:
                    await tile.wait_for(timeout=self.step_timeout_ms)
                    await tile.click()
                    trail.append("tile:Paraguai")
                except PWTimeout:
                    body = (await page.inner_text("body"))[:600].lower()
                    if any(k in body for k in _BLOCK_WORDS):
                        return await fail(AdapterStatus.BLOCKED, "anti-bot page instead of country tiles", page)
                    return await fail(AdapterStatus.DEGRADED, "country tile 'Paraguai' not found (selector drift?)",
                                      page)
                try:
                    await page.locator(SELECTORS["cookie_close"]).first.click(timeout=3_000)
                    trail.append("cookies:closed")
                except Exception:  # noqa: BLE001 - banner is optional
                    pass

                # 2) amount + currency
                try:
                    await page.wait_for_selector(SELECTORS["send_amount"], timeout=self.step_timeout_ms)
                except PWTimeout:
                    return await fail(AdapterStatus.DEGRADED, "amount form (#txtSendAmount) did not appear", page)
                # Angular initialises the form a moment after the input renders (limits call ->
                # "Enviar até ... BRL"); a value typed before that is reset to 0.00, so wait for it.
                try:
                    await page.get_by_text(re.compile(r"Enviar at[ée]", re.I)).first.wait_for(timeout=15_000)
                    trail.append("limits:ready")
                except PWTimeout:
                    trail.append("limits:not-seen")
                try:
                    await page.select_option(SELECTORS["currency_select"], "PYG")
                except Exception as exc:  # noqa: BLE001
                    trail.append(f"currency-select-skipped:{type(exc).__name__}")
                amount_ok = False
                for attempt in range(1, 4):
                    await page.fill(SELECTORS["send_amount"], str(amount))
                    await page.keyboard.press("Tab")
                    try:
                        # the value must survive AND the receive tiles must render for it
                        await page.wait_for_function(
                            "([sel, want]) => { const el = document.querySelector(sel); "
                            "return !!el && el.value.replace(/[^0-9.]/g, '').startsWith(want) "
                            "&& !!document.querySelector('[amplitude-id^=\"tile-fundsout\"]'); }",
                            arg=[SELECTORS["send_amount"], str(amount)], timeout=15_000,
                        )
                        amount_ok = True
                        trail.append(f"amount={amount}" + (f"(try {attempt})" if attempt > 1 else ""))
                        break
                    except PWTimeout:
                        trail.append(f"amount-reset(try {attempt})")
                if not amount_ok:
                    return await fail(AdapterStatus.DEGRADED,
                                      "amount did not stick / receive tiles never rendered (form reset by the SPA)", page)

                # 3) receive method, then payment method
                if not await click_first(RECEIVE_TILES[receive], RECEIVE_LABELS[receive], "receive"):
                    return await fail(AdapterStatus.DEGRADED, f"receive option for {receive!r} not found", page)
                if not await click_first(PAYMENT_TILES[payment], PAYMENT_LABELS[payment], "payment"):
                    return await fail(AdapterStatus.DEGRADED, f"payment option for {payment!r} not offered", page)
                if bank and not await click_first((), (bank,), "bank"):
                    trail.append(f"bank:{bank}:not-found")

                # 4) wait for the quote (receive amount populated), then read the summary
                try:
                    await page.wait_for_function(
                        "sel => { const el = document.querySelector(sel); "
                        "return !!(el && el.value && el.value !== '0.00'); }",
                        arg=SELECTORS["receive_amount"], timeout=self.step_timeout_ms,
                    )
                except PWTimeout:
                    return await fail(AdapterStatus.DEGRADED,
                                      "receive amount never populated (option not accepted or selector drift)", page)
                receive_text = await page.input_value(SELECTORS["receive_amount"])
                body_text = await page.inner_text("body")
                received = try_parse_decimal(receive_text)
                scenario["receive_amount_pyg"] = str(received) if received is not None else None
                scenario["receive_amount_text"] = receive_text
                summary = extract_summary(body_text)
                scenario.update(summary)
                if promo:
                    scenario["promo"] = promo
                trail.append(f"receive={receive_text}")
                await page.screenshot(path=str(shot_path), full_page=True)
                shot_bytes = shot_path.read_bytes()
            except PWTimeout as exc:
                return await fail(AdapterStatus.DEGRADED, f"timeout: {str(exc)[:160]}", page)
            except Exception as exc:  # noqa: BLE001 - never raise for provider-side failures
                return await fail(AdapterStatus.ERROR, f"{type(exc).__name__}: {str(exc)[:200]}", page)
            finally:
                await browser.close()

        result = self.parse(json.dumps(scenario, ensure_ascii=False), captured_at=captured_at, url=START_URL,
                            screenshot_path=str(shot_path), screenshot_bytes=shot_bytes)
        if result.evidence is not None:
            result.evidence.sha256 = sha256_hex(shot_bytes)
        result.message = "; ".join(filter(None, [result.message, f"steps: {' > '.join(trail)}"]))
        return result


adapter = WesternUnionAdapter()
