"""An entity's relationships from sources other than GLEIF's own hierarchy:
bank holding company control, >5% beneficial ownership, significant control,
insider roles and LEI successions. Each kind stays its own group - they are
different claims. Built from the knowledge graph at publish time
(er.serving.publish.build_connections); read here as part of the entity
document."""

from __future__ import annotations

from er.serving.store import ENTITIES, Store

from .models import EntityConnections


def load_connections(store: Store, entity_id: str) -> EntityConnections:
    doc = store.get(ENTITIES, entity_id, fields=("connections",))
    return EntityConnections(**((doc or {}).get("connections") or {}))
