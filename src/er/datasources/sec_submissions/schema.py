from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


SUBMISSION_ENTITY_SCHEMA = pa.schema(
    [
        ("cik", pa.string()),
        ("name", pa.string()),
        ("entity_type", pa.string()),
        ("sic", pa.string()),
        ("sic_description", pa.string()),
        ("ein", pa.string()),
        ("state_of_incorporation", pa.string()),
        ("fiscal_year_end", pa.string()),
        ("former_names", pa.list_(pa.string())),
        ("tickers", pa.list_(pa.string())),
        ("exchanges", pa.list_(pa.string())),
        ("business_street1", pa.string()),
        ("business_street2", pa.string()),
        ("business_city", pa.string()),
        ("business_state_or_country", pa.string()),
        ("business_zip_code", pa.string()),
        ("mailing_street1", pa.string()),
        ("mailing_street2", pa.string()),
        ("mailing_city", pa.string()),
        ("mailing_state_or_country", pa.string()),
        ("mailing_zip_code", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)
