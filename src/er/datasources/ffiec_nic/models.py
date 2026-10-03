from __future__ import annotations

from pydantic import BaseModel


class NicInstitution(BaseModel):
    rssd_id: str
    legal_name: str
    short_name: str | None = None
    entity_type: str | None = None
    lei: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    opened_on: str | None = None
    closed_on: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class NicRelationship(BaseModel):
    parent_rssd_id: str
    offspring_rssd_id: str
    controlled: bool
    regulatory_level: str | None = None
    equity_percent: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class NicTransformation(BaseModel):
    predecessor_rssd_id: str
    successor_rssd_id: str
    transformation_code: str | None = None
    transformation_date: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
