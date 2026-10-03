from __future__ import annotations

from pydantic import BaseModel


class InsiderRelationship(BaseModel):
    accession_number: str
    filing_date: str | None = None
    period_of_report: str | None = None
    document_type: str | None = None
    issuer_cik: str
    issuer_name: str
    issuer_ticker: str | None = None
    owner_cik: str
    owner_name: str
    relationship: str | None = None
    owner_title: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class InsiderTransaction(BaseModel):
    accession_number: str
    transaction_id: str
    owner_cik: str
    issuer_cik: str
    security_title: str | None = None
    transaction_date: str | None = None
    transaction_code: str | None = None
    acquired_disposed: str | None = None
    shares: float | None = None
    price_per_share: float | None = None
    shares_following: float | None = None
    direct_indirect: str | None = None
    derivative: bool = False
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
