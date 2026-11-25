"""SEC's monthly Form ADV Part 1A extracts -> one row per adviser per snapshot.

Each monthly zip holds one CSV (Latin-1, one column per Part 1A item), small
enough to read whole. Keeping every snapshot, rather than the latest, is what
gives an adviser an AUM history.
The snapshot date is the newest "Latest ADV Filing Date" in the file: SEC's own
file names mix MMDDYY, MMDDYYYY and MMYYYY, so they can't be trusted to parse.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from er.config import AppConfig
from er.datasources.common.download import download_if_missing
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import AdvClientType, AdvFirm
from .schema import CLIENT_TYPE_SCHEMA, FIRM_SCHEMA


FIRM_COLUMNS = {
    "crd_number": "Organization CRD#",
    "firm_type": "Firm Type",
    "sec_number": "SEC#",
    "cik": "CIK#",
    "lei": "1P",
    "business_name": "Primary Business Name",
    "legal_name": "Legal Name",
    "street1": "Main Office Street Address 1",
    "street2": "Main Office Street Address 2",
    "city": "Main Office City",
    "state": "Main Office State",
    "country": "Main Office Country",
    "postal_code": "Main Office Postal Code",
    "phone": "Main Office Telephone Number",
    "website": "Website Address",
    "sec_status": "SEC Current Status",
    "latest_filing_date": "Latest ADV Filing Date",
    "legal_form": "3A",
    "employees": "5A",
    "advisory_employees": "5B(1)",
    "raum_discretionary": "5F(2)(a)",
    "raum_non_discretionary": "5F(2)(b)",
    "raum": "5F(2)(c)",
    "accounts_discretionary": "5F(2)(d)",
    "accounts_non_discretionary": "5F(2)(e)",
    "accounts": "5F(2)(f)",
    "raum_non_us": "5F(3)",
    "private_fund_count": "Count of Private Funds - 7B(1)",
    "private_fund_gross_assets": "Total Gross Assets of Private Funds",
    "hedge_fund_count": "Total number of Hedge funds",
    "liquidity_fund_count": "Total number of Liquidity funds",
    "pe_fund_count": "Total number of PE funds",
    "real_estate_fund_count": "Total number of Real Estate funds",
    "securitized_fund_count": "Total number of Securitized funds",
    "vc_fund_count": "Total number of VC funds",
    "other_fund_count": "Total number of Other funds",
}
NUMERIC = {name for name, field in AdvFirm.model_fields.items() if field.annotation in (int | None, float | None)}

# Item 5.D: (1) number of clients, (2) "fewer than 5" checkbox, (3) RAUM.
CLIENT_TYPES = {
    "a": "Individuals (other than high net worth)",
    "b": "High net worth individuals",
    "c": "Banking or thrift institutions",
    "d": "Investment companies",
    "e": "Business development companies",
    "f": "Pooled investment vehicles",
    "g": "Pension and profit sharing plans",
    "h": "Charitable organizations",
    "i": "State or municipal government entities",
    "j": "Other investment advisers",
    "k": "Insurance companies",
    "l": "Sovereign wealth funds and foreign official institutions",
    "m": "Corporations or other businesses",
    "n": "Other",
}


def _number(value: str | None) -> float | None:
    text = (value or "").replace(",", "").strip()
    try:
        return float(text) if text else None
    except ValueError:
        return None


def _date(value: str | None) -> str | None:
    try:
        return datetime.strptime((value or "").strip(), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def _rows(archive: zipfile.ZipFile) -> list[dict]:
    member = next(name for name in archive.namelist() if name.lower().endswith(".csv"))
    with archive.open(member) as raw:
        return list(csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1", newline="")))


def _firm(raw: dict, snapshot_date: str, provenance: dict) -> AdvFirm:
    fields = {name: raw.get(column) for name, column in FIRM_COLUMNS.items()}
    for name in NUMERIC:
        number = _number(fields[name])
        fields[name] = int(number) if number is not None and AdvFirm.model_fields[name].annotation == int | None else number
    fields["latest_filing_date"] = _date(fields["latest_filing_date"])
    for name in ("business_name", "legal_name", "city", "website", "sec_status", "firm_type"):
        fields[name] = (fields[name] or "").strip() or None
    fields["business_name"] = fields["business_name"] or fields["legal_name"] or ""
    return AdvFirm(**fields, snapshot_date=snapshot_date, **provenance)


def _client_types(raw: dict, crd: str, snapshot_date: str, provenance: dict) -> list[AdvClientType]:
    out = []
    for letter, label in CLIENT_TYPES.items():
        count = _number(raw.get(f"5D({letter})(1)"))
        fewer = bool((raw.get(f"5D({letter})(2)") or "").strip())
        raum = _number(raw.get(f"5D({letter})(3)"))
        if not (count or fewer or raum):
            continue
        out.append(AdvClientType(crd_number=crd, snapshot_date=snapshot_date, client_type=label,
                                 client_count=int(count) if count is not None else None,
                                 fewer_than_five=fewer, raum=raum, **provenance))
    return out


def parse_zip(path: Path, firms: BatchedParquetWriter, clients: BatchedParquetWriter, seen: set) -> int:
    provenance = {"source_file": path.name, "ingested_at": datetime.now(timezone.utc).isoformat()}
    with zipfile.ZipFile(path) as archive:
        rows = _rows(archive)
    dates = [d for d in (_date(row.get("Latest ADV Filing Date")) for row in rows) if d]
    snapshot_date = max(dates) if dates else path.stem
    count = 0
    for raw in rows:
        crd = (raw.get("Organization CRD#") or "").strip()
        if not crd or (crd, snapshot_date) in seen:
            continue
        seen.add((crd, snapshot_date))
        firms.add(_firm(raw, snapshot_date, provenance).model_dump())
        for client in _client_types(raw, crd, snapshot_date, provenance):
            clients.add(client.model_dump())
        count += 1
    return count


def run_all(cfg: AppConfig) -> dict[str, int]:
    source = cfg.sec_adv_firms
    for url in source.source_urls:
        download_if_missing(url, source.raw_dir / url.rsplit("/", 1)[-1])
    firms = BatchedParquetWriter(source.processed_dir / "sec_adv_firms.parquet", FIRM_SCHEMA, source.batch_size)
    clients = BatchedParquetWriter(
        source.processed_dir / "sec_adv_client_types.parquet", CLIENT_TYPE_SCHEMA, source.batch_size
    )
    seen: set[tuple[str, str]] = set()
    # Registered files first: a firm that moved from exempt reporting to
    # registration within a snapshot keeps its registered row.
    paths = sorted(source.raw_dir.glob("*.zip"), key=lambda p: ("exempt" in p.name, p.name))
    rows = sum(parse_zip(path, firms, clients, seen) for path in paths)
    firms.close()
    clients.close()
    return {"files": len(paths), "firm_snapshots": rows, "client_type_rows": clients.total_written}
