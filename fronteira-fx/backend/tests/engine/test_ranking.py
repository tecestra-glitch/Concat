from decimal import Decimal

from fronteira_fx.engine.ranking import PHYSICAL_MARGIN, Candidate, rank_opportunities

D = Decimal


def cand(id_, channel, roi, *, net_gain=None, capital=D("5000"), confidence="quoted", city=None, objective="cycle"):
    roi = D(roi)
    gain = D(net_gain) if net_gain is not None else roi * capital
    return Candidate(
        id=id_,
        title=id_,
        kind="cycle",
        channel=channel,
        city=city,
        capital=capital,
        final_value=capital + gain,
        net_gain=gain,
        roi=roi,
        effective_rate=None,
        confidence=confidence,
        objective=objective,
    )


def test_micro_gain_digital_enters_main_ranking():
    ranked = rank_opportunities([cand("tiny", "digital", D("0.37") / D("5000"), net_gain="0.37")])
    assert ranked[0].in_main_ranking is True
    assert ranked[0].candidate.net_gain == D("0.37")


def test_digital_without_gain_goes_secondary():
    ranked = rank_opportunities([cand("flat", "digital", "0"), cand("loss", "digital", "-0.002")])
    assert all(not r.in_main_ranking for r in ranked)
    assert "sem ganho" in ranked[0].ranking_reason


def test_physical_threshold_exactly_one_percentage_point():
    best_digital = D("0.0071")
    digital = cand("dig", "digital", best_digital)
    exactly = cand("phys-eq", "physical", best_digital + PHYSICAL_MARGIN, city="CDE")
    below = cand("phys-below", "physical", best_digital + PHYSICAL_MARGIN - D("0.00000001"), city="CDE")
    by_id = {r.candidate.id: r for r in rank_opportunities([digital, exactly, below])}
    assert by_id["dig"].in_main_ranking
    assert by_id["phys-eq"].in_main_ranking, by_id["phys-eq"].ranking_reason
    assert not by_id["phys-below"].in_main_ranking
    assert "abaixo do limiar" in by_id["phys-below"].ranking_reason
    assert by_id["phys-below"].comparable_best_digital_roi == best_digital
    # ordering: main first, by roi desc
    ranked = rank_opportunities([digital, exactly, below])
    assert [r.candidate.id for r in ranked] == ["phys-eq", "dig", "phys-below"]


def test_physical_without_digital_comparable_enters_when_positive():
    ranked = rank_opportunities(
        [cand("p", "physical", "0.002", city="PJC"), cand("p0", "physical", "-0.001", city="PJC")]
    )
    by_id = {r.candidate.id: r for r in ranked}
    assert by_id["p"].in_main_ranking and by_id["p"].comparable_best_digital_roi is None
    assert not by_id["p0"].in_main_ranking


def test_comparable_groups_use_same_capital_and_objective():
    dig_5k = cand("d5", "digital", "0.02", capital=D("5000"))
    phys_10k = cand("p10", "physical", "0.015", capital=D("10000"), city="CDE")  # different group => no bar
    phys_5k = cand("p5", "physical", "0.015", capital=D("5000"), city="CDE")
    by_id = {r.candidate.id: r for r in rank_opportunities([dig_5k, phys_10k, phys_5k])}
    assert by_id["p10"].in_main_ranking
    assert not by_id["p5"].in_main_ranking


def test_incomplete_digital_does_not_set_the_bar_and_is_flagged():
    inc = cand("inc", "digital", "0.05", confidence="incomplete")
    phys = cand("phys", "physical", "0.02", city="CDE")
    by_id = {r.candidate.id: r for r in rank_opportunities([inc, phys])}
    assert by_id["inc"].in_main_ranking and "incompleta" in by_id["inc"].ranking_reason
    assert by_id["phys"].in_main_ranking and by_id["phys"].comparable_best_digital_roi is None


def test_ranking_is_deterministic():
    cands = [cand("a", "digital", "0.001"), cand("b", "digital", "0.001"), cand("c", "physical", "0.03", city="CDE")]
    r1 = [r.to_dict() for r in rank_opportunities(cands)]
    r2 = [r.to_dict() for r in rank_opportunities(list(reversed(cands)))]
    assert r1 == r2
    assert r1[0]["roi"] == "0.03" and r1[0]["in_main_ranking"] is True
