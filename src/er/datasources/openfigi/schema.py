from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


MAPPING_SCHEMA = pa.schema(
    [
        ("cusip", pa.string()),
        ("mapping_rank", pa.int32()),
        ("figi", pa.string()),
        ("name", pa.string()),
        ("ticker", pa.string()),
        ("exchange_code", pa.string()),
        ("market_sector", pa.string()),
        ("security_type", pa.string()),
        ("security_type_2", pa.string()),
        ("share_class_figi", pa.string()),
        ("composite_figi", pa.string()),
        ("error", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)
