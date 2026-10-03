from __future__ import annotations

from pydantic import BaseModel


class CompanyRecord(BaseModel):
    company_number: str
    company_name: str
    company_status: str | None = None
    company_category: str | None = None
    country_of_origin: str | None = None
    incorporation_date: str | None = None
    dissolution_date: str | None = None
    address_line1: str | None = None
    locality: str | None = None
    region: str | None = None
    postal_code: str | None = None
    sic_codes: list[str] = []
    previous_names: list[str] = []
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class PscRecord(BaseModel):
    psc_id: str
    company_number: str
    psc_type: str
    name: str
    country_of_residence: str | None = None
    nationality: str | None = None
    registration_number: str | None = None
    legal_authority: str | None = None
    legal_form: str | None = None
    natures_of_control: list[str] = []
    notified_on: str | None = None
    ceased_on: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
