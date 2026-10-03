from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
from pypdf import PdfReader

from er.config import AppConfig
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import SecAdvBrochure, SecAdvDocument, SecAdvPage
from .schema import BROCHURE_SCHEMA, DOCUMENT_SCHEMA, PAGE_SCHEMA


def _iso_date(value: str) -> str:
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            pass
    return value


def parse_mapping(cfg: AppConfig, path: Path) -> int:
    writer = BatchedParquetWriter(
        cfg.sec_adv.processed_dir / "sec_adv_brochures.parquet",
        BROCHURE_SCHEMA,
        cfg.sec_adv.batch_size,
    )
    ingested_at = datetime.now(timezone.utc).isoformat()
    count = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for raw in csv.DictReader(stream):
            date_filed = _iso_date((raw.get("DateFiled") or "").strip())
            row = SecAdvBrochure(
                firm_name=(raw.get("FirmName") or "").strip(),
                sec_number=(raw.get("SECNumber") or "").strip(),
                crd_number=(raw.get("CRDNumber") or "").strip(),
                filing_id=(raw.get("FilingID") or "").strip(),
                brochure_name=(raw.get("BrochureName") or "").strip(),
                brochure_id=(raw.get("BrochureID") or "").strip(),
                brochure_version=(raw.get("BrochureVersion") or "").strip(),
                date_filed=date_filed,
                pdf_file_name=(raw.get("PDFFileName") or "").strip(),
                source_file=path.name,
                snapshot_date=date_filed,
                ingested_at=ingested_at,
            )
            writer.add(row.model_dump())
            count += 1
    writer.close()
    return count


def parse_documents(cfg: AppConfig, zip_paths: list[Path]) -> dict[str, int]:
    brochures_path = cfg.sec_adv.processed_dir / "sec_adv_brochures.parquet"
    con = duckdb.connect()
    rows = con.sql(
        f"SELECT pdf_file_name, crd_number, brochure_id, date_filed FROM read_parquet('{brochures_path}')"
    ).fetchall()
    con.close()
    brochures = {row[0]: row[1:] for row in rows}

    document_writer = BatchedParquetWriter(
        cfg.sec_adv.processed_dir / "sec_adv_documents.parquet",
        DOCUMENT_SCHEMA,
        cfg.sec_adv.batch_size,
    )
    page_writer = BatchedParquetWriter(
        cfg.sec_adv.processed_dir / "sec_adv_pages.parquet",
        PAGE_SCHEMA,
        cfg.sec_adv.batch_size,
    )
    ingested_at = datetime.now(timezone.utc).isoformat()
    documents = pages = 0

    for zip_path in zip_paths:
        with zipfile.ZipFile(zip_path) as archive:
            for member in archive.namelist():
                pdf_file_name = Path(member).name
                metadata = brochures.get(pdf_file_name)
                if metadata is None or not member.lower().endswith(".pdf"):
                    continue
                crd_number, brochure_id, date_filed = metadata
                content = archive.read(member)
                content_hash = hashlib.sha256(content).hexdigest()
                source_file = f"{zip_path.name}:{member}"
                error = None
                page_count = 0
                try:
                    reader = PdfReader(io.BytesIO(content))
                    page_count = len(reader.pages)
                    for page_number, page in enumerate(reader.pages, start=1):
                        page_writer.add(
                            SecAdvPage(
                                crd_number=crd_number,
                                brochure_id=brochure_id,
                                pdf_file_name=pdf_file_name,
                                page_number=page_number,
                                text=page.extract_text() or "",
                                content_hash=content_hash,
                                source_file=source_file,
                                snapshot_date=date_filed,
                                ingested_at=ingested_at,
                            ).model_dump()
                        )
                        pages += 1
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                document_writer.add(
                    SecAdvDocument(
                        crd_number=crd_number,
                        brochure_id=brochure_id,
                        pdf_file_name=pdf_file_name,
                        content_hash=content_hash,
                        page_count=page_count,
                        extraction_error=error,
                        source_file=source_file,
                        snapshot_date=date_filed,
                        ingested_at=ingested_at,
                    ).model_dump()
                )
                documents += 1
    page_writer.close()
    document_writer.close()
    return {"documents": documents, "pages": pages}


def run_all(cfg: AppConfig) -> dict[str, int]:
    mappings = sorted(cfg.sec_adv.raw_dir.glob("*mapping*.csv"))
    if not mappings:
        raise FileNotFoundError(f"no *mapping*.csv found under {cfg.sec_adv.raw_dir}")
    brochures = parse_mapping(cfg, mappings[-1])
    counts = parse_documents(cfg, sorted(cfg.sec_adv.raw_dir.glob("*.zip")))
    return {"brochures": brochures, **counts}
