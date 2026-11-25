from __future__ import annotations

from pydantic import BaseModel


class FormDOffering(BaseModel):
    accession_number: str
    file_number: str | None = None
    filing_date: str | None = None
    submission_type: str | None = None
    is_amendment: bool = False
    previous_accession_number: str | None = None
    issuer_cik: str
    issuer_name: str
    street1: str | None = None
    city: str | None = None
    state: str | None = None
    state_description: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    jurisdiction: str | None = None
    entity_type: str | None = None
    year_of_incorporation: str | None = None
    co_issuer_count: int = 0
    industry_group: str | None = None
    fund_type: str | None = None
    is_fund: bool = False
    is_40_act: bool | None = None
    revenue_range: str | None = None
    nav_range: str | None = None
    exemptions: list[str] = []
    first_sale_date: str | None = None
    first_sale_yet_to_occur: bool | None = None
    more_than_one_year: bool | None = None
    minimum_investment: float | None = None
    total_offering: float | None = None
    offering_indefinite: bool = False
    total_sold: float | None = None
    total_remaining: float | None = None
    investor_count: int | None = None
    non_accredited_count: int | None = None
    sales_commission: float | None = None
    finders_fee: float | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class FormDPerson(BaseModel):
    accession_number: str
    person_index: str
    name: str
    city: str | None = None
    state: str | None = None
    relationships: list[str] = []
    clarification: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class FormDRecipient(BaseModel):
    accession_number: str
    recipient_index: str
    name: str
    crd_number: str | None = None
    broker_dealer_name: str | None = None
    broker_dealer_crd: str | None = None
    states: list[str] = []
    foreign_solicitation: bool | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
