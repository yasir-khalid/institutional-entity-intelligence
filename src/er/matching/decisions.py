"""Turn a ranked list of scored candidates into a decision.

The gap-to-runner-up check is what makes this safe: a lone high score is
trustworthy, but two close high scores mean the evidence doesn't actually
distinguish between them - auto-matching either one risks a wrong-entity,
high-confidence error, which the design this project follows treats as the single
worst failure mode (worse than no match at all).
"""

from __future__ import annotations

from er.config import MatchingDecisionThresholds
from er.matching.models import CandidateScore, Decision


def decide(
    ranked_candidates: list[CandidateScore], thresholds: MatchingDecisionThresholds
) -> tuple[Decision, CandidateScore | None, float | None]:
    """Returns (decision, chosen_candidate_or_None, gap_to_runner_up_or_None).

    ranked_candidates must already be sorted best-first.
    """
    if not ranked_candidates:
        return Decision.UNMATCHED, None, None

    top = ranked_candidates[0]
    runner_up_score = ranked_candidates[1].score if len(ranked_candidates) > 1 else float("-inf")
    gap = top.score - runner_up_score if runner_up_score != float("-inf") else None

    if top.score >= thresholds.auto_match_min_score and (
        gap is None or gap >= thresholds.auto_match_min_gap
    ):
        return Decision.AUTO_MATCH, top, gap

    if top.score >= thresholds.review_min_score:
        return Decision.REVIEW, top, gap

    return Decision.UNMATCHED, None, gap
