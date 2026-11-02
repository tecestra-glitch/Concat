from datetime import timedelta
from decimal import Decimal

from fronteira_fx.services.history import history_series, volatility_for_key
from fronteira_fx.services.quotes import context_hash, latest_quotes, series_key, store_quote_draft
from tests.conftest import NOW, add_source, draft

D = Decimal


def test_series_key_and_context_hash_are_stable():
    assert context_hash(None) == "" and context_hash({}) == ""
    assert context_hash({"a": 1, "b": 2}) == context_hash({"b": 2, "a": 1})
    assert series_key("chaco", "CDE", "USD", "PYG", "cash") == "chaco:CDE:USD/PYG:cash"
    assert (
        series_key("wu", None, "BRL", "PYG", "transfer", amount_base=D("5000"), ctx_hash="abcdef0123")
        == "wu:digital:BRL/PYG:transfer:5000:abcdef01"
    )


def test_latest_per_context_and_filters(db):
    add_source(db, "chaco", cities=["CDE"], branches=[("chaco-cde", "CDE")])
    add_source(db, "wu", method="browser", kind="remittance")
    old = draft("chaco", "USD", "PYG", "7200", "7250", city="CDE", branch_id="chaco-cde")
    new = draft("chaco", "USD", "PYG", "7300", "7350", city="CDE", branch_id="chaco-cde")
    store_quote_draft(db, old, evidence_id=None, data_mode="real", captured_at=NOW - timedelta(minutes=10))
    store_quote_draft(db, new, evidence_id=None, data_mode="real", captured_at=NOW)
    for amt in ("5000", "10000"):
        store_quote_draft(
            db,
            draft(
                "wu",
                "BRL",
                "PYG",
                "1370",
                None,
                modality="transfer",
                channel="digital",
                amount_base=amt,
                context={"payment": "pix"},
            ),
            evidence_id=None,
            data_mode="real",
            captured_at=NOW,
        )
    store_quote_draft(
        db,
        draft("chaco", "USD", "PYG", "1", "1", city="CDE", branch_id="chaco-cde"),
        evidence_id=None,
        data_mode="demo",
        captured_at=NOW,
    )  # demo row must be invisible
    db.flush()

    rows = latest_quotes(db, data_mode="real", lookback_s=None)
    assert len(rows) == 3
    chaco = [q for q in rows if q.source_id == "chaco"]
    assert len(chaco) == 1 and chaco[0].buy == D("7300")
    assert (
        len(latest_quotes(db, data_mode="real", amount=D("5000"), lookback_s=None)) == 2
    )  # chaco (any amount) + wu 5000
    assert len(latest_quotes(db, data_mode="real", city="CDE", lookback_s=None)) == 1
    assert len(latest_quotes(db, data_mode="real", base="BRL", quote="PYG", lookback_s=None)) == 2
    assert len(latest_quotes(db, data_mode="real", source="wu", modality="transfer", lookback_s=None)) == 2
    # Janela relativa ao NOW fixo das fixtures (lookback_s usaria o relógio real e quebraria o teste).
    assert latest_quotes(db, data_mode="real", since=NOW - timedelta(seconds=60)) == rows  # all within lookback


def test_history_resampling_and_prefix_key(db):
    add_source(db, "chaco", cities=["CDE"], branches=[("chaco-cde", "CDE")])
    for i in range(7):  # every 2.5 min => two per 5-min cell
        ts = NOW - timedelta(seconds=150 * (6 - i))
        store_quote_draft(
            db,
            draft("chaco", "USD", "PYG", str(7300 + i), str(7350 + i), city="CDE", branch_id="chaco-cde", declared=ts),
            evidence_id=None,
            data_mode="real",
            captured_at=ts,
        )
    db.flush()
    exact = history_series(
        db, "chaco:CDE:USD/PYG:cash:@chaco-cde", data_mode="real", start=NOW - timedelta(hours=1), end=NOW
    )
    prefix = history_series(db, "chaco:CDE:USD/PYG:cash", data_mode="real", start=NOW - timedelta(hours=1), end=NOW)
    assert len(exact.points) == 4 and [p.model_dump(mode="json") for p in exact.points] == [
        p.model_dump(mode="json") for p in prefix.points
    ]
    last = exact.points[-1]
    assert last.buy == D("7306") and last.mid == (D("7306") + D("7356")) / 2
    assert exact.points[0].t.minute % 5 == 0 and exact.points[0].t.second == 0
    vol = volatility_for_key(db, "chaco:CDE:USD/PYG:cash", window="1h", data_mode="real", now=NOW)
    assert vol.status == "insufficient_data" and vol.returns_used == 3
    assert history_series(db, "chaco:CDE:USD/PYG:cash", data_mode="demo").points == []
