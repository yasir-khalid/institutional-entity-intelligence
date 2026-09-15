"""Assembles one EntityProfile: canonical identity + every attached identifier +
GLEIF relationship neighborhood + SEC 13F activity summary (when available).

This is the single place these joins are written - er.cli.entity (and any
future consumer: an API, a graph UI) should call get_entity_profile() rather
than re-deriving them.
"""

from __future__ import annotations

import duckdb

from er.config import AppConfig
from er.entity.models import EntityIdentifier, EntityLineage, EntityProfile, Sec13FActivity, Sec13FHoldingSummary
from er.graph.build import build_hierarchy


def _load_identifiers(cfg: AppConfig, entity_id: str) -> list[EntityIdentifier]:
    path = cfg.entity.processed_dir / "entity_identifiers.parquet"
    if not path.exists():
        return []
    con = duckdb.connect()
    rows = con.execute(
        f"""
        SELECT identifier_type, identifier_value, confidence, source,
               source_file, snapshot_date, ingested_at
        FROM read_parquet('{path}')
        WHERE entity_id = ?
        """,
        [entity_id],
    ).fetchall()
    con.close()
    return [
        EntityIdentifier(
            identifier_type=t,
            identifier_value=v,
            confidence=c,
            source=s,
            source_file=sf,
            snapshot_date=sd,
            ingested_at=ia,
        )
        for t, v, c, s, sf, sd, ia in rows
    ]


def _load_sec_13f_activity(cfg: AppConfig, entity_id: str) -> Sec13FActivity | None:
    """None means "no SEC 13F filer identifier resolved for this entity" - not
    "this institution files nothing," which er.cli.entity must render as an
    explicit "not a 13F filer / not yet resolved," never as a silent blank."""
    identifiers_path = cfg.entity.processed_dir / "entity_identifiers.parquet"
    filings_path = cfg.sec_13f.processed_dir / "sec_13f_filings.parquet"
    holdings_path = cfg.sec_13f.processed_dir / "sec_13f_holdings.parquet"
    if not (identifiers_path.exists() and filings_path.exists() and holdings_path.exists()):
        return None

    con = duckdb.connect()
    cik_row = con.execute(
        f"""
        SELECT identifier_value FROM read_parquet('{identifiers_path}')
        WHERE entity_id = ? AND identifier_type = 'CIK'
        LIMIT 1
        """,
        [entity_id],
    ).fetchone()
    if not cik_row:
        con.close()
        return None
    cik = cik_row[0]

    latest_filing = con.execute(
        f"""
        SELECT accession_number, period_of_report, filing_date
        FROM read_parquet('{filings_path}')
        WHERE cik = ?
        ORDER BY filing_date DESC
        LIMIT 1
        """,
        [cik],
    ).fetchone()
    if not latest_filing:
        con.close()
        return Sec13FActivity(cik=cik)
    accession_number, period_of_report, filing_date = latest_filing

    top_holdings = con.execute(
        f"""
        SELECT name_of_issuer, value
        FROM read_parquet('{holdings_path}')
        WHERE accession_number = ?
        ORDER BY value DESC NULLS LAST
        LIMIT 10
        """,
        [accession_number],
    ).fetchall()
    (reported_count,) = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{holdings_path}') WHERE accession_number = ?",
        [accession_number],
    ).fetchone()
    con.close()

    return Sec13FActivity(
        cik=cik,
        latest_period_of_report=period_of_report,
        latest_filing_date=filing_date,
        reported_security_count=reported_count,
        top_reported_holdings=[
            Sec13FHoldingSummary(name_of_issuer=name, value=value) for name, value in top_holdings
        ],
    )


def get_entity_profile(cfg: AppConfig, entity_id: str) -> EntityProfile | None:
    path = cfg.entity.processed_dir / "entities.parquet"
    con = duckdb.connect()
    row = con.execute(
        f"""
        SELECT entity_id, canonical_name, entity_type, jurisdiction, legal_country, entity_status,
               entity_creation_date, initial_registration_date, last_update_date,
               next_renewal_date, registration_status, gleif_snapshot_date
        FROM read_parquet('{path}') WHERE entity_id = ?
        """,
        [entity_id],
    ).fetchone()
    con.close()
    if not row:
        return None

    lineage = EntityLineage(
        entity_creation_date=row[6],
        initial_registration_date=row[7],
        last_update_date=row[8],
        next_renewal_date=row[9],
        registration_status=row[10],
        gleif_snapshot_date=row[11],
    )

    return EntityProfile(
        entity_id=row[0],
        canonical_name=row[1],
        entity_type=row[2],
        jurisdiction=row[3],
        legal_country=row[4],
        entity_status=row[5],
        lineage=lineage,
        identifiers=_load_identifiers(cfg, entity_id),
        hierarchy=build_hierarchy(cfg, entity_id),
        sec_13f=_load_sec_13f_activity(cfg, entity_id),
    )
