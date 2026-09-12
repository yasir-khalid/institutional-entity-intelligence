from __future__ import annotations

from pydantic import BaseModel

# relationship_type -> (label when I point UP to it, label when it points DOWN to me)
# "up" = this entity is the start_node (child/subordinate) pointing at the row's end_node.
# "down" = this entity is the end_node (parent/superior) with the row's start_node pointing at it.
RELATIONSHIP_LABELS: dict[str, tuple[str, str]] = {
    "IS_DIRECTLY_CONSOLIDATED_BY": ("Direct parent", "Subsidiaries (direct)"),
    "IS_ULTIMATELY_CONSOLIDATED_BY": ("Ultimate parent", "Subsidiaries (ultimate)"),
    "IS_FUND-MANAGED_BY": ("Managed by", "Funds managed"),
    "IS_SUBFUND_OF": ("Umbrella / parent fund", "Sub-funds"),
    "IS_FEEDER_TO": ("Feeds into (master fund)", "Feeder funds"),
    "IS_INTERNATIONAL_BRANCH_OF": ("Head office", "Branches"),
}

# exception_category (always describes a missing PARENT relationship) -> display label
EXCEPTION_LABELS: dict[str, str] = {
    "DIRECT_ACCOUNTING_CONSOLIDATION_PARENT": "Direct parent",
    "ULTIMATE_ACCOUNTING_CONSOLIDATION_PARENT": "Ultimate parent",
}

# exception_reason -> human-readable explanation of why no relationship row exists
EXCEPTION_REASONS: dict[str, str] = {
    "NATURAL_PERSONS": "parent is a natural person, not a legal entity",
    "NON_CONSOLIDATING": "entity does not prepare consolidated accounts",
    "NO_KNOWN_PERSON": "no known parent",
    "NO_LEI": "parent has no LEI",
    "NON_PUBLIC": "parent information is non-public",
}


class RelationshipEdge(BaseModel):
    lei: str
    name: str | None
    relationship_type: str
    status: str | None
    label: str


class RelationshipException(BaseModel):
    exception_category: str
    exception_reason: str
    label: str
    reason_text: str


class HierarchyResult(BaseModel):
    lei: str
    name: str | None
    upward: list[RelationshipEdge] = []
    downward: list[RelationshipEdge] = []
    exceptions: list[RelationshipException] = []


class HierarchyNode(BaseModel):
    """A node in a multi-hop hierarchy traversal. relationship_type/label/status
    describe the edge connecting this node to its parent in the traversal (None
    for the root, which has no incoming edge). `expanded=False` means this node's
    own relationships were not fetched - it's a leaf either because `depth` was
    exhausted or because it was already visited elsewhere (cycle protection) or
    the traversal's node budget ran out.
    """

    lei: str
    name: str | None
    relationship_type: str | None = None
    label: str | None = None
    status: str | None = None
    expanded: bool = True
    exceptions: list[RelationshipException] = []
    upward: list["HierarchyNode"] = []
    downward: list["HierarchyNode"] = []
