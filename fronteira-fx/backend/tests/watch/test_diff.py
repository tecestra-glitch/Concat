from __future__ import annotations

from decimal import Decimal

from fronteira_fx.adapters.base import AdapterStatus
from fronteira_fx.watch.diff import (
    Snapshot,
    canonical_quotes,
    content_hash,
    dec_str,
    diff_quotes,
    diff_results,
    quote_key,
)
from tests.watch.conftest import BUSINESS_NOW, quote, result


def test_dec_str_is_stable():
    assert dec_str(Decimal("7350.00")) == "7350"
    assert dec_str(Decimal("7.35E+3")) == "7350"
    assert dec_str(Decimal("5.4043")) == "5.4043"
    assert dec_str(Decimal("0.00")) == "0"
    assert dec_str(None) is None


def test_hash_ignores_order_and_decimal_formatting():
    a = result(quote(buy="7290", sell="7350"), quote("BRL", "PYG", "1360", "1384"))
    b = result(quote("BRL", "PYG", "1360.0", "1384.00"), quote(buy="7290.00", sell="7350"))
    assert content_hash(a) == content_hash(b)
    assert len(content_hash(a)) == 64
    c = result(quote(buy="7290", sell="7360"), quote("BRL", "PYG", "1360", "1384"))
    assert content_hash(a) != content_hash(c)


def test_hash_depends_on_context_amount_and_branch_but_not_on_status_message():
    base = result(quote(), message="nota A")
    assert content_hash(base) == content_hash(result(quote(), message="nota B", status=AdapterStatus.DEGRADED))
    assert content_hash(base) != content_hash(result(quote(branch_id="x-1")))
    assert content_hash(base) != content_hash(result(quote(amount_base="5000")))
    assert content_hash(base) != content_hash(result(quote(context={"payment": "pix"})))
    # context key order is irrelevant
    k1 = quote_key(quote(context={"payment": "pix", "receive": "bank"}))
    k2 = quote_key(quote(context={"receive": "bank", "payment": "pix"}))
    assert k1 == k2


def test_first_observation_is_a_baseline():
    assert diff_results(None, result(quote()), source_id="fake") == []


def test_identical_results_produce_no_changes():
    before = result(quote(), quote("BRL", "PYG", "1360", "1384"))
    after = result(quote(buy="7290.00", sell="7350.0"), quote("BRL", "PYG", "1360", "1384"))
    assert diff_results(before, after, source_id="fake") == []


def test_quote_change_summary_matches_contract_example():
    before = result(quote(buy="7290", sell="7350"))
    after = result(quote(buy="7290", sell="7360"))
    changes = diff_results(before, after, source_id="fake", ts=BUSINESS_NOW)
    assert len(changes) == 1
    c = changes[0]
    assert c.kind == "quote_change"
    assert c.summary == "USD/PYG CDE venda 7350 → 7360"
    assert c.source_id == "fake" and c.ts == BUSINESS_NOW and c.evidence_id is None
    assert c.before["sell"] == "7350" and c.after["sell"] == "7360"
    assert c.before["key"]["base"] == "USD" and c.after["key"]["city"] == "CDE"


def test_both_sides_moving_and_labels_with_branch_amount_context():
    before = result(
        quote(buy="7290", sell="7350", branch_id="chaco-9"),
        quote("BRL", "PYG", "1366.5", None, city=None, modality="transfer", channel="digital", amount_base="5000",
              context={"payment": "pix", "receive": "bank_account", "bank": None}),
    )
    after = result(
        quote(buy="7300", sell="7360", branch_id="chaco-9"),
        quote("BRL", "PYG", "1370", None, city=None, modality="transfer", channel="digital", amount_base="5000",
              context={"payment": "pix", "receive": "bank_account", "bank": None}),
    )
    summaries = sorted(c.summary for c in diff_results(before, after, source_id="fake"))
    assert summaries == [
        "BRL/PYG transfer 5000 BRL pix→bank_account compra 1366.5 → 1370",
        "USD/PYG CDE chaco-9 compra 7290 → 7300, venda 7350 → 7360",
    ]


def test_added_and_removed_quotes():
    before = result(quote(), quote("BRL", "PYG", "1360", "1384"))
    after = result(quote(), quote("USD", "BRL", "5.37", "5.41", city="ASU"))
    changes = diff_results(before, after, source_id="fake")
    kinds = {c.kind for c in changes}
    assert kinds == {"quote_change"}
    summaries = sorted(c.summary for c in changes)
    assert summaries == [
        "BRL/PYG CDE cotação removida (era compra 1360 · venda 1384)",
        "USD/BRL ASU nova cotação: compra 5.37 · venda 5.41",
    ]


def test_layout_change_when_ok_turns_into_error():
    before = result(quote(), quote("BRL", "PYG", "1360", "1384"))
    after = result(status=AdapterStatus.ERROR, message="no quotes parsed (layout changed?)")
    changes = diff_results(before, after, source_id="fake")
    assert [c.kind for c in changes] == ["layout_change"]
    assert "cotações 2 → 0" in changes[0].summary and "status ok → error" in changes[0].summary
    assert changes[0].after["message"] == "no quotes parsed (layout changed?)"


def test_layout_change_when_quote_count_drops_more_than_half():
    before = result(*[quote(branch_id=f"b{i}") for i in range(10)])
    after = result(*[quote(branch_id=f"b{i}") for i in range(4)], status=AdapterStatus.OK)
    changes = diff_results(before, after, source_id="fake")
    assert [c.kind for c in changes] == ["layout_change"]  # and no "removed" spam
    # a 40 % drop is not a layout change: individual removals are reported
    after6 = result(*[quote(branch_id=f"b{i}") for i in range(6)])
    changes = diff_results(before, after6, source_id="fake")
    assert len(changes) == 4 and all(c.kind == "quote_change" for c in changes)


def test_status_change_for_other_transitions_and_recovery_without_quote_spam():
    ok = result(quote(), quote("BRL", "PYG", "1360", "1384"))
    blocked = result(status=AdapterStatus.BLOCKED, message="HTTP 403: blocked by anti-bot/WAF")
    # ok -> blocked is a status change (not a parser problem)
    changes = diff_results(ok, blocked, source_id="fake")
    assert [c.kind for c in changes] == ["status_change"]
    assert changes[0].summary == "status ok → blocked: HTTP 403: blocked by anti-bot/WAF"
    # blocked -> ok: one status change, no "nova cotação" for every quote
    changes = diff_results(blocked, ok, source_id="fake")
    assert [c.kind for c in changes] == ["status_change"]
    assert changes[0].summary == "status blocked → ok"
    # ok -> stale with the same quotes: status change only
    stale = result(quote(), quote("BRL", "PYG", "1360", "1384"), status=AdapterStatus.STALE, message="declared 3h old")
    changes = diff_results(ok, stale, source_id="fake")
    assert [c.kind for c in changes] == ["status_change"]


def test_status_and_quote_changes_together_are_ordered_most_significant_first():
    ok = result(quote(buy="7290", sell="7350"))
    degraded_same_count = result(quote(buy="7290", sell="7360"), status=AdapterStatus.DEGRADED, message="1 branch missing")
    # ok -> degraded counts as a layout change (parser drift) even with the same quote count
    changes = diff_results(ok, degraded_same_count, source_id="fake")
    assert [c.kind for c in changes] == ["layout_change"]
    # stale -> ok with a moved price: status first, then the quote
    stale = result(quote(buy="7290", sell="7350"), status=AdapterStatus.STALE)
    changes = diff_results(stale, result(quote(buy="7290", sell="7360")), source_id="fake")
    assert [c.kind for c in changes] == ["status_change", "quote_change"]


def test_snapshot_round_trip_preserves_hash_and_diffability():
    res = result(quote(buy="7290", sell="7350"), quote("BRL", "PYG", "1360", None, context={"promo": "x"}))
    snap = Snapshot.from_result(res)
    restored = Snapshot.from_json(snap.to_json())
    assert restored is not None
    assert restored.hash == snap.hash == content_hash(res)
    assert restored.quotes == canonical_quotes(res)
    assert Snapshot.from_json(None) is None
    changes = diff_quotes(restored.quotes, canonical_quotes(result(quote(buy="7290", sell="7351"))), source_id="fake")
    assert [c.summary for c in changes] == [
        "BRL/PYG CDE promo=x cotação removida (era compra 1360 · venda —)",
        "USD/PYG CDE venda 7350 → 7351",
    ]
