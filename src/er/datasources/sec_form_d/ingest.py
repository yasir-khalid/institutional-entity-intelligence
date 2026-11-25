"""SEC Form D quarterly data sets -> offerings, related persons and sales-compensation recipients.

Each quarter's zip holds six TSVs keyed by ACCESSIONNUMBER. A filing can name
co-issuers; the offering row describes the primary issuer and counts the rest.
"Indefinite" offering amounts are kept as a flag, never as zero, and an
amendment (D/A) is its own row - it restates the running amount sold.
"""

from __future__ import annotations

import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from er.config import AppConfig
from er.datasources.common.download import download_if_missing
from er.datasources.common.parquet_writer import BatchedParquetWriter

from .models import FormDOffering, FormDPerson, FormDRecipient
from .schema import OFFERING_SCHEMA, PERSON_SCHEMA, RECIPIENT_SCHEMA


TABLES = ("FORMDSUBMISSION.tsv", "ISSUERS.tsv", "OFFERING.tsv", "RELATEDPERSONS.tsv", "RECIPIENTS.tsv")


def _read(path: Path) -> str:
    return f"read_csv('{path}', delim='\\t', header=true, quote='', all_varchar=true)"


def _amount(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "", "Indefinite") else None
    except ValueError:
        return None


def _flag(value: str | None) -> bool | None:
    text = (value or "").strip().lower()
    return {"true": True, "false": False, "yes": True, "no": False}.get(text)


def _date(value: str | None) -> str | None:
    for pattern in ("%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime((value or "").strip(), pattern).date().isoformat()
        except ValueError:
            pass
    return None


def _text(value: str | None) -> str | None:
    return (value or "").strip() or None


def offering(row: dict, provenance: dict) -> FormDOffering:
    offered = row["TOTALOFFERINGAMOUNT"]
    group = _text(row["INDUSTRYGROUPTYPE"])
    count = _amount(row["TOTALNUMBERALREADYINVESTED"])
    non_accredited = _amount(row["NUMBERNONACCREDITEDINVESTORS"])
    return FormDOffering(
        accession_number=row["ACCESSIONNUMBER"],
        file_number=_text(row["FILE_NUM"]),
        filing_date=_date(row["FILING_DATE"]),
        submission_type=_text(row["SUBMISSIONTYPE"]),
        is_amendment=bool(_flag(row["ISAMENDMENT"])),
        previous_accession_number=_text(row["PREVIOUSACCESSIONNUMBER"]),
        issuer_cik=row["CIK"],
        issuer_name=_text(row["ENTITYNAME"]) or "",
        street1=_text(row["STREET1"]),
        city=_text(row["CITY"]),
        state=_text(row["STATEORCOUNTRY"]),
        state_description=_text(row["STATEORCOUNTRYDESCRIPTION"]),
        postal_code=_text(row["ZIPCODE"]),
        phone=_text(row["ISSUERPHONENUMBER"]),
        jurisdiction=_text(row["JURISDICTIONOFINC"]),
        entity_type=_text(row["ENTITYTYPE"]),
        year_of_incorporation=_text(row["YEAROFINC_VALUE_ENTERED"]),
        co_issuer_count=int(row["co_issuer_count"] or 0),
        industry_group=group,
        fund_type=_text(row["INVESTMENTFUNDTYPE"]),
        is_fund=group == "Pooled Investment Fund",
        is_40_act=_flag(row["IS40ACT"]),
        revenue_range=_text(row["REVENUERANGE"]),
        nav_range=_text(row["AGGREGATENETASSETVALUERANGE"]),
        exemptions=[item.strip() for item in (row["FEDERALEXEMPTIONS_ITEMS_LIST"] or "").split(",") if item.strip()],
        first_sale_date=_date(row["SALE_DATE"]),
        first_sale_yet_to_occur=_flag(row["YETTOOCCUR"]),
        more_than_one_year=_flag(row["MORETHANONEYEAR"]),
        minimum_investment=_amount(row["MINIMUMINVESTMENTACCEPTED"]),
        total_offering=_amount(offered),
        offering_indefinite=(offered or "").strip() == "Indefinite",
        total_sold=_amount(row["TOTALAMOUNTSOLD"]),
        total_remaining=_amount(row["TOTALREMAINING"]),
        investor_count=int(count) if count is not None else None,
        non_accredited_count=int(non_accredited) if non_accredited is not None else None,
        sales_commission=_amount(row["SALESCOMM_DOLLARAMOUNT"]),
        finders_fee=_amount(row["FINDERSFEE_DOLLARAMOUNT"]),
        **provenance,
    )


def person(row: dict, provenance: dict) -> FormDPerson:
    # Filers naming an entity as a related person put "-" in the first-name box.
    parts = (part.strip() if part else "" for part in (row["FIRSTNAME"], row["MIDDLENAME"], row["LASTNAME"]))
    name = " ".join(part for part in parts if part.strip("-. "))
    return FormDPerson(
        accession_number=row["ACCESSIONNUMBER"],
        person_index=row["RELATEDPERSON_SEQ_KEY"],
        name=name,
        city=_text(row["CITY"]),
        state=_text(row["STATEORCOUNTRY"]),
        relationships=[value.strip() for value in (row["RELATIONSHIP_1"], row["RELATIONSHIP_2"], row["RELATIONSHIP_3"])
                       if value and value.strip()],
        clarification=_text(row["RELATIONSHIPCLARIFICATION"]),
        **provenance,
    )


def recipient(row: dict, provenance: dict) -> FormDRecipient:
    def crd(value: str | None) -> str | None:
        text = _text(value)
        return text if text and text.lower() != "none" else None

    return FormDRecipient(
        accession_number=row["ACCESSIONNUMBER"],
        recipient_index=row["RECIPIENT_SEQ_KEY"],
        name=_text(row["RECIPIENTNAME"]) or "",
        crd_number=crd(row["RECIPIENTCRDNUMBER"]),
        broker_dealer_name=crd(row["ASSOCIATEDBDNAME"]),
        broker_dealer_crd=crd(row["ASSOCIATEDBDCRDNUMBER"]),
        states=[item.strip() for item in (row["STATES_OR_VALUE_LIST"] or "").split(",") if item.strip()],
        foreign_solicitation=_flag(row["FOREIGNSOLICITATION"]),
        **provenance,
    )


def _write(con, query: str, build, writer: BatchedParquetWriter, provenance: dict) -> None:
    for batch in con.sql(query).to_arrow_reader(10_000):
        for row in batch.to_pylist():
            writer.add(build(row, provenance).model_dump())


def parse_zip(path: Path, writers: dict[str, BatchedParquetWriter]) -> None:
    provenance = {
        "source_file": path.name,
        "snapshot_date": path.name.split("_")[0].upper(),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
    }
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(path) as archive:
        members = {Path(name).name: name for name in archive.namelist()}
        paths = {table: Path(archive.extract(members[table], path=tmp)) for table in TABLES}
        con = duckdb.connect()
        _write(con, f"""
            WITH issuers AS (
                SELECT *, count(*) OVER (PARTITION BY ACCESSIONNUMBER) - 1 AS co_issuer_count
                FROM {_read(paths['ISSUERS.tsv'])}
            )
            SELECT s.*, i.* EXCLUDE (ACCESSIONNUMBER), o.* EXCLUDE (ACCESSIONNUMBER)
            FROM {_read(paths['FORMDSUBMISSION.tsv'])} s
            JOIN issuers i USING (ACCESSIONNUMBER)
            JOIN {_read(paths['OFFERING.tsv'])} o USING (ACCESSIONNUMBER)
            WHERE i.IS_PRIMARYISSUER_FLAG = 'YES' AND s.TESTORLIVE = 'LIVE'
        """, offering, writers["offerings"], provenance)
        _write(con, f"SELECT * FROM {_read(paths['RELATEDPERSONS.tsv'])}", person, writers["people"], provenance)
        _write(con, f"SELECT * FROM {_read(paths['RECIPIENTS.tsv'])}", recipient, writers["recipients"], provenance)
        con.close()


def run_all(cfg: AppConfig) -> dict[str, int]:
    source = cfg.sec_form_d
    for url in source.source_urls:
        download_if_missing(url, source.raw_dir / url.rsplit("/", 1)[-1])
    out = source.processed_dir
    writers = {
        "offerings": BatchedParquetWriter(out / "sec_form_d_offerings.parquet", OFFERING_SCHEMA, source.batch_size),
        "people": BatchedParquetWriter(out / "sec_form_d_people.parquet", PERSON_SCHEMA, source.batch_size),
        "recipients": BatchedParquetWriter(out / "sec_form_d_recipients.parquet", RECIPIENT_SCHEMA, source.batch_size),
    }
    paths = sorted(source.raw_dir.glob("*_d.zip"))
    for path in paths:
        parse_zip(path, writers)
    for writer in writers.values():
        writer.close()
    return {"quarters": len(paths), **{name: writer.total_written for name, writer in writers.items()}}
