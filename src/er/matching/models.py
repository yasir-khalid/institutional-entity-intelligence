from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class Decision(str, Enum):
    AUTO_MATCH = "AUTO_MATCH"
    REVIEW = "REVIEW"
    UNMATCHED = "UNMATCHED"


class CandidateScore(BaseModel):
    lei: str
    legal_name: str
    jurisdiction: str | None = None
    score: float  # match/ER evidence score - "how much evidence says these are the same entity"
    retrieval_score: float | None = None  # raw OpenSearch relevance - "how useful is this as a candidate"
    rank: int
    evidence: dict[str, float] = {}


class MatchResult(BaseModel):
    query_name: str
    decision: Decision
    lei: str | None = None
    score: float | None = None
    gap: float | None = None
    evidence: dict[str, float] = {}
    candidates: list[CandidateScore] = []
    # Populated only for REVIEW/UNMATCHED: why the matcher didn't auto-match, what
    # additional evidence would help, and (when the failure is a genuine tie between
    # multiple plausible entities) which ones are competing.
    reason: str | None = None
    missing_evidence: list[str] = []
    competing_candidates: list[CandidateScore] = []
