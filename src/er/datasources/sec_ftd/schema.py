from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


FTD_SCHEMA = pa.schema(
    [
        ("settlement_date", pa.string()),
        ("cusip", pa.string()),
        ("symbol", pa.string()),
        ("quantity", pa.int64()),
        ("description", pa.string()),
        ("price", pa.float64()),
        *PROVENANCE_FIELDS,
    ]
)
