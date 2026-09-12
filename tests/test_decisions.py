from er.config import MatchingDecisionThresholds
from er.matching.decisions import decide
from er.matching.models import CandidateScore, Decision

THRESHOLDS = MatchingDecisionThresholds(auto_match_min_score=140, auto_match_min_gap=30, review_min_score=90)


def _candidate(lei, score, rank=1):
    return CandidateScore(lei=lei, legal_name=f"Entity {lei}", score=score, rank=rank)


def test_no_candidates_is_unmatched():
    decision, chosen, gap = decide([], THRESHOLDS)
    assert decision == Decision.UNMATCHED
    assert chosen is None
    assert gap is None


def test_single_high_scoring_candidate_auto_matches():
    candidates = [_candidate("LEI1", 160)]
    decision, chosen, gap = decide(candidates, THRESHOLDS)
    assert decision == Decision.AUTO_MATCH
    assert chosen.lei == "LEI1"
    assert gap is None


def test_clear_winner_with_gap_auto_matches():
    candidates = [_candidate("LEI1", 165), _candidate("LEI2", 90)]
    decision, chosen, gap = decide(candidates, THRESHOLDS)
    assert decision == Decision.AUTO_MATCH
    assert chosen.lei == "LEI1"
    assert gap == 75


def test_two_close_high_scores_go_to_review_not_auto_match():
    # This is the core safety property: ambiguous evidence must never auto-match,
    # even when the top score alone clears the threshold.
    candidates = [_candidate("LEI1", 165), _candidate("LEI2", 162)]
    decision, chosen, gap = decide(candidates, THRESHOLDS)
    assert decision == Decision.REVIEW
    assert chosen.lei == "LEI1"
    assert gap == 3


def test_mid_score_goes_to_review():
    candidates = [_candidate("LEI1", 100)]
    decision, chosen, gap = decide(candidates, THRESHOLDS)
    assert decision == Decision.REVIEW
    assert chosen.lei == "LEI1"


def test_low_score_is_unmatched():
    candidates = [_candidate("LEI1", 50)]
    decision, chosen, gap = decide(candidates, THRESHOLDS)
    assert decision == Decision.UNMATCHED
    assert chosen is None
