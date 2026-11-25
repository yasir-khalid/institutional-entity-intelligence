from __future__ import annotations

from pydantic import BaseModel


class ShortVolume(BaseModel):
    trade_date: str
    symbol: str
    short_volume: float
    short_exempt_volume: float | None = None
    total_volume: float
    markets: list[str] = []
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
