"""Assemble a HierarchyResult for one LEI: active relationships in both directions,
named via a batch entity lookup, plus any "missing parent" exceptions that aren't
already explained by an active relationship row - the project's recurring caution
that a missing relationship row does not mean a confirmed absence of a parent.
"""

from __future__ import annotations

from er.config import AppConfig
from er.graph.edges import fetch_entity_names, fetch_exceptions, fetch_relationships
from er.graph.models import (
    EXCEPTION_LABELS,
    EXCEPTION_REASONS,
    RELATIONSHIP_LABELS,
    HierarchyResult,
    RelationshipEdge,
    RelationshipException,
)

# Which relationship_type "covers" (explains away) which exception_category, so we
# don't report "no known ultimate parent" when an active IS_ULTIMATELY_CONSOLIDATED_BY
# row already answers that question.
_EXCEPTION_COVERED_BY = {
    "DIRECT_ACCOUNTING_CONSOLIDATION_PARENT": "IS_DIRECTLY_CONSOLIDATED_BY",
    "ULTIMATE_ACCOUNTING_CONSOLIDATION_PARENT": "IS_ULTIMATELY_CONSOLIDATED_BY",
}


def build_hierarchy(cfg: AppConfig, lei: str) -> HierarchyResult:
    name = fetch_entity_names(cfg, [lei]).get(lei)
    raw_relationships = fetch_relationships(cfg, lei)
    raw_exceptions = fetch_exceptions(cfg, lei)

    other_leis = {
        r["end_node_id"] if r["start_node_id"] == lei else r["start_node_id"] for r in raw_relationships
    }
    other_leis.discard(lei)
    names = fetch_entity_names(cfg, list(other_leis))

    upward: list[RelationshipEdge] = []
    downward: list[RelationshipEdge] = []
    active_upward_types: set[str] = set()

    for r in raw_relationships:
        if r["relationship_status"] == "INACTIVE":
            continue
        up_label, down_label = RELATIONSHIP_LABELS.get(
            r["relationship_type"], (r["relationship_type"], r["relationship_type"])
        )
        if r["start_node_id"] == lei:
            other = r["end_node_id"]
            upward.append(
                RelationshipEdge(
                    lei=other,
                    name=names.get(other),
                    relationship_type=r["relationship_type"],
                    status=r["relationship_status"],
                    label=up_label,
                )
            )
            active_upward_types.add(r["relationship_type"])
        else:
            other = r["start_node_id"]
            downward.append(
                RelationshipEdge(
                    lei=other,
                    name=names.get(other),
                    relationship_type=r["relationship_type"],
                    status=r["relationship_status"],
                    label=down_label,
                )
            )

    exceptions: list[RelationshipException] = []
    for e in raw_exceptions:
        category = e["exception_category"]
        covering_type = _EXCEPTION_COVERED_BY.get(category)
        if covering_type and covering_type in active_upward_types:
            continue  # an active relationship row already answers this
        exceptions.append(
            RelationshipException(
                exception_category=category,
                exception_reason=e["exception_reason"],
                label=EXCEPTION_LABELS.get(category, category),
                reason_text=EXCEPTION_REASONS.get(e["exception_reason"], e["exception_reason"]),
            )
        )

    return HierarchyResult(lei=lei, name=name, upward=upward, downward=downward, exceptions=exceptions)
