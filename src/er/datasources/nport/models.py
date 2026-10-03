from __future__ import annotations

from pydantic import BaseModel


class NPortFund(BaseModel):
    accession_number: str
    filing_date: str | None = None
    report_date: str | None = None
    cik: str | None = None
    registrant_name: str | None = None
    registrant_lei: str | None = None
    series_id: str | None = None
    series_name: str | None = None
    series_lei: str | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    net_assets: float | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class NPortHolding(BaseModel):
    accession_number: str
    holding_id: str
    issuer_name: str | None = None
    issuer_lei: str | None = None
    issuer_title: str | None = None
    issuer_cusip: str | None = None
    isin: str | None = None
    ticker: str | None = None
    balance: float | None = None
    unit: str | None = None
    currency_code: str | None = None
    currency_value: float | None = None
    exchange_rate: float | None = None
    percentage: float | None = None
    payoff_profile: str | None = None
    asset_category: str | None = None
    issuer_type: str | None = None
    investment_country: str | None = None
    fair_value_level: str | None = None
    derivative_category: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
