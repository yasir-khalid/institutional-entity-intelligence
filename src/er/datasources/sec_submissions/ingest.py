from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from er.config import AppConfig
from er.datasources.common.download import download_if_missing
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import SecSubmissionEntity
from .schema import SUBMISSION_ENTITY_SCHEMA


def _clean(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _address(data: dict, kind: str) -> dict[str, str | None]:
    address = data.get("addresses", {}).get(kind, {})
    prefix = "business" if kind == "business" else "mailing"
    return {
        f"{prefix}_street1": _clean(address.get("street1")),
        f"{prefix}_street2": _clean(address.get("street2")),
        f"{prefix}_city": _clean(address.get("city")),
        f"{prefix}_state_or_country": _clean(address.get("stateOrCountry")),
        f"{prefix}_zip_code": _clean(address.get("zipCode")),
    }


def _row(data: dict, provenance: dict) -> dict:
    former_names = [
        name
        for item in data.get("formerNames", [])
        if (name := _clean(item.get("name"))) is not None
    ]
    return SecSubmissionEntity(
        cik=str(data.get("cik", "")).zfill(10),
        name=str(data.get("name", "")).strip(),
        entity_type=_clean(data.get("entityType")),
        sic=_clean(data.get("sic")),
        sic_description=_clean(data.get("sicDescription")),
        ein=_clean(data.get("ein")),
        state_of_incorporation=_clean(data.get("stateOfIncorporation")),
        fiscal_year_end=_clean(data.get("fiscalYearEnd")),
        former_names=former_names,
        tickers=[str(value) for value in data.get("tickers", [])],
        exchanges=[str(value) for value in data.get("exchanges", [])],
        **_address(data, "business"),
        **_address(data, "mailing"),
        **provenance,
    ).model_dump()


def parse_zip(cfg: AppConfig, path: Path) -> int:
    out_path = cfg.sec_submissions.processed_dir / "sec_submissions.parquet"
    writer = BatchedParquetWriter(out_path, SUBMISSION_ENTITY_SCHEMA, cfg.sec_submissions.batch_size)
    ingested_at = datetime.now(timezone.utc).isoformat()
    snapshot_date = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).date().isoformat()
    count = 0

    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            if not member.endswith(".json") or not Path(member).name.startswith("CIK"):
                continue
            data = json.loads(archive.read(member))
            writer.add(
                _row(
                    data,
                    {
                        "source_file": f"{path.name}:{member}",
                        "snapshot_date": snapshot_date,
                        "ingested_at": ingested_at,
                    },
                )
            )
            count += 1
    writer.close()
    return count


def run_all(cfg: AppConfig) -> dict[str, int]:
    path = download_if_missing(
        cfg.sec_submissions.source_url,
        cfg.sec_submissions.raw_dir / cfg.sec_submissions.source_file,
    )
    return {"entities": parse_zip(cfg, path)}
