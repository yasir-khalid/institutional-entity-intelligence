from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


SERIES_CLASS_SCHEMA = pa.schema(
    [
        ("reporting_file_number", pa.string()),
        ("cik", pa.string()),
        ("entity_name", pa.string()),
        ("entity_org_type", pa.string()),
        ("series_id", pa.string()),
        ("series_name", pa.string()),
        ("class_id", pa.string()),
        ("class_name", pa.string()),
        ("class_ticker", pa.string()),
        ("address_1", pa.string()),
        ("address_2", pa.string()),
        ("city", pa.string()),
        ("state", pa.string()),
        ("zip_code", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)
