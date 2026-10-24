"""Portable backups of runtime-owned research metadata; never replace a job.

Institutional source data remains authoritative in processed Parquet. Saved
research, like human reviews, is authored at runtime and explicitly exported.
The versioned JSON envelope preserves addressed evidence and trace payloads.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from er.serving.store import INVESTIGATIONS, Store
from er.workspace.research import ACTIVE, now


def export_investigations(store: Store, path: Path) -> int:
    if path.exists():
        raise ValueError("Backup already exists; choose a new destination to preserve it.")
    documents = list(store.scan(INVESTIGATIONS))
    rows = [{"version": 1, "document": json.dumps(doc)} for doc in documents]
    table = pa.Table.from_pylist(rows, schema=pa.schema([("version", pa.int32()), ("document", pa.string())]))
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".research-backup-", suffix=".parquet", dir=path.parent)
    os.close(handle)
    try:
        pq.write_table(table, temporary)
        # Install only the complete file, without overwriting a concurrent
        # export to the same destination. The temporary is on the same volume.
        os.link(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return len(rows)


def restore_investigations(store: Store, path: Path) -> dict[str, int]:
    # Validate the whole backup before creating anything. Existing conversations
    # are never overwritten, including jobs currently owned by another worker.
    documents = []
    for row in pq.read_table(path).to_pylist():
        if row.get("version") != 1:
            raise ValueError("Unsupported research backup version")
        doc = json.loads(row["document"])
        if (not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", doc.get("id", "")) or
            doc.get("status") not in (*ACTIVE, "succeeded", "failed", "canceled") or
            not isinstance(doc.get("turns"), list) or not isinstance(doc.get("events"), list) or
            not isinstance(doc.get("question"), str) or not isinstance(doc.get("title"), str) or
            not isinstance(doc.get("attempts"), int) or not doc.get("request_id")):
            raise ValueError("Invalid research backup document")
        if any(not isinstance(turn, dict) or not isinstance(turn.get("question"), str) or
               not isinstance(turn.get("result"), dict) or not isinstance(turn["result"].get("answer"), str)
               for turn in doc["turns"]):
            raise ValueError("Invalid research backup answer")
        doc = {**doc, "revision": 0, "lease_owner": None, "lease_until": None, "updated_at": now()}
        if doc["status"] in ACTIVE:
            doc.update(status="queued", attempts=0, events=[])
        documents.append(doc)
    restored = sum(store.compare_and_put(INVESTIGATIONS, doc["id"], None, doc) for doc in documents)
    return {"restored": restored, "skipped_existing": len(documents) - restored}
