from er.config import MatchingDecisionThresholds
from er.matching.features import build_query_record
from er.matching.matcher import _build_reason, _fund_structure_ambiguous, _missing_evidence
from er.matching.models import CandidateScore, Decision

THRESHOLDS = MatchingDecisionThresholds(
    auto_match_min_score=140, auto_match_min_gap=30, review_min_score=90, tie_tolerance=5
)


def _candidate(lei, score, jurisdiction="GB", rank=1):
    return CandidateScore(lei=lei, legal_name=f"Entity {lei}", jurisdiction=jurisdiction, score=score, rank=rank)


def test_auto_match_has_no_reason():
    scored = [_candidate("LEI1", 200)]
    reason, competing = _build_reason(Decision.AUTO_MATCH, scored, THRESHOLDS)
    assert reason is None
    assert competing == []


def test_no_candidates_has_no_reason():
    reason, competing = _build_reason(Decision.UNMATCHED, [], THRESHOLDS)
    assert reason is None
    assert competing == []


def test_tied_candidates_produce_a_tie_reason_naming_jurisdictions():
    # This is the "North Rock Capital" case: several entities score identically
    # because the query lacks any distinguishing information.
    scored = [
        _candidate("LEI_US", 40, jurisdiction="US"),
        _candidate("LEI_GB", 40, jurisdiction="GB"),
        _candidate("LEI_HK", 40, jurisdiction="HK"),
    ]
    reason, competing = _build_reason(Decision.UNMATCHED, scored, THRESHOLDS)
    assert "3 entities" in reason
    assert "US" in reason and "GB" in reason and "HK" in reason
    assert len(competing) == 3


def test_single_weak_candidate_reports_low_score_not_a_tie():
    scored = [_candidate("LEI1", 50)]
    reason, competing = _build_reason(Decision.UNMATCHED, scored, THRESHOLDS)
    assert competing == []
    assert "too low" in reason


def test_review_reports_below_auto_match_threshold():
    scored = [_candidate("LEI1", 100)]
    reason, competing = _build_reason(Decision.REVIEW, scored, THRESHOLDS)
    assert competing == []
    assert "review threshold" in reason


def test_missing_evidence_lists_absent_fields():
    query = {"country": None, "postcode": None, "registration_id": None}
    missing = _missing_evidence(query)
    assert "country/jurisdiction" in missing
    assert "postcode/address" in missing
    assert "registration identifier" in missing


def test_missing_evidence_omits_provided_fields():
    query = {"country": "GB", "postcode": None, "registration_id": "12345"}
    missing = _missing_evidence(query)
    assert missing == ["postcode/address"]


def test_fund_structure_ambiguous_when_query_silent_and_top_two_disagree():
    # Regression test / experiment 005: a query lacking "master"/"feeder" (e.g. an
    # aggressive-core-stripped adversarial query) string-matches the master/plain
    # variant's own core exactly (name_core_exact fires) while the feeder variant's
    # core still carries the extra "feeder" token and only earns name_ratio -
    # producing a large, confident-looking score gap that reflects tokenization,
    # not real evidence. Confirmed live this was auto-matching the WRONG (master)
    # fund when the true answer was the feeder, with gaps of 60-240 points.
    query = build_query_record("acme global credit fund")  # no master/feeder token
    top = CandidateScore(lei="MASTER", legal_name="Acme Global Credit Fund", score=100, rank=1)
    runner_up = CandidateScore(lei="FEEDER", legal_name="Acme Global Credit Feeder Fund", score=40, rank=2)
    raw_by_lei = {
        "MASTER": {"is_master": True, "is_feeder": False},
        "FEEDER": {"is_master": False, "is_feeder": True},
    }
    assert _fund_structure_ambiguous(query, top, runner_up, raw_by_lei) is True


def test_fund_structure_not_ambiguous_when_query_asserts_a_claim():
    query = build_query_record("acme global credit master fund")
    top = CandidateScore(lei="MASTER", legal_name="Acme Global Credit Master Fund", score=100, rank=1)
    runner_up = CandidateScore(lei="FEEDER", legal_name="Acme Global Credit Feeder Fund", score=40, rank=2)
    raw_by_lei = {
        "MASTER": {"is_master": True, "is_feeder": False},
        "FEEDER": {"is_master": False, "is_feeder": True},
    }
    assert _fund_structure_ambiguous(query, top, runner_up, raw_by_lei) is False


def test_fund_structure_not_ambiguous_when_top_two_agree():
    query = build_query_record("acme global credit fund")
    top = CandidateScore(lei="A", legal_name="Acme Global Credit Fund I", score=100, rank=1)
    runner_up = CandidateScore(lei="B", legal_name="Acme Global Credit Fund II", score=40, rank=2)
    raw_by_lei = {
        "A": {"is_master": False, "is_feeder": False},
        "B": {"is_master": False, "is_feeder": False},
    }
    assert _fund_structure_ambiguous(query, top, runner_up, raw_by_lei) is False


def test_fund_structure_not_ambiguous_with_no_runner_up():
    query = build_query_record("acme global credit fund")
    top = CandidateScore(lei="A", legal_name="Acme Global Credit Fund", score=100, rank=1)
    assert _fund_structure_ambiguous(query, top, None, {"A": {"is_master": True}}) is False
