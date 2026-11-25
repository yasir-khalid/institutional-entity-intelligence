from __future__ import annotations

from pydantic import BaseModel


class FailToDeliver(BaseModel):
    settlement_date: str
    cusip: str
    symbol: str | None = None
    quantity: int
    description: str | None = None
    price: float | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
