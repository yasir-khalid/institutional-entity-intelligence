from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


XBRL_FACT_SCHEMA = pa.schema(
    [
        ("cik", pa.string()),
        ("entity_name", pa.string()),
        ("taxonomy", pa.string()),
        ("tag", pa.string()),
        ("label", pa.string()),
        ("unit", pa.string()),
        ("value", pa.float64()),
        ("period_start", pa.string()),
        ("period_end", pa.string()),
        ("fiscal_year", pa.int64()),
        ("fiscal_period", pa.string()),
        ("form", pa.string()),
        ("filed", pa.string()),
        ("accession_number", pa.string()),
        ("frame", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)

XBRL_ISSUER_SCHEMA = pa.schema(
    [
        ("cik", pa.string()),
        ("entity_name", pa.string()),
        ("tickers", pa.list_(pa.string())),
        ("former_names", pa.list_(pa.string())),
        ("sic", pa.string()),
        ("sic_description", pa.string()),
        ("fiscal_year_end", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)
