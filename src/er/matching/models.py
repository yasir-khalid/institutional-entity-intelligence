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
    score: float
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
