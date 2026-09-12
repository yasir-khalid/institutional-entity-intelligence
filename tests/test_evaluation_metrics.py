from er.evaluation.metrics import (
    RowResult,
    auto_match_coverage,
    auto_match_precision,
    categorize,
    dangerous_failure_rate,
    decision_rates,
    failure_breakdown,
    mean_reciprocal_rank,
    recall_at_k,
    summarize,
    top1_accuracy,
)


def _row(
    pair_id="p1",
    case_type="isin_confirmed",
    difficulty="easy",
    conflict_type=None,
    expected_lei="LEI_A",
    confusable_lei=None,
    candidate_leis=("LEI_A", "LEI_B"),
    decision="AUTO_MATCH",
    chosen_lei="LEI_A",
):
    return RowResult(
        pair_id=pair_id,
        case_type=case_type,
        difficulty=difficulty,
        conflict_type=conflict_type,
        expected_lei=expected_lei,
        confusable_lei=confusable_lei,
        candidate_leis=list(candidate_leis),
        decision=decision,
        chosen_lei=chosen_lei,
    )


def test_recall_at_k_found_within_k():
    rows = [_row(candidate_leis=("LEI_X", "LEI_A", "LEI_Y"))]
    assert recall_at_k(rows, 1) == 0.0
    assert recall_at_k(rows, 2) == 1.0


def test_recall_at_k_empty_rows():
    assert recall_at_k([], 5) == 0.0


def test_top1_accuracy():
    rows = [
        _row(candidate_leis=("LEI_A", "LEI_B")),
        _row(candidate_leis=("LEI_B", "LEI_A")),
    ]
    assert top1_accuracy(rows) == 0.5


def test_mrr_averages_reciprocal_ranks():
    rows = [
        _row(candidate_leis=("LEI_A",)),  # rank 1 -> 1.0
        _row(candidate_leis=("LEI_X", "LEI_A")),  # rank 2 -> 0.5
        _row(candidate_leis=("LEI_X", "LEI_Y")),  # not found -> 0.0
    ]
    assert mean_reciprocal_rank(rows) == (1.0 + 0.5 + 0.0) / 3


def test_decision_rates_sum_to_one():
    rows = [
        _row(decision="AUTO_MATCH"),
        _row(decision="REVIEW"),
        _row(decision="UNMATCHED"),
        _row(decision="AUTO_MATCH"),
    ]
    rates = decision_rates(rows)
    assert rates["AUTO_MATCH"] == 0.5
    assert rates["REVIEW"] == 0.25
    assert rates["UNMATCHED"] == 0.25
    assert abs(sum(rates.values()) - 1.0) < 1e-9


def test_auto_match_precision_none_when_no_auto_matches():
    rows = [_row(decision="REVIEW")]
    assert auto_match_precision(rows) is None


def test_auto_match_precision_and_coverage():
    rows = [
        _row(decision="AUTO_MATCH", chosen_lei="LEI_A", expected_lei="LEI_A"),  # correct
        _row(decision="AUTO_MATCH", chosen_lei="LEI_B", expected_lei="LEI_A"),  # wrong
        _row(decision="REVIEW"),
    ]
    assert auto_match_precision(rows) == 0.5
    assert auto_match_coverage(rows) == 2 / 3


def test_dangerous_failure_rate_none_without_confusable_rows():
    rows = [_row(case_type="isin_confirmed")]
    assert dangerous_failure_rate(rows) is None


def test_dangerous_failure_rate_detects_wrong_confident_match():
    rows = [
        _row(
            case_type="confusable_pair",
            expected_lei="LEI_A",
            confusable_lei="LEI_B",
            decision="AUTO_MATCH",
            chosen_lei="LEI_B",  # matched the WRONG entity, confidently
        ),
        _row(
            case_type="confusable_pair",
            expected_lei="LEI_A",
            confusable_lei="LEI_B",
            decision="REVIEW",
            chosen_lei="LEI_A",
        ),
    ]
    assert dangerous_failure_rate(rows) == 0.5


def test_summarize_returns_expected_keys():
    rows = [_row()]
    summary = summarize(rows)
    assert summary["n"] == 1
    assert "recall_at_1" in summary
    assert "auto_match_precision" in summary
    assert "dangerous_failure_rate_confusable_pairs" in summary
    assert "failure_breakdown" in summary


def test_categorize_success():
    row = _row(decision="AUTO_MATCH", chosen_lei="LEI_A", expected_lei="LEI_A")
    assert categorize(row) == "success"


def test_categorize_wrong_auto_match():
    row = _row(decision="AUTO_MATCH", chosen_lei="LEI_B", expected_lei="LEI_A")
    assert categorize(row) == "wrong_auto_match"


def test_categorize_retrieval_miss():
    row = _row(decision="UNMATCHED", candidate_leis=("LEI_X", "LEI_Y"), expected_lei="LEI_A")
    assert categorize(row) == "retrieval_miss"


def test_categorize_under_confident_top1():
    # Correct entity retrieved AND ranked first, but the matcher still didn't commit -
    # a threshold/scoring-margin problem, distinct from a retrieval failure.
    row = _row(decision="REVIEW", candidate_leis=("LEI_A", "LEI_B"), expected_lei="LEI_A")
    assert categorize(row) == "under_confident_top1"


def test_categorize_correctly_deferred():
    # Correct entity retrieved but NOT ranked first - declining to AUTO_MATCH here is
    # the right call, not a bug, so this must not land in the same bucket as a real
    # scoring failure.
    row = _row(decision="REVIEW", candidate_leis=("LEI_B", "LEI_A"), expected_lei="LEI_A")
    assert categorize(row) == "correctly_deferred"


def test_failure_breakdown_sums_to_one():
    rows = [
        _row(decision="AUTO_MATCH", chosen_lei="LEI_A", expected_lei="LEI_A"),
        _row(decision="AUTO_MATCH", chosen_lei="LEI_B", expected_lei="LEI_A"),
        _row(decision="UNMATCHED", candidate_leis=("LEI_X",), expected_lei="LEI_A"),
        _row(decision="REVIEW", candidate_leis=("LEI_A", "LEI_B"), expected_lei="LEI_A"),
    ]
    breakdown = failure_breakdown(rows)
    assert breakdown["success"] == 0.25
    assert breakdown["wrong_auto_match"] == 0.25
    assert breakdown["retrieval_miss"] == 0.25
    assert breakdown["under_confident_top1"] == 0.25
    assert abs(sum(breakdown.values()) - 1.0) < 1e-9
