from __future__ import annotations

from pydantic import BaseModel


class BeneficialOwnership(BaseModel):
    accession_number: str
    form_type: str
    filing_intent: str
    filing_date: str
    event_date: str | None = None
    filer_cik: str | None = None
    issuer_cik: str
    issuer_name: str | None = None
    issuer_cusip: str | None = None
    security_class: str | None = None
    rule_designation: str | None = None
    person_index: int
    reporting_person_cik: str | None = None
    reporting_person_name: str
    reporting_person_type: str | None = None
    citizenship_or_organization: str | None = None
    aggregate_shares: float | None = None
    percent_of_class: float | None = None
    sole_voting_power: float | None = None
    shared_voting_power: float | None = None
    sole_dispositive_power: float | None = None
    shared_dispositive_power: float | None = None
    document_url: str
    content_hash: str
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
