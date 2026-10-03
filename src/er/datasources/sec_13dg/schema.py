from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


OWNERSHIP_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("form_type", pa.string()),
        ("filing_intent", pa.string()),
        ("filing_date", pa.string()),
        ("event_date", pa.string()),
        ("filer_cik", pa.string()),
        ("issuer_cik", pa.string()),
        ("issuer_name", pa.string()),
        ("issuer_cusip", pa.string()),
        ("security_class", pa.string()),
        ("rule_designation", pa.string()),
        ("person_index", pa.int32()),
        ("reporting_person_cik", pa.string()),
        ("reporting_person_name", pa.string()),
        ("reporting_person_type", pa.string()),
        ("citizenship_or_organization", pa.string()),
        ("aggregate_shares", pa.float64()),
        ("percent_of_class", pa.float64()),
        ("sole_voting_power", pa.float64()),
        ("shared_voting_power", pa.float64()),
        ("sole_dispositive_power", pa.float64()),
        ("shared_dispositive_power", pa.float64()),
        ("document_url", pa.string()),
        ("content_hash", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)
