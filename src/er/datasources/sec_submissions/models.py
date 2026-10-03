from __future__ import annotations

from pydantic import BaseModel


class SecSubmissionEntity(BaseModel):
    cik: str
    name: str
    entity_type: str | None = None
    sic: str | None = None
    sic_description: str | None = None
    ein: str | None = None
    state_of_incorporation: str | None = None
    fiscal_year_end: str | None = None
    former_names: list[str] = []
    tickers: list[str] = []
    exchanges: list[str] = []
    business_street1: str | None = None
    business_street2: str | None = None
    business_city: str | None = None
    business_state_or_country: str | None = None
    business_zip_code: str | None = None
    mailing_street1: str | None = None
    mailing_street2: str | None = None
    mailing_city: str | None = None
    mailing_state_or_country: str | None = None
    mailing_zip_code: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
