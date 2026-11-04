"""Cadastro de instituições (`data/institutions.json`): loader validado, proveniência por número, sem invenção.

Nenhum teste acessa a internet: os dados são o próprio arquivo versionado e os casos inválidos são montados em memória.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal

import pytest

from fronteira_fx.services.institutions import (
    load_institutions,
    parse_institutions,
)


def figure(value=None, **overrides) -> dict:
    base: dict = {"value": value, "currency": None, "source_url": None, "checked_at": None, "note": None}
    if value is not None:
        base.update(source_url="https://example.com/tarifas", checked_at="2026-11-04")
    base.update(overrides)
    return base


def entry(**overrides) -> dict:
    base = {
        "id": "exemplo-banco",
        "name": "Banco Exemplo",
        "country": "PY",
        "kind": "bank",
        "status": "active",
        "currencies_held": None,
        "opens_remotely": None,
        "requires": None,
        "api": None,
        "source_url": None,
        "checked_at": None,
        "fx_cost": {
            "spread_pct": figure(),
            "iof_pct": figure(),
            "fee_pct": figure(),
            "fee_fixed": figure(),
        },
    }
    base.update(overrides)
    return base


def dump(*entries: dict) -> str:
    return json.dumps(list(entries))


# ---------- arquivo real ----------

@pytest.fixture(scope="module")
def real() -> dict:
    return load_institutions()


def test_real_file_loads_and_covers_the_research_list(real):
    expected = {
        "wise", "nubank-conta-global", "avenue", "nomad", "revolut-br", "inter-global", "c6-conta-global",
        "btg", "itau-personnalite-conta-global", "bb-americas-gold-global",
        "itau-py-cuenta-light", "itau-py-cuenta-full", "familiar", "eko", "basa", "atlas", "continental",
        "sudameris", "gnb", "personal-pay", "zimple", "wally", "tigo-money", "ueno", "airtm",
    }
    assert expected <= set(real), sorted(expected - set(real))


def test_ueno_is_discontinued(real):
    assert real["ueno"].status == "discontinued"
    assert real["ueno"].discontinued_note


def test_wise_does_not_hold_guarani(real):
    assert "PYG" not in (real["wise"].currencies_held or [])


def test_every_non_null_figure_has_source_and_date(real):
    for inst in real.values():
        for name, fig in inst.fx_cost.model_dump().items():
            if fig["value"] is not None:
                assert fig["source_url"], f"{inst.id}.{name} sem source_url"
                assert fig["checked_at"], f"{inst.id}.{name} sem checked_at"


def test_every_non_null_fact_has_entry_source(real):
    for inst in real.values():
        facts = [inst.currencies_held, inst.opens_remotely, inst.requires]
        if any(f is not None for f in facts):
            assert inst.source_url and inst.checked_at, inst.id
        if inst.api is not None:
            assert inst.api_source_url and inst.checked_at, inst.id


def test_money_is_decimal_string_never_float(real):
    for inst in real.values():
        for fig in inst.fx_cost.model_dump().values():
            if fig["value"] is not None:
                assert isinstance(fig["value"], str)
                assert isinstance(Decimal(fig["value"]), Decimal)


def test_no_invented_values_for_unconfirmed_institutions(real):
    # C6 e Continental: a pesquisa não confirmou nenhum custo nem fonte.
    for key in ("c6-conta-global", "continental"):
        inst = real[key]
        assert all(f["value"] is None for f in inst.fx_cost.model_dump().values()), key
        assert inst.currencies_held is None and inst.opens_remotely is None


def test_fx_cost_values_match_research(real):
    assert real["nubank-conta-global"].fx_cost.iof_pct.value == "0.035"
    assert real["wise"].fx_cost.iof_pct.value == "0.035"
    assert real["basa"].fx_cost.spread_pct.value == "0.0592"


def test_conditional_figures_stay_null_with_their_condition(real):
    # spread zero só para Ultravioleta; US$ 50 e 1% só em texto de clientes Enterprise: sem valor para cálculo.
    nubank = real["nubank-conta-global"].fx_cost.spread_pct
    assert nubank.value is None and "Ultravioleta" in nubank.note
    airtm = real["airtm"].fx_cost
    assert airtm.fee_fixed.value is None and "Enterprise" in airtm.fee_fixed.note
    assert airtm.fee_pct.value is None
    # Nomad: a conversão "a partir de 1%" é só o piso de uma faixa de 1% a 2% conforme o Nomad Pass.
    nomad = real["nomad"].fx_cost.spread_pct
    assert nomad.value is None and "Nomad Pass" in nomad.note


def test_nomad_spread_is_a_range_not_a_confirmed_value(real):
    # a pesquisa (bancos.md, linha 96) diz "a partir de 1%" e "de 1% a 2%": 1% não é um número confirmado.
    assert real["nomad"].fx_cost.spread_pct.value is None
    assert real["nomad"].fx_cost.iof_pct.value == "0.035"


def test_research_date_is_recorded(real):
    assert real["wise"].checked_at == date(2026, 11, 4)


def test_country_and_kind_use_allowed_values(real):
    assert {i.country for i in real.values()} <= {"BR", "PY", "INT"}
    assert {i.kind for i in real.values()} <= {"bank", "fintech", "wallet", "broker"}


# ---------- validação ----------

def test_accepts_a_well_formed_entry():
    parsed = parse_institutions(dump(entry()))
    assert parsed["exemplo-banco"].name == "Banco Exemplo"


def test_rejects_json_number_as_money():
    bad = entry(fx_cost={**entry()["fx_cost"], "iof_pct": {"value": 0.035, "source_url": "https://x", "checked_at": "2026-11-04"}})
    with pytest.raises(ValueError, match="iof_pct"):
        parse_institutions(dump(bad))


def test_rejects_value_without_source():
    bad = entry(fx_cost={**entry()["fx_cost"], "spread_pct": {"value": "0.01", "source_url": None, "checked_at": None}})
    with pytest.raises(ValueError, match="source_url"):
        parse_institutions(dump(bad))


def test_rejects_fact_without_entry_source():
    with pytest.raises(ValueError, match="source_url"):
        parse_institutions(dump(entry(currencies_held=["PYG"])))


def test_rejects_percentage_at_or_above_one():
    bad = entry(fx_cost={**entry()["fx_cost"], "spread_pct": figure("1")})
    with pytest.raises(ValueError, match="entre 0 e 1"):
        parse_institutions(dump(bad))


def test_fixed_fee_requires_currency():
    bad = entry(fx_cost={**entry()["fx_cost"], "fee_fixed": figure("50")})
    with pytest.raises(ValueError, match="currency"):
        parse_institutions(dump(bad))


def test_rejects_unknown_kind_and_country():
    with pytest.raises(ValueError):
        parse_institutions(dump(entry(kind="corretora")))
    with pytest.raises(ValueError):
        parse_institutions(dump(entry(country="AR")))


def test_discontinued_requires_note():
    with pytest.raises(ValueError, match="discontinued_note"):
        parse_institutions(dump(entry(status="discontinued")))


def test_duplicate_id_is_rejected():
    with pytest.raises(ValueError, match="duplicado"):
        parse_institutions(dump(entry(), entry()))


def test_bad_id_is_rejected():
    with pytest.raises(ValueError):
        parse_institutions(dump(entry(id="Banco Exemplo")))


def test_top_level_must_be_a_list():
    with pytest.raises(ValueError, match="lista"):
        parse_institutions(json.dumps({"id": "x"}))


def test_rejects_non_canonical_decimal_strings():
    # o frontend (DecimalString) só aceita ^-?\d+(\.\d+)?$; o backend não pode deixar passar outra forma.
    for raw in (" 0.01", "+0.01", ".5", "1e-2", "0.01 ", "0,01"):
        bad = entry(fx_cost={**entry()["fx_cost"], "spread_pct": figure(raw)})
        with pytest.raises(ValueError):
            parse_institutions(dump(bad))


def test_trailing_newline_is_not_a_valid_id():
    with pytest.raises(ValueError):
        parse_institutions(dump(entry(id="ok-id\n")))


def test_currency_is_checked_even_when_value_is_null():
    bad = entry(fx_cost={**entry()["fx_cost"], "fee_fixed": {"value": None, "currency": "usd!"}})
    with pytest.raises(ValueError, match="currency"):
        parse_institutions(dump(bad))


def test_currencies_held_is_immutable():
    parsed = parse_institutions(dump(entry(currencies_held=["PYG"], source_url="https://example.com", checked_at="2026-11-04")))
    with pytest.raises(AttributeError):
        parsed["exemplo-banco"].currencies_held.append("USD")
