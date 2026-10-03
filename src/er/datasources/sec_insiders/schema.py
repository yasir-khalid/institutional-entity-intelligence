from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


RELATIONSHIP_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("filing_date", pa.string()),
        ("period_of_report", pa.string()),
        ("document_type", pa.string()),
        ("issuer_cik", pa.string()),
        ("issuer_name", pa.string()),
        ("issuer_ticker", pa.string()),
        ("owner_cik", pa.string()),
        ("owner_name", pa.string()),
        ("relationship", pa.string()),
        ("owner_title", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)

TRANSACTION_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("transaction_id", pa.string()),
        ("owner_cik", pa.string()),
        ("issuer_cik", pa.string()),
        ("security_title", pa.string()),
        ("transaction_date", pa.string()),
        ("transaction_code", pa.string()),
        ("acquired_disposed", pa.string()),
        ("shares", pa.float64()),
        ("price_per_share", pa.float64()),
        ("shares_following", pa.float64()),
        ("direct_indirect", pa.string()),
        ("derivative", pa.bool_()),
        *PROVENANCE_FIELDS,
    ]
)
