from __future__ import annotations

from pydantic import BaseModel


class SecAdvBrochure(BaseModel):
    firm_name: str
    sec_number: str
    crd_number: str
    filing_id: str
    brochure_name: str
    brochure_id: str
    brochure_version: str
    date_filed: str
    pdf_file_name: str
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class SecAdvDocument(BaseModel):
    crd_number: str
    brochure_id: str
    pdf_file_name: str
    content_hash: str | None = None
    page_count: int = 0
    extraction_error: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class SecAdvPage(BaseModel):
    crd_number: str
    brochure_id: str
    pdf_file_name: str
    page_number: int
    text: str
    content_hash: str
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
