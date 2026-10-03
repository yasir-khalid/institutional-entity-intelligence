from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from er.config import AppConfig
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import CompanyRecord, PscRecord
from .schema import COMPANY_SCHEMA, PSC_SCHEMA


_DATE = re.compile(r"(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)")


def _snapshot_date(path: Path) -> str | None:
    match = _DATE.search(path.name)
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}" if match else None


def _clean(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", newline="")
    return path.open(encoding="utf-8-sig", newline="")


@contextmanager
def _company_stream(path: Path):
    if path.suffix.lower() != ".zip":
        with _open_text(path) as stream:
            yield stream
        return
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not members:
            raise ValueError(f"{path.name} contains no CSV")
        with archive.open(members[0]) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig", newline="") as stream:
            yield stream


def _psc_lines(path: Path):
    if path.suffix.lower() != ".zip":
        with _open_text(path) as stream:
            for line in stream:
                yield path.name, line
        return
    with zipfile.ZipFile(path) as archive:
        for member in archive.namelist():
            if not member.lower().endswith((".txt", ".jsonl")):
                continue
            with archive.open(member) as raw, io.TextIOWrapper(raw, encoding="utf-8-sig") as stream:
                for line in stream:
                    yield f"{path.name}:{member}", line


def parse_companies(cfg: AppConfig, path: Path) -> int:
    writer = BatchedParquetWriter(
        cfg.companies_house.processed_dir / "companies_house_companies.parquet",
        COMPANY_SCHEMA,
        cfg.companies_house.batch_size,
    )
    provenance = {
        "source_file": path.name,
        "snapshot_date": _snapshot_date(path),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    count = 0
    with _company_stream(path) as stream:
        for raw in csv.DictReader(stream):
            sic_codes = [
                value
                for index in range(1, 5)
                if (value := _clean(raw.get(f"SICCode.SicText_{index}"))) is not None
            ]
            previous_names = [
                value
                for index in range(1, 11)
                if (value := _clean(raw.get(f"PreviousName_{index}.CompanyName"))) is not None
            ]
            writer.add(
                CompanyRecord(
                    company_number=(raw.get(" CompanyNumber") or raw.get("CompanyNumber") or "").strip(),
                    company_name=(raw.get("CompanyName") or "").strip(),
                    company_status=_clean(raw.get("CompanyStatus")),
                    company_category=_clean(raw.get("CompanyCategory")),
                    country_of_origin=_clean(raw.get("CountryOfOrigin")),
                    incorporation_date=_clean(raw.get("IncorporationDate")),
                    dissolution_date=_clean(raw.get("DissolutionDate")),
                    address_line1=_clean(raw.get("RegAddress.AddressLine1")),
                    locality=_clean(raw.get("RegAddress.PostTown")),
                    region=_clean(raw.get("RegAddress.County")),
                    postal_code=_clean(raw.get("RegAddress.PostCode")),
                    sic_codes=sic_codes,
                    previous_names=previous_names,
                    **provenance,
                ).model_dump()
            )
            count += 1
    writer.close()
    return count


def parse_psc(cfg: AppConfig, paths: list[Path]) -> int:
    writer = BatchedParquetWriter(
        cfg.companies_house.processed_dir / "companies_house_psc.parquet",
        PSC_SCHEMA,
        cfg.companies_house.batch_size,
    )
    ingested_at = datetime.now(timezone.utc).isoformat()
    count = 0
    for path in paths:
        for source_file, line in _psc_lines(path):
            if not line.strip():
                continue
            raw = json.loads(line)
            data = raw.get("data", raw)
            company_number = str(raw.get("company_number") or data.get("company_number") or "").strip()
            identification = data.get("identification") or {}
            link = (data.get("links") or {}).get("self")
            name = _clean(data.get("name")) or _clean(identification.get("legal_name")) or "Unknown"
            key = link or json.dumps(
                [company_number, data.get("kind"), name, data.get("notified_on")],
                separators=(",", ":"),
            )
            writer.add(
                PscRecord(
                    psc_id=hashlib.sha256(key.encode()).hexdigest()[:24],
                    company_number=company_number,
                    psc_type=str(data.get("kind") or "unknown"),
                    name=name,
                    country_of_residence=_clean(data.get("country_of_residence")),
                    nationality=_clean(data.get("nationality")),
                    registration_number=_clean(identification.get("registration_number")),
                    legal_authority=_clean(identification.get("legal_authority")),
                    legal_form=_clean(identification.get("legal_form")),
                    natures_of_control=[str(value) for value in data.get("natures_of_control", [])],
                    notified_on=_clean(data.get("notified_on")),
                    ceased_on=_clean(data.get("ceased_on")),
                    source_file=source_file,
                    snapshot_date=_snapshot_date(path),
                    ingested_at=ingested_at,
                ).model_dump()
            )
            count += 1
    writer.close()
    return count


def run_all(cfg: AppConfig) -> dict[str, int]:
    company_files = sorted(
        {*cfg.companies_house.raw_dir.glob("*BasicCompanyData*.csv*"),
         *cfg.companies_house.raw_dir.glob("*BasicCompanyData*.zip")}
    )
    if not company_files:
        raise FileNotFoundError(f"no BasicCompanyData CSV found under {cfg.companies_house.raw_dir}")
    psc_files = sorted(
        {*cfg.companies_house.raw_dir.glob("*psc*.txt*"),
         *cfg.companies_house.raw_dir.glob("*psc*.zip")}
    )
    return {
        "companies": parse_companies(cfg, company_files[-1]),
        "psc": parse_psc(cfg, psc_files),
    }
