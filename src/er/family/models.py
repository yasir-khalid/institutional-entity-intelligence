from __future__ import annotations

from pydantic import BaseModel


class FamilyMember(BaseModel):
    lei: str
    legal_name: str
    jurisdiction: str | None = None
    role: str  # "management" | "fund" - see brand.guess_role
    confidence: str  # "high" | "possible"
    graph_confirmed: bool = False


class RelationshipEvidence(BaseModel):
    from_lei: str
    from_name: str | None
    relationship_type: str
    to_lei: str
    to_name: str | None


class FamilyResult(BaseModel):
    query_name: str
    brand_core: str
    members: list[FamilyMember] = []
    relationship_evidence: list[RelationshipEvidence] = []
