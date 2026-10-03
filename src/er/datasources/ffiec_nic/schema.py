from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


INSTITUTION_SCHEMA = pa.schema(
    [
        ("rssd_id", pa.string()),
        ("legal_name", pa.string()),
        ("short_name", pa.string()),
        ("entity_type", pa.string()),
        ("lei", pa.string()),
        ("city", pa.string()),
        ("state", pa.string()),
        ("country", pa.string()),
        ("opened_on", pa.string()),
        ("closed_on", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)

RELATIONSHIP_SCHEMA = pa.schema(
    [
        ("parent_rssd_id", pa.string()),
        ("offspring_rssd_id", pa.string()),
        ("controlled", pa.bool_()),
        ("regulatory_level", pa.string()),
        ("equity_percent", pa.float64()),
        ("start_date", pa.string()),
        ("end_date", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)

TRANSFORMATION_SCHEMA = pa.schema(
    [
        ("predecessor_rssd_id", pa.string()),
        ("successor_rssd_id", pa.string()),
        ("transformation_code", pa.string()),
        ("transformation_date", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)
