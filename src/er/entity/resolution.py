"""The stored decisions linking other sources' records to an LEI, and the
human reviews of them. A review is written as its own dated document - the
automated decision is never edited. Reviews are the one thing the API writes,
so OpenSearch is their system of record; `make pull-reviews` copies them down
for er.knowledge.build, which applies the latest review per pair."""

from __future__ import annotations

import csv
import uuid
from datetime import datetime, timezone
from pathlib import Path

from er.serving.store import ENTITIES, REVIEWS, Store

from .models import MatchDecisionRecord, MatchReview


OUTCOMES = ("CONFIRMED", "REJECTED")
REVIEW_COLUMNS = ["node_id", "lei", "outcome", "reviewer", "reviewed_at", "rationale"]


def load_reviews(store: Store, lei: str) -> list[MatchReview]:
    return [
        MatchReview(**doc)
        for doc in store.find(REVIEWS, where={"lei": lei}, sort=(("reviewed_at", "asc"),), size=1000)
    ]


def record_review(
    store: Store, node_id: str, lei: str, outcome: str, reviewer: str, rationale: str | None
) -> MatchReview:
    outcome = outcome.upper()
    if outcome not in OUTCOMES:
        raise ValueError(f"outcome must be one of {OUTCOMES}")
    if not reviewer.strip():
        raise ValueError("a review needs a reviewer")
    review = MatchReview(
        node_id=node_id,
        lei=lei,
        outcome=outcome,
        reviewer=reviewer.strip(),
        reviewed_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        rationale=(rationale or "").strip() or None,
    )
    store.put(REVIEWS, uuid.uuid4().hex, review.model_dump())
    return review


def export_reviews(store: Store, path: Path) -> int:
    """Writes every review to the CSV er.knowledge.build reads."""
    reviews = sorted(store.scan(REVIEWS), key=lambda review: (review["reviewed_at"], review["node_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=REVIEW_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(reviews)
    return len(reviews)


def load_match_decisions(store: Store, lei: str) -> list[MatchDecisionRecord]:
    """Every 13F crosswalk decision that chose this LEI (auto-matched or sent
    to review), plus each one's reviews."""
    doc = store.get(ENTITIES, lei, fields=("match_decisions",))
    decisions = (doc or {}).get("match_decisions") or []
    if not decisions:
        return []
    reviews = load_reviews(store, lei)
    return [
        MatchDecisionRecord(
            **decision,
            reviews=[review for review in reviews if review.node_id == decision["node_id"]],
        )
        for decision in decisions
    ]
