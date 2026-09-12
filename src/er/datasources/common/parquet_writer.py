"""Generic streaming Parquet writer, shared across all data sources.

Deliberately source-agnostic: no schema knowledge, no source-specific logic. Each
source's own ingest module supplies its own pyarrow schema (see e.g.
er.datasources.gleif.schema) - this class only handles bounded-memory batching and
the actual file write.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

# Provenance columns every source's schema should include - see individual source
# schema modules for how they're spliced in.
PROVENANCE_FIELDS = [
    ("source_file", pa.string()),
    ("snapshot_date", pa.string()),
    ("ingested_at", pa.string()),
]


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
