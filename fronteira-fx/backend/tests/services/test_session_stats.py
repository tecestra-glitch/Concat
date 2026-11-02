"""Resumo da sessão por chave (`services/session_stats.py`): dia em America/Asuncion, Δ, spread e casas."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from fronteira_fx.services.quotes import store_quote_draft
from fronteira_fx.services.session_stats import ASUNCION, day_start_asuncion, session_stats
from tests.api.test_candles_api import _mount
from tests.conftest import add_source, draft

D = Decimal
KEY = "chaco:CDE:USD/PYG:cash"
NOW = datetime(2026, 11, 2, 12, 30, tzinfo=UTC)
DAY_START_UTC = datetime(2026, 11, 2, 3, 0, tzinfo=UTC)


def _store(
    db: Session,
    source_id: str,
    base: str,
    quote: str,
    buy: str | None,
    sell: str | None,
    at: datetime,
    *,
    city: str | None = "CDE",
    branch_id: str | None = None,
    modality: str = "cash",
    kind: str = "indicative",
    data_mode: str = "real",
) -> None:
    store_quote_draft(
        db,
        draft(source_id, base, quote, buy, sell, city=city, branch_id=branch_id, modality=modality, kind=kind),
        evidence_id=None,
        data_mode=data_mode,
        captured_at=at,
    )


def _seed_chaco(db: Session) -> None:
    """Exemplo canônico de §0.4 da spec, para `chaco` (CDE, cash)."""
    add_source(db, "chaco", cities=["CDE"], branches=[("chaco-cde-centro", "CDE")])
    _store(db, "chaco", "USD", "PYG", "7320", "7350", datetime(2026, 11, 2, 12, 1, tzinfo=UTC))
    _store(db, "chaco", "USD", "PYG", "7322", "7352", datetime(2026, 11, 2, 12, 6, tzinfo=UTC))
    _store(db, "chaco", "USD", "PYG", "7318", None, datetime(2026, 11, 2, 12, 11, tzinfo=UTC))
    _store(db, "chaco", "USD", "PYG", "7325", "7355", datetime(2026, 11, 2, 12, 16, tzinfo=UTC))
    db.commit()


def _json(stats) -> dict:
    """Forma da API (strings decimais): o contrato que o cliente recebe."""
    return stats.model_dump(mode="json")


# ---- day_start_asuncion -------------------------------------------------------------------------


def test_day_start_is_midnight_in_asuncion_for_the_day_of_now():
    assert day_start_asuncion(datetime(2026, 11, 2, 12, 0, tzinfo=UTC)) == datetime(2026, 11, 2, 0, 0, tzinfo=ASUNCION)
    assert day_start_asuncion(datetime(2026, 11, 2, 12, 0, tzinfo=UTC)).astimezone(UTC) == DAY_START_UTC


def test_day_start_uses_asuncion_date_not_utc_date():
    # 02:30Z ainda é 1 de novembro em Assunção (UTC-3).
    assert day_start_asuncion(datetime(2026, 11, 2, 2, 30, tzinfo=UTC)) == datetime(2026, 11, 1, 0, 0, tzinfo=ASUNCION)


# ---- session_stats: exemplo canônico ------------------------------------------------------------


def test_canonical_example_matches_spec_section_0_4(db):
    _seed_chaco(db)
    stats = session_stats(db, [KEY], NOW, "real")[0]
    body = _json(stats)
    assert body["key"] == KEY
    assert body["open"] == "7335"
    assert body["high"] == "7340"
    assert body["low"] == "7318"
    assert body["last"] == "7340"
    assert stats.last_at == datetime(2026, 11, 2, 12, 16, tzinfo=UTC)
    assert body["change_abs"] == "5"
    assert body["change_pct"] is not None
    assert abs(D(body["change_pct"]) - D("0.06816633")) < D("1e-6")
    assert body["n_quotes"] == 4
    assert body["spread_avg"] == "30"
    assert body["houses"] == 1
    assert body["data_mode"] == "real"
    assert stats.day_start == datetime(2026, 11, 2, 0, 0, tzinfo=ASUNCION)


# ---- session_stats: casas do par ----------------------------------------------------------------


def test_houses_counts_distinct_non_reference_sources_for_the_pair(db):
    _seed_chaco(db)
    add_source(db, "alberdi", cities=["CDE"])
    add_source(db, "norte", cities=["ASU"])
    add_source(db, "bcp", kind="central_bank", method="official_api")
    at = datetime(2026, 11, 2, 12, 20, tzinfo=UTC)
    _store(db, "alberdi", "USD", "PYG", "7300", "7340", at)
    _store(db, "norte", "BRL", "PYG", "1380", "1390", at, city="ASU")
    _store(db, "bcp", "USD", "PYG", "7325", "7325", at, city=None, kind="market_reference")
    db.commit()
    assert session_stats(db, [KEY], NOW, "real")[0].houses == 2
    assert session_stats(db, ["norte:ASU:BRL/PYG:cash"], NOW, "real")[0].houses == 1


# ---- session_stats: janela do dia ---------------------------------------------------------------


def test_quotes_before_day_start_or_after_now_are_out_of_window(db):
    _seed_chaco(db)
    _store(db, "chaco", "USD", "PYG", "7000", "7010", datetime(2026, 11, 2, 2, 59, tzinfo=UTC))
    _store(db, "chaco", "USD", "PYG", "7500", "7510", datetime(2026, 11, 2, 12, 45, tzinfo=UTC))
    db.commit()
    body = _json(session_stats(db, [KEY], NOW, "real")[0])
    assert body["n_quotes"] == 4
    assert body["open"] == "7335"
    assert body["last"] == "7340"


# ---- session_stats: vazio, chave, modo, ordem, lados -------------------------------------------


def test_no_quotes_gives_null_fields_and_zero_counts(db):
    stats = session_stats(db, ["x:CDE:USD/PYG:cash"], NOW, "real")[0]
    body = _json(stats)
    assert body["open"] is None
    assert body["high"] is None
    assert body["low"] is None
    assert body["last"] is None
    assert stats.last_at is None
    assert body["change_abs"] is None
    assert body["change_pct"] is None
    assert body["spread_avg"] is None
    assert body["n_quotes"] == 0
    assert body["houses"] == 0
    assert body["data_mode"] == "real"


def test_branch_quote_counts_for_the_series_but_other_modality_does_not(db):
    _seed_chaco(db)
    _store(
        db,
        "chaco",
        "USD",
        "PYG",
        "7330",
        "7360",
        datetime(2026, 11, 2, 12, 21, tzinfo=UTC),
        branch_id="chaco-cde-centro",
    )
    _store(db, "chaco", "USD", "PYG", "9000", "9100", datetime(2026, 11, 2, 12, 22, tzinfo=UTC), modality="cash_promo")
    db.commit()
    body = _json(session_stats(db, [KEY], NOW, "real")[0])
    assert body["n_quotes"] == 5
    assert body["last"] == "7345"
    assert body["high"] == "7345"


def test_demo_mode_does_not_see_real_quotes(db):
    _seed_chaco(db)
    body = _json(session_stats(db, [KEY], NOW, "demo")[0])
    assert body["n_quotes"] == 0
    assert body["houses"] == 0
    assert body["open"] is None
    assert body["data_mode"] == "demo"


def test_quotes_without_any_side_are_ignored_even_for_n_quotes(db):
    _seed_chaco(db)
    _store(db, "chaco", "USD", "PYG", None, None, datetime(2026, 11, 2, 12, 25, tzinfo=UTC))
    db.commit()
    body = _json(session_stats(db, [KEY], NOW, "real")[0])
    assert body["n_quotes"] == 4
    assert body["last"] == "7340"


def test_change_pct_is_null_when_open_is_zero(db):
    add_source(db, "chaco", cities=["CDE"])
    _store(db, "chaco", "USD", "PYG", "0", "0", datetime(2026, 11, 2, 12, 1, tzinfo=UTC))
    _store(db, "chaco", "USD", "PYG", "10", "20", datetime(2026, 11, 2, 12, 2, tzinfo=UTC))
    db.commit()
    body = _json(session_stats(db, [KEY], NOW, "real")[0])
    assert body["open"] == "0"
    assert body["last"] == "15"
    assert body["change_pct"] is None


def test_results_keep_the_order_of_the_requested_keys(db):
    _seed_chaco(db)
    result = session_stats(db, ["b:CDE:USD/PYG:cash", KEY, "a:CDE:USD/PYG:cash"], NOW, "real")
    assert [s.key for s in result] == ["b:CDE:USD/PYG:cash", KEY, "a:CDE:USD/PYG:cash"]
    assert [s.n_quotes for s in result] == [0, 4, 0]


# ---- API ----------------------------------------------------------------------------------------


def test_stats_endpoint_returns_session_stats_for_the_series(app, client, db):
    _mount(app)
    now = datetime.now(UTC)
    day_start = day_start_asuncion(now)
    first_at = now - timedelta(minutes=5)
    if first_at < day_start.astimezone(UTC):
        pytest.skip("janela do dia acabou de virar")
    add_source(db, "chaco", cities=["CDE"], branches=[("chaco-cde-centro", "CDE")])
    _store(db, "chaco", "USD", "PYG", "7320", "7350", first_at)
    _store(db, "chaco", "USD", "PYG", "7322", "7352", first_at + timedelta(minutes=1))
    _store(db, "chaco", "USD", "PYG", "7318", None, first_at + timedelta(minutes=2))
    _store(db, "chaco", "USD", "PYG", "7325", "7355", first_at + timedelta(minutes=3))
    db.commit()
    r = client.get("/v1/pregao/stats", params={"keys": KEY})
    if day_start_asuncion(datetime.now(UTC)) != day_start:
        pytest.skip("o dia virou durante a requisição")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 1
    assert body[0]["n_quotes"] == 4
    assert isinstance(body[0]["change_pct"], str)
    assert body[0]["day_start"].endswith("-03:00")
