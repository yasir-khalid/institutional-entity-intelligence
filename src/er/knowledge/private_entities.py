"""Curated private-entity registry for SPVs and project companies.

GLEIF is the spine for registered legal entities, but a bankruptcy-remote
project SPV often has no LEI. Returning unrelated "Investor LLC" matches for
"Beignet Investor LLC" is worse than saying "this is a provisional, curated
record". This module is deliberately small: it holds public, cited facts about
named private entities, never merges them into the GLEIF canonical layer, and
always labels them PROVISIONAL.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from er.config import REPO_ROOT

DEFAULT_PATH = REPO_ROOT / "config" / "private_entities.json"


@dataclass(frozen=True)
class PrivateSource:
    id: str
    title: str
    publisher: str
    published_at: str | None
    url: str | None


@dataclass
class PrivateRelationship:
    to: str
    type: str
    label: str | None = None
    pct: float | None = None
    as_of: str | None = None
    source_ids: list[str] = field(default_factory=list)


@dataclass
class PrivateEntity:
    id: str
    name: str
    aliases: list[str]
    entity_type: str
    jurisdiction: str | None
    registration_id: str | None
    registration_authority: str | None
    status: str
    confidence: str
    notes: str
    source_ids: list[str]
    relationships: list[PrivateRelationship]

    @property
    def searchable(self) -> str:
        return " ".join([self.name, *self.aliases, self.id]).lower()

    def payload(self, sources: dict[str, PrivateSource], by_id: dict[str, "PrivateEntity"]) -> dict[str, Any]:
        outgoing = [
            {
                "direction": "outgoing",
                "from_id": self.id,
                "from_name": self.name,
                "to_id": r.to,
                "to_name": by_id[r.to].name if r.to in by_id else r.to,
                "type": r.type,
                "label": r.label,
                "pct": r.pct,
                "as_of": r.as_of,
                "sources": [_source_payload(s, sources) for s in r.source_ids if s in sources],
            }
            for r in self.relationships
        ]
        incoming = [
            {
                "direction": "incoming",
                "from_id": other.id,
                "from_name": other.name,
                "to_id": self.id,
                "to_name": self.name,
                "type": r.type,
                "label": r.label,
                "pct": r.pct,
                "as_of": r.as_of,
                "sources": [_source_payload(s, sources) for s in r.source_ids if s in sources],
            }
            for other in by_id.values()
            for r in other.relationships
            if r.to == self.id
        ]
        return {
            "entity_id": self.id,
            "name": self.name,
            "aliases": self.aliases,
            "entity_type": self.entity_type,
            "jurisdiction": self.jurisdiction,
            "registration_id": self.registration_id,
            "registration_authority": self.registration_authority,
            "status": self.status,
            "resolution_status": "PROVISIONAL",
            "provisional": True,
            "lei": None,
            "confidence": self.confidence,
            "notes": self.notes,
            "sources": [_source_payload(s, sources) for s in self.source_ids if s in sources],
            "relationships": outgoing + incoming,
        }


def _source_payload(source_id: str, sources: dict[str, PrivateSource]) -> dict[str, Any]:
    s = sources[source_id]
    return {
        "source_id": s.id,
        "title": s.title,
        "publisher": s.publisher,
        "published_at": s.published_at,
        "url": s.url,
    }


class PrivateEntityRegistry:
    def __init__(self, sources: dict[str, PrivateSource], entities: dict[str, PrivateEntity]) -> None:
        self.sources = sources
        self.entities = entities

    def find(self, query: str, jurisdiction: str | None = None, limit: int = 10) -> list[PrivateEntity]:
        q = query.strip().lower()
        if not q:
            return []
        exact = [
            e for e in self.entities.values()
            if e.id.lower() == q or e.name.lower() == q or any(a.lower() == q for a in e.aliases)
        ]
        pool = exact or [e for e in self.entities.values() if q in e.searchable]
        if jurisdiction:
            pool = [e for e in pool if (e.jurisdiction or "").upper() == jurisdiction.upper()]
        pool.sort(key=lambda e: (0 if e in exact else 1, len(e.name), e.name))
        return pool[:limit]

    def get(self, entity_id: str) -> PrivateEntity | None:
        return self.entities.get(entity_id)

    def payload(self, entity: PrivateEntity) -> dict[str, Any]:
        return entity.payload(self.sources, self.entities)


def load_private_entities(path: str | Path | None = None) -> PrivateEntityRegistry:
    path = Path(path or DEFAULT_PATH)
    raw = json.loads(path.read_text())
    sources = {
        s["id"]: PrivateSource(
            id=s["id"], title=s["title"], publisher=s["publisher"],
            published_at=s.get("published_at"), url=s.get("url"),
        )
        for s in raw.get("sources", [])
    }
    entities: dict[str, PrivateEntity] = {}
    for item in raw.get("entities", []):
        relations = [
            PrivateRelationship(
                to=r["to"], type=r["type"], label=r.get("label"), pct=r.get("pct"),
                as_of=r.get("as_of"), source_ids=r.get("source_ids", []),
            )
            for r in item.get("relationships", [])
        ]
        entity = PrivateEntity(
            id=item["id"], name=item["name"], aliases=item.get("aliases", []),
            entity_type=item.get("entity_type", "private_company"),
            jurisdiction=item.get("jurisdiction"), registration_id=item.get("registration_id"),
            registration_authority=item.get("registration_authority"), status=item.get("status", "active"),
            confidence=item.get("confidence", "public_source"),
            notes=item.get("notes", ""), source_ids=item.get("source_ids", []), relationships=relations,
        )
        for sid in entity.source_ids:
            if sid not in sources:
                raise ValueError(f"private entity {entity.id} references unknown source {sid}")
        for rel in relations:
            if rel.to not in entities and rel.to not in {x["id"] for x in raw.get("entities", [])}:
                raise ValueError(f"private entity {entity.id} relationship references unknown entity {rel.to}")
            for sid in rel.source_ids:
                if sid not in sources:
                    raise ValueError(f"private entity {entity.id} relationship references unknown source {sid}")
        entities[entity.id] = entity
    return PrivateEntityRegistry(sources, entities)
