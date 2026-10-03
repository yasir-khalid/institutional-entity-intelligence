from __future__ import annotations

import csv
import io
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from er.config import AppConfig
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import GleifExternalIdentifier
from .schema import EXTERNAL_IDENTIFIER_SCHEMA


MAPPING_PATTERNS = {
    "BIC": ("*BIC*.zip", "BIC"),
    "MIC": ("*MIC*.zip", "MIC"),
    "OPENCORPORATES_ID": ("*oc-lei*.zip", "OpenCorporatesID"),
}
_DATE_RE = re.compile(r"(20\d{6})")


def _find_files(raw_dir: Path) -> list[tuple[str, str, Path]]:
    found: list[tuple[str, str, Path]] = []
    names = list(raw_dir.glob("*.zip"))
    for identifier_type, (pattern, column) in MAPPING_PATTERNS.items():
        matches = [path for path in names if path.match(pattern) or path.match(pattern.lower())]
        if matches:
            found.append((identifier_type, column, sorted(matches)[-1]))
    return found


def parse_mappings(cfg: AppConfig) -> int:
    files = _find_files(cfg.gleif.raw_dir)
    if not files:
        return 0

    out_path = cfg.gleif.processed_dir / "gleif_external_identifiers.parquet"
    writer = BatchedParquetWriter(out_path, EXTERNAL_IDENTIFIER_SCHEMA, cfg.gleif.batch_size)
    ingested_at = datetime.now(timezone.utc).isoformat()
    count = 0

    for identifier_type, value_column, path in files:
        match = _DATE_RE.search(path.name)
        snapshot_date = None
        if match:
            raw_date = match.group(1)
            snapshot_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        with zipfile.ZipFile(path) as archive:
            member = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
            stream = io.TextIOWrapper(archive.open(member), encoding="utf-8-sig", newline="")
            for raw in csv.DictReader(stream):
                row = GleifExternalIdentifier(
                    lei=(raw.get("LEI") or "").strip(),
                    identifier_type=identifier_type,
                    identifier_value=(raw.get(value_column) or "").strip(),
                    source_file=f"{path.name}:{member}",
                    snapshot_date=snapshot_date,
                    ingested_at=ingested_at,
                )
                writer.add(row.model_dump())
                count += 1
    writer.close()
    return count
