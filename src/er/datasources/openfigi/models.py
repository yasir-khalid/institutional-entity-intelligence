from __future__ import annotations

from pydantic import BaseModel


class OpenFigiMapping(BaseModel):
    cusip: str
    mapping_rank: int
    figi: str | None = None
    name: str | None = None
    ticker: str | None = None
    exchange_code: str | None = None
    market_sector: str | None = None
    security_type: str | None = None
    security_type_2: str | None = None
    share_class_figi: str | None = None
    composite_figi: str | None = None
    error: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
