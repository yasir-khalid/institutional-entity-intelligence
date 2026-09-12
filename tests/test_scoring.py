from er.config import MatchingPenalties, MatchingWeights
from er.matching.scoring import explain, score_candidate

WEIGHTS = MatchingWeights()
PENALTIES = MatchingPenalties()

BASE_FEATURES = {
    "name_exact": False,
    "name_core_exact": False,
    "name_ratio": 0.0,
    "country_exact": None,
    "jurisdiction_exact": None,
    "postcode_exact": None,
    "postcode_prefix_exact": None,
    "city_exact": None,
    "fund_number_exact": None,
    "registration_id_exact": None,
    "fund_number_conflict": False,
    "master_conflict": False,
    "feeder_conflict": False,
    "registration_id_conflict": False,
}


def _features(**overrides):
    return {**BASE_FEATURES, **overrides}


def test_score_zero_for_all_negative_features():
    assert score_candidate(_features(), WEIGHTS, PENALTIES) == 0.0


def test_name_exact_adds_its_weight():
    score = score_candidate(_features(name_exact=True), WEIGHTS, PENALTIES)
    assert score == WEIGHTS.name_exact


def test_name_ratio_scales_by_weight():
    score = score_candidate(_features(name_ratio=0.5), WEIGHTS, PENALTIES)
    assert score == 0.5 * WEIGHTS.name_ratio


def test_conflicts_subtract_penalties():
    score = score_candidate(
        _features(name_exact=True, fund_number_conflict=True), WEIGHTS, PENALTIES
    )
    assert score == WEIGHTS.name_exact - PENALTIES.fund_number_conflict


def test_strong_match_beats_weak_match():
    strong = score_candidate(
        _features(name_exact=True, jurisdiction_exact=True, postcode_exact=True), WEIGHTS, PENALTIES
    )
    weak = score_candidate(_features(name_ratio=0.6), WEIGHTS, PENALTIES)
    assert strong > weak


def test_registration_id_conflict_is_the_strongest_penalty():
    with_reg_conflict = score_candidate(
        _features(name_exact=True, registration_id_conflict=True), WEIGHTS, PENALTIES
    )
    with_fund_conflict = score_candidate(
        _features(name_exact=True, fund_number_conflict=True), WEIGHTS, PENALTIES
    )
    assert with_reg_conflict < with_fund_conflict


def test_explain_omits_zero_contribution_features():
    evidence = explain(_features(name_exact=True), WEIGHTS, PENALTIES)
    assert evidence == {"name_exact": WEIGHTS.name_exact}


def test_explain_includes_negative_contributions():
    evidence = explain(_features(master_conflict=True), WEIGHTS, PENALTIES)
    assert evidence == {"master_conflict": -PENALTIES.master_conflict}
