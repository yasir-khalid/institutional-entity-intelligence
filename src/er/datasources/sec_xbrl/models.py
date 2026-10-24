"""Raw -> cleaned boundary for SEC XBRL company facts.

One XbrlFact is one reported numeric value: an issuer (cik), a concept (tag),
the unit it is stated in, the value, the period it describes (period_end, with
period_start for a duration concept like revenue), and the filing that reported
it (form, filed, accession_number). `filed` is the knowledge time - what a
reader could have known on that date - which is what makes a point-in-time
question answerable; storing only the latest value would destroy it.
"""

from __future__ import annotations

from pydantic import BaseModel


class XbrlFact(BaseModel):
    cik: str
    entity_name: str
    taxonomy: str
    tag: str
    label: str | None = None
    unit: str
    value: float
    period_start: str | None = None
    period_end: str
    fiscal_year: int | None = None
    fiscal_period: str | None = None
    form: str | None = None
    filed: str
    accession_number: str | None = None
    frame: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None


class XbrlIssuer(BaseModel):
    cik: str
    entity_name: str
    tickers: list[str] = []
    former_names: list[str] = []
    sic: str | None = None
    sic_description: str | None = None
    fiscal_year_end: str | None = None
    source_file: str | None = None
    snapshot_date: str | None = None
    ingested_at: str | None = None
