"""Raw data access for the relationship graph - one LEI in, matching rows out.
No business logic here (that's build.py); just lookups against the published
serving indexes (er.serving.store).
"""

from __future__ import annotations

from er.serving.store import ENTITIES, RELATIONSHIPS, Store


# Larger than any LEI's relationship count in the GLEIF data (5,497 at most),
# and within OpenSearch's default 10,000-hit window.
MAX_RELATIONSHIPS = 10_000


def fetch_relationships(store: Store, lei: str) -> list[dict]:
    return store.find(
        RELATIONSHIPS,
        either={"start_node_id": lei, "end_node_id": lei},
        size=MAX_RELATIONSHIPS,
        fields=("start_node_id", "end_node_id", "relationship_type", "relationship_status"),
    )


def fetch_relationships_among(store: Store, leis: list[str]) -> list[dict]:
    """Active relationship edges where BOTH ends are in `leis` - used to confirm
    family membership within an already-retrieved candidate pool (er.family), not
    to discover new members. See er/family/discover.py for why: expanding via
    relationships alone would pull in e.g. all 96 subsidiaries of a shared banking
    parent, most of which have nothing to do with the queried brand.
    """
    if len(leis) < 2:
        return []
    rows = store.find(
        RELATIONSHIPS,
        where={"start_node_id": list(leis), "end_node_id": list(leis)},
        size=MAX_RELATIONSHIPS,
        fields=("start_node_id", "end_node_id", "relationship_type", "relationship_status"),
    )
    return [row for row in rows if row["relationship_status"] != "INACTIVE"]


def fetch_entity(store: Store, lei: str) -> dict:
    return store.get(ENTITIES, lei, fields=("canonical_name", "exceptions")) or {}


def fetch_entity_names(store: Store, leis: list[str]) -> dict[str, str]:
    docs = store.mget(ENTITIES, leis, fields=("canonical_name",))
    return {lei: doc["canonical_name"] for lei, doc in docs.items() if doc.get("canonical_name")}
