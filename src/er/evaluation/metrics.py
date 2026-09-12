"""Pure aggregation over matcher outputs - no OpenSearch, no I/O, fully unit-testable.

`run_benchmark.py` is the only file that actually runs the matcher; everything here
just consumes the results.
"""

from __future__ import annotations

from dataclasses import dataclass

DECISIONS = ("AUTO_MATCH", "REVIEW", "UNMATCHED")


@dataclass
class RowResult:
    pair_id: str
    case_type: str
    difficulty: str
    expected_lei: str
    confusable_lei: str | None
    candidate_leis: list[str]  # ranked, best first
    decision: str
    chosen_lei: str | None


def recall_at_k(rows: list[RowResult], k: int) -> float:
    if not rows:
        return 0.0
    hits = sum(1 for r in rows if r.expected_lei in r.candidate_leis[:k])
    return hits / len(rows)


def top1_accuracy(rows: list[RowResult]) -> float:
    if not rows:
        return 0.0
    hits = sum(1 for r in rows if r.candidate_leis and r.candidate_leis[0] == r.expected_lei)
    return hits / len(rows)


def mean_reciprocal_rank(rows: list[RowResult]) -> float:
    """Standard MRR: 0 contribution for a row where expected_lei wasn't retrieved at all."""
    if not rows:
        return 0.0
    total = 0.0
    for r in rows:
        if r.expected_lei in r.candidate_leis:
            total += 1.0 / (r.candidate_leis.index(r.expected_lei) + 1)
    return total / len(rows)


def decision_rates(rows: list[RowResult]) -> dict[str, float]:
    n = len(rows) or 1
    return {d: sum(1 for r in rows if r.decision == d) / n for d in DECISIONS}


def auto_match_precision(rows: list[RowResult]) -> float | None:
    """Of rows the matcher was confident enough to AUTO_MATCH, what fraction picked
    the actually-correct entity. None (not 0) when there were no AUTO_MATCH rows -
    the metric is undefined, not "bad", in that case."""
    auto = [r for r in rows if r.decision == "AUTO_MATCH"]
    if not auto:
        return None
    correct = sum(1 for r in auto if r.chosen_lei == r.expected_lei)
    return correct / len(auto)


def auto_match_coverage(rows: list[RowResult]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if r.decision == "AUTO_MATCH") / len(rows)


def dangerous_failure_rate(rows: list[RowResult]) -> float | None:
    """Fraction of confusable_pair rows that AUTO_MATCHed to the WRONG (confusable)
    entity with confidence. This is the single metric the project's design treats as
    mattering most: a wrong entity picked confidently is worse than no match at all.
    None when there are no confusable_pair rows to evaluate."""
    confusable = [r for r in rows if r.case_type == "confusable_pair"]
    if not confusable:
        return None
    dangerous = sum(1 for r in confusable if r.decision == "AUTO_MATCH" and r.chosen_lei == r.confusable_lei)
    return dangerous / len(confusable)


def summarize(rows: list[RowResult]) -> dict:
    summary = {
        "n": len(rows),
        "recall_at_1": round(recall_at_k(rows, 1), 4),
        "recall_at_5": round(recall_at_k(rows, 5), 4),
        "recall_at_10": round(recall_at_k(rows, 10), 4),
        "recall_at_20": round(recall_at_k(rows, 20), 4),
        "top1_accuracy": round(top1_accuracy(rows), 4),
        "mrr": round(mean_reciprocal_rank(rows), 4),
        "decision_rates": {k: round(v, 4) for k, v in decision_rates(rows).items()},
        "auto_match_coverage": round(auto_match_coverage(rows), 4),
    }
    precision = auto_match_precision(rows)
    summary["auto_match_precision"] = round(precision, 4) if precision is not None else None
    dangerous = dangerous_failure_rate(rows)
    summary["dangerous_failure_rate_confusable_pairs"] = round(dangerous, 4) if dangerous is not None else None
    return summary
