from __future__ import annotations

from pydantic import BaseModel


class Sec13FFiling(BaseModel):
    """One filing (SUBMISSION + COVERPAGE joined on ACCESSION_NUMBER) - the filer's
    identity and metadata for a single quarterly 13F report."""

    accession_number: str
    filing_date: str | None = None
    submission_type: str | None = None
    cik: str
    period_of_report: str | None = None

    is_amendment: bool = False
    amendment_no: str | None = None
    amendment_type: str | None = None

    filer_name: str
    filer_name_norm: str = ""
    filer_name_core: str = ""
    filer_street1: str | None = None
    filer_street2: str | None = None
    filer_city: str | None = None
    filer_state_or_country: str | None = None
    filer_zipcode: str | None = None

    report_type: str | None = None
    form13f_file_number: str | None = None
    crd_number: str | None = None
    sec_file_number: str | None = None

    # provenance
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class Sec13FHolding(BaseModel):
    """One row of INFOTABLE - a single reported security position within a filing."""

    accession_number: str
    infotable_sk: str | None = None
    name_of_issuer: str
    title_of_class: str | None = None
    cusip: str | None = None
    figi: str | None = None
    value: int | None = None
    shares_or_principal_amount: float | None = None
    shares_or_principal_type: str | None = None
    put_call: str | None = None
    investment_discretion: str | None = None
    other_manager: str | None = None
    voting_auth_sole: int | None = None
    voting_auth_shared: int | None = None
    voting_auth_none: int | None = None

    # provenance
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class Sec13FValidation(BaseModel):
    accession_number: str
    declared_entry_total: int | None = None
    observed_entry_total: int
    declared_value_total: int | None = None
    observed_value_total: int
    value_unit: str
    row_count_matches: bool
    value_total_matches: bool
    amendment_action: str
    valid: bool
    errors: list[str] = []
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class Sec13FOtherManager(BaseModel):
    accession_number: str
    other_manager_sk: str
    cik: str | None = None
    form13f_file_number: str | None = None
    crd_number: str | None = None
    sec_file_number: str | None = None
    name: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
