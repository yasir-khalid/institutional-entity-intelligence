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
    HierarchyNode,
    HierarchyResult,
    RelationshipEdge,
    RelationshipException,
)

DEFAULT_MAX_NODES = 200

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


def build_hierarchy_tree(
    cfg: AppConfig,
    lei: str,
    depth: int = 1,
    direction: str = "all",
    max_nodes: int = DEFAULT_MAX_NODES,
) -> HierarchyNode:
    """Multi-hop version of build_hierarchy(): depth=1 (the default) is exactly
    today's single-hop behavior - each edge is a leaf carrying only its own
    name/type, not expanded further. depth=2 expands one more level past that, etc.

    Cycle protection: a LEI is only ever expanded once across the whole traversal,
    even if reachable via multiple paths (real GLEIF data can have cycles, e.g. two
    entities that are each other's direct/ultimate parent in different accounting
    contexts). max_nodes caps total expansions - hub nodes (an ultimate parent with
    dozens of subsidiaries) can otherwise make a deep traversal explode; once the
    budget is spent, remaining nodes are returned unexpanded (`expanded=False`)
    rather than the traversal silently running away or erroring.
    """
    visited: set[str] = set()
    budget = {"remaining": max_nodes}

    def expand(node_lei: str, remaining_depth: int) -> HierarchyNode:
        visited.add(node_lei)
        budget["remaining"] -= 1
        flat = build_hierarchy(cfg, node_lei)
        node = HierarchyNode(lei=node_lei, name=flat.name, exceptions=flat.exceptions)

        can_recurse = remaining_depth > 1 and budget["remaining"] > 0

        def expand_or_leaf(edge: RelationshipEdge) -> HierarchyNode:
            if can_recurse and edge.lei not in visited:
                child = expand(edge.lei, remaining_depth=remaining_depth - 1)
            else:
                child = HierarchyNode(lei=edge.lei, name=edge.name, expanded=False)
            child.relationship_type = edge.relationship_type
            child.label = edge.label
            child.status = edge.status
            return child

        if direction in ("parents", "all"):
            for edge in flat.upward:
                node.upward.append(expand_or_leaf(edge))
        if direction in ("children", "all"):
            for edge in flat.downward:
                node.downward.append(expand_or_leaf(edge))
        return node

    return expand(lei, remaining_depth=depth)
