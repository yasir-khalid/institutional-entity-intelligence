from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

_PROVENANCE_FIELDS = [
    ("source_file", pa.string()),
    ("snapshot_date", pa.string()),
    ("ingested_at", pa.string()),
]

ENTITY_SCHEMA = pa.schema(
    [
        ("lei", pa.string()),
        ("legal_name", pa.string()),
        ("legal_name_norm", pa.string()),
        ("legal_name_core", pa.string()),
        ("aliases", pa.list_(pa.string())),
        ("aliases_norm", pa.list_(pa.string())),
        ("entity_status", pa.string()),
        ("entity_category", pa.string()),
        ("jurisdiction", pa.string()),
        ("legal_form_code", pa.string()),
        ("legal_form_other", pa.string()),
        ("registration_authority_id", pa.string()),
        ("registration_id", pa.string()),
        ("registration_id_norm", pa.string()),
        ("registration_status", pa.string()),
        ("legal_address_line1", pa.string()),
        ("legal_city", pa.string()),
        ("legal_region", pa.string()),
        ("legal_postcode", pa.string()),
        ("legal_country", pa.string()),
        ("legal_address_norm", pa.string()),
        ("hq_address_line1", pa.string()),
        ("hq_city", pa.string()),
        ("hq_region", pa.string()),
        ("hq_postcode", pa.string()),
        ("hq_country", pa.string()),
        ("hq_address_norm", pa.string()),
        ("entity_creation_date", pa.string()),
        ("initial_registration_date", pa.string()),
        ("last_update_date", pa.string()),
        ("next_renewal_date", pa.string()),
        ("name_tokens", pa.list_(pa.string())),
        ("postcode_prefix", pa.string()),
        ("fund_number", pa.int32()),
        ("is_master", pa.bool_()),
        ("is_feeder", pa.bool_()),
        ("is_offshore", pa.bool_()),
        ("is_domestic", pa.bool_()),
        *_PROVENANCE_FIELDS,
    ]
)

RELATIONSHIP_SCHEMA = pa.schema(
    [
        ("start_node_id", pa.string()),
        ("start_node_id_type", pa.string()),
        ("end_node_id", pa.string()),
        ("end_node_id_type", pa.string()),
        ("relationship_type", pa.string()),
        ("relationship_status", pa.string()),
        ("start_date", pa.string()),
        ("end_date", pa.string()),
        *_PROVENANCE_FIELDS,
    ]
)

RELATIONSHIP_EXCEPTION_SCHEMA = pa.schema(
    [
        ("lei", pa.string()),
        ("exception_category", pa.string()),
        ("exception_reason", pa.string()),
        *_PROVENANCE_FIELDS,
    ]
)

ISIN_LEI_SCHEMA = pa.schema(
    [
        ("isin", pa.string()),
        ("lei", pa.string()),
        *_PROVENANCE_FIELDS,
    ]
)


class BatchedParquetWriter:
    """Accumulates row dicts and flushes to a Parquet file in bounded-memory batches."""

    def __init__(self, path: Path, schema: pa.Schema, batch_size: int = 50_000):
        self.path = path
        self.schema = schema
        self.batch_size = batch_size
        self._rows: list[dict[str, Any]] = []
        self._writer: pq.ParquetWriter | None = None
        self.total_written = 0

    def add(self, row: dict[str, Any]) -> None:
        self._rows.append(row)
        if len(self._rows) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._rows:
            return
        table = pa.Table.from_pylist(self._rows, schema=self.schema)
        if self._writer is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = pq.ParquetWriter(self.path, self.schema)
        self._writer.write_table(table)
        self.total_written += len(self._rows)
        self._rows = []

    def close(self) -> None:
        self.flush()
        if self._writer is not None:
            self._writer.close()
