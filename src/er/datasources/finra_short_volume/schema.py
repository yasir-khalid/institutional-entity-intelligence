from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


SHORT_VOLUME_SCHEMA = pa.schema(
    [
        ("trade_date", pa.string()),
        ("symbol", pa.string()),
        ("short_volume", pa.float64()),
        ("short_exempt_volume", pa.float64()),
        ("total_volume", pa.float64()),
        ("markets", pa.list_(pa.string())),
        *PROVENANCE_FIELDS,
    ]
)
