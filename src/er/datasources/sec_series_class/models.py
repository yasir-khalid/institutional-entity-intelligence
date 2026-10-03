from __future__ import annotations

from pydantic import BaseModel


class SecSeriesClass(BaseModel):
    reporting_file_number: str
    cik: str
    entity_name: str
    entity_org_type: str | None = None
    series_id: str
    series_name: str
    class_id: str | None = None
    class_name: str | None = None
    class_ticker: str | None = None
    address_1: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
