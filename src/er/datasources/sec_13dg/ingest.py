from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx
from lxml import etree

from er.config import AppConfig
from er.datasources.common.download import SEC_USER_AGENT, download_if_missing
from er.datasources.common.parquet_writer import BatchedParquetWriter
from er.datasources.common.xml_utils import element_text

from .models import BeneficialOwnership
from .schema import OWNERSHIP_SCHEMA


logger = logging.getLogger(__name__)

# Structured XML has been mandatory since 18 Dec 2024 and EDGAR files it under
# these form types. Older "SC 13D"/"SC 13G" filings are HTML/ASCII and are not read.
FORM_TYPES = ("SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A")

_INDEX_LINE = re.compile(
    r"^(?P<form>SCHEDULE 13[DG](?:/A)?)\s+.*?\s+(?P<cik>\d+)\s+"
    r"(?P<date>\d{4}-\d{2}-\d{2})\s+(?P<path>edgar/data/\S+)\s*$"
)


def _index_url(quarter: str) -> str:
    year, number = quarter.upper().split("Q")
    return f"https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{number}/form.idx"


def list_filings(index_path: Path) -> list[dict[str, str]]:
    """One entry per accession. form.idx repeats a filing under every CIK it
    touches (issuer and each filer), but the primary document is the same."""
    filings: dict[str, dict[str, str]] = {}
    with index_path.open(encoding="latin-1") as stream:
        for line in stream:
            match = _INDEX_LINE.match(line)
            if not match or match.group("form") not in FORM_TYPES:
                continue
            path = match.group("path")
            accession = Path(path).stem
            folder = f"{Path(path).parent}/{accession.replace('-', '')}"
            filings.setdefault(
                accession,
                {
                    "accession_number": accession,
                    "form_type": match.group("form"),
                    "filing_date": match.group("date"),
                    "document_url": f"https://www.sec.gov/Archives/{folder}/primary_doc.xml",
                },
            )
    return list(filings.values())


def _local(element: etree._Element) -> str:
    return etree.QName(element).localname


def _find(node: etree._Element, name: str) -> etree._Element | None:
    return next((element for element in node.iter(etree.Element) if _local(element) == name), None)


def _text(node: etree._Element, *names: str) -> str | None:
    for name in names:
        value = element_text(_find(node, name))
        if value:
            return value
    return None


def _number(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%m/%d/%Y").date().isoformat()
    except ValueError:
        return value


def _cik(value: str | None) -> str | None:
    return value.zfill(10) if value and value.strip("0") else None


def _cusip(value: str | None) -> str | None:
    # Filers with no CUSIP for the class enter zeros rather than leaving it blank.
    if not value or not value.strip("0"):
        return None
    return value.strip().upper()


def parse_document(content: bytes, filing: dict[str, str], provenance: dict) -> list[BeneficialOwnership]:
    root = etree.fromstring(content)
    is_13d = filing["form_type"].startswith("SCHEDULE 13D")
    person_tag = "reportingPersonInfo" if is_13d else "coverPageHeaderReportingPersonDetails"
    people = [element for element in root.iter(etree.Element) if _local(element) == person_tag]

    issuer_cik = _cik(_text(root, "issuerCIK", "issuerCik"))
    if issuer_cik is None:
        raise ValueError(f"{filing['accession_number']} has no issuer CIK")
    filer_cik = _cik(_text(root, "cik"))
    rules = [
        element_text(element)
        for element in root.iter(etree.Element)
        if _local(element) == "designateRulePursuantThisScheduleFiled" and element_text(element)
    ]
    shared = {
        "accession_number": filing["accession_number"],
        "form_type": filing["form_type"],
        "filing_intent": "ACTIVE" if is_13d else "PASSIVE",
        "filing_date": filing["filing_date"],
        "event_date": _iso_date(_text(root, "dateOfEvent", "eventDateRequiresFilingThisStatement")),
        "filer_cik": filer_cik,
        "issuer_cik": issuer_cik,
        "issuer_name": _text(root, "issuerName"),
        "issuer_cusip": _cusip(_text(root, "issuerCusipNumber")),
        "security_class": _text(root, "securitiesClassTitle"),
        "rule_designation": "; ".join(rules) or None,
        "document_url": filing["document_url"],
        "content_hash": hashlib.sha256(content).hexdigest(),
        **provenance,
    }

    rows = []
    for index, person in enumerate(people, start=1):
        person_cik = _cik(_text(person, "reportingPersonCIK", "reportingPersonCik"))
        # 13G cover pages carry names only; a single-person filing is filed by
        # that person, so the filer CIK identifies them. Groups stay name-only.
        if person_cik is None and len(people) == 1:
            person_cik = filer_cik
        rows.append(
            BeneficialOwnership(
                **shared,
                person_index=index,
                reporting_person_cik=person_cik,
                reporting_person_name=_text(person, "reportingPersonName") or "",
                reporting_person_type=_text(person, "typeOfReportingPerson"),
                citizenship_or_organization=_text(person, "citizenshipOrOrganization"),
                aggregate_shares=_number(
                    _text(person, "aggregateAmountOwned", "reportingPersonBeneficiallyOwnedAggregateNumberOfShares")
                ),
                percent_of_class=_number(_text(person, "percentOfClass", "classPercent")),
                sole_voting_power=_number(_text(person, "soleVotingPower")),
                shared_voting_power=_number(_text(person, "sharedVotingPower")),
                sole_dispositive_power=_number(_text(person, "soleDispositivePower")),
                shared_dispositive_power=_number(_text(person, "sharedDispositivePower")),
            )
        )
    return rows


class _RateLimit:
    """Spaces request starts at most `per_second` apart across threads, so
    several workers can overlap their latency without exceeding SEC's limit."""

    def __init__(self, per_second: float):
        self.interval = 1 / per_second
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_at)
            self.next_at = start + self.interval
        time.sleep(start - now)


def _fetch(client: httpx.Client, limit: _RateLimit, url: str, cache: Path) -> bytes | None:
    if cache.exists():
        return cache.read_bytes()
    for attempt in range(4):
        limit.wait()
        try:
            response = client.get(url)
        except httpx.TransportError:
            time.sleep(2 ** attempt)
            continue
        if response.status_code == 404:
            return None
        if response.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(response.content)
        return response.content
    raise RuntimeError(f"giving up on {url} after 4 attempts")


def run_all(cfg: AppConfig, quarters: list[str] | None = None, limit: int | None = None) -> dict[str, int]:
    quarters = quarters or cfg.sec_13dg.quarters
    limit = limit if limit is not None else cfg.sec_13dg.max_filings
    filings: list[dict[str, str]] = []
    for quarter in quarters:
        index_path = download_if_missing(_index_url(quarter), cfg.sec_13dg.raw_dir / f"form-{quarter.upper()}.idx")
        filings.extend(list_filings(index_path))
    filings.sort(key=lambda filing: (filing["filing_date"], filing["accession_number"]), reverse=True)
    if limit:
        filings = filings[:limit]

    writer = BatchedParquetWriter(
        cfg.sec_13dg.processed_dir / "sec_13dg_ownership.parquet",
        OWNERSHIP_SCHEMA,
        cfg.sec_13dg.batch_size,
    )
    ingested_at = datetime.now(timezone.utc).isoformat()
    limit_rate = _RateLimit(cfg.sec_13dg.requests_per_second)
    documents = rows = missing = 0
    with (
        httpx.Client(headers={"User-Agent": SEC_USER_AGENT}, timeout=60, follow_redirects=True) as client,
        ThreadPoolExecutor(max_workers=cfg.sec_13dg.workers) as pool,
    ):
        contents = pool.map(
            lambda filing: _fetch(
                client,
                limit_rate,
                filing["document_url"],
                cfg.sec_13dg.raw_dir / "xml" / f"{filing['accession_number']}.xml",
            ),
            filings,
        )
        for number, (filing, content) in enumerate(zip(filings, contents), start=1):
            if content is None:
                missing += 1
                continue
            provenance = {
                "source_file": f"{filing['accession_number']}/primary_doc.xml",
                "snapshot_date": filing["filing_date"],
                "ingested_at": ingested_at,
            }
            for row in parse_document(content, filing, provenance):
                writer.add(row.model_dump())
                rows += 1
            documents += 1
            if number % 500 == 0:
                logger.info("13D/G: %d/%d filings read", number, len(filings))
    writer.close()
    return {"filings": len(filings), "documents": documents, "missing": missing, "rows": rows}
