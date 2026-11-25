from __future__ import annotations

from pydantic import BaseModel, field_validator


class AdvFirm(BaseModel):
    crd_number: str
    snapshot_date: str
    firm_type: str | None = None
    sec_number: str | None = None
    cik: str | None = None
    lei: str | None = None
    business_name: str
    legal_name: str | None = None
    street1: str | None = None
    street2: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    postal_code: str | None = None
    phone: str | None = None
    website: str | None = None
    sec_status: str | None = None
    latest_filing_date: str | None = None
    legal_form: str | None = None
    employees: int | None = None
    advisory_employees: int | None = None
    raum_discretionary: float | None = None
    raum_non_discretionary: float | None = None
    raum: float | None = None
    accounts_discretionary: int | None = None
    accounts_non_discretionary: int | None = None
    accounts: int | None = None
    raum_non_us: float | None = None
    private_fund_count: int | None = None
    private_fund_gross_assets: float | None = None
    hedge_fund_count: int | None = None
    liquidity_fund_count: int | None = None
    pe_fund_count: int | None = None
    real_estate_fund_count: int | None = None
    securitized_fund_count: int | None = None
    vc_fund_count: int | None = None
    other_fund_count: int | None = None
    source_file: str | None = None
    ingested_at: str | None = None

    @field_validator("cik")
    @classmethod
    def _pad_cik(cls, value: str | None) -> str | None:
        return value.zfill(10) if value and value.isdigit() else None

    @field_validator("lei")
    @classmethod
    def _lei(cls, value: str | None) -> str | None:
        value = (value or "").strip().upper()
        return value if len(value) == 20 and value.isalnum() else None


class AdvClientType(BaseModel):
    crd_number: str
    snapshot_date: str
    client_type: str
    client_count: int | None = None
    fewer_than_five: bool = False
    raum: float | None = None
    source_file: str | None = None
    ingested_at: str | None = None
