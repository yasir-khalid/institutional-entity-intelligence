"""Build-time source profiles; runtime coverage is a single serving document."""
from __future__ import annotations

from pathlib import Path

import duckdb

from er.config import AppConfig
from er.serving.store import COVERAGE, MissingIndexError, Store

# Each source's files remain owned by its datasource package. This registry
# describes product coverage, rather than parsing or merging raw records.
SOURCE_TABLES = (
    ("gleif", "GLEIF LEI", ("gleif_entities", "gleif_relationships"), "Legal identity and accounting relationships"),
    ("sec_13f", "SEC 13F", ("sec_13f_filings", "sec_13f_effective_holdings", "sec_13f_quarantine"),
     "Latest reported long US-equity holdings; excludes shorts, derivatives, non-US securities, private investments and sub-threshold positions"),
    ("sec_13dg", "SEC 13D/G", ("sec_13dg_ownership",), "Reported beneficial ownership; distinct from investment discretion"),
    ("sec_insiders", "SEC Forms 3/4/5", ("sec_insider_relationships", "sec_insider_transactions"), "Officers, directors and reported insider transactions"),
    ("sec_series_class", "SEC series & class", ("sec_series_classes",), "Fund series and share classes; distinct from legal entities"),
    ("sec_submissions", "EDGAR submissions", ("sec_submissions",), "Filer identity and filing metadata"),
    ("nport", "SEC N-PORT", ("nport_funds", "nport_holdings"), "Dated fund portfolios, publicly reported with a lag"),
    ("openfigi", "OpenFIGI", ("openfigi_mappings",), "Security identifiers; an identifier of a security is not its issuer's identifier"),
    ("sec_adv", "SEC Form ADV", ("sec_adv_brochures", "sec_adv_documents", "sec_adv_pages"), "Investment adviser registrations and brochures"),
    ("companies_house", "Companies House", ("companies_house_companies", "companies_house_psc"), "UK company register and persons with significant control"),
    ("ffiec_nic", "FFIEC NIC", ("ffiec_nic_institutions", "ffiec_nic_relationships"), "Bank regulatory control; distinct from accounting consolidation"),
    ("sec_xbrl", "SEC XBRL", ("sec_xbrl_facts", "sec_xbrl_issuers"),
     "As-reported financial statement values; a 10-K/A restates rather than corrects"),
)


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def profile_table(path: Path) -> dict:
    with duckdb.connect() as con:
        relation = con.read_parquet(str(path))
        schema = [{"name": name, "type": str(kind)} for name, kind in zip(relation.columns, relation.types)]
        date_column = next((name for name in ("snapshot_date", "filing_date", "report_date")
                            if name in relation.columns), None)
        date_sql = (f"max(coalesce(try_cast({_quote(date_column)} AS DATE), "
                    f"try_strptime(cast({_quote(date_column)} AS VARCHAR), '%d-%b-%Y')::DATE))"
                    if date_column else "NULL")
        count, latest = relation.aggregate(f"count(*), {date_sql}").fetchone()
        return {"name": path.stem, "record_count": count,
                "as_of": latest.isoformat() if latest else None, "schema": schema}


def build_coverage(cfg: AppConfig) -> dict:
    sources = []
    for key, label, tables, caveat in SOURCE_TABLES:
        directory = getattr(cfg, key).processed_dir
        profiles = [profile_table(directory / f"{name}.parquet")
                    for name in tables if (directory / f"{name}.parquet").exists()]
        sources.append({"source": key, "label": label, "available": bool(profiles), "tables": profiles,
                        "as_of": max((p["as_of"] for p in profiles if p["as_of"]), default=None),
                        "quarantined": next((p["record_count"] for p in profiles
                                             if p["name"] == "sec_13f_quarantine"), 0), "caveat": caveat})
    decisions = {"AUTO_MATCH": 0, "REVIEW": 0, "UNMATCHED": 0}
    path = cfg.sec_13f.processed_dir / "crosswalk_sec_13f_gleif.parquet"
    if path.exists():
        with duckdb.connect() as con:
            decisions.update(dict(con.read_parquet(str(path)).aggregate("decision, count(*)", "decision").fetchall()))
    return {"sources": sources, "decisions": decisions}


def load_coverage(store: Store) -> dict:
    try:
        doc = store.get(COVERAGE, "current")
    except MissingIndexError:
        doc = None
    return doc or {"generation": None, "published_at": None, "sources": [], "decisions": {}, "indexes": {},
                   "previous_generation": None, "partial": False,
                   "warning": "Coverage has not been published. Run make publish to create a measured source inventory."}
