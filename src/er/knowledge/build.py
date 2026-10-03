from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from er.config import AppConfig

from .models import EdgeType, NodeType


logger = logging.getLogger(__name__)

# 13D/G reporting persons of type IN are individuals. They share the owner-cik:
# node Forms 3/4/5 use for people rather than becoming legal entities.
_OWNER_NODE = "CASE WHEN reporting_person_type = 'IN' THEN 'owner-cik:' ELSE 'cik:' END || reporting_person_cik"


def _columns(path: Path) -> set[str]:
    con = duckdb.connect()
    names = {row[0] for row in con.sql(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()}
    con.close()
    return names


def _reviews(cfg: AppConfig, *, latest: bool = False) -> str | None:
    """Human match reviews as a SQL relation, or None when there are none.
    With latest=True only each (node_id, lei) pair's most recent outcome is
    kept - that is what decides the graph edge; every review stays a fact."""
    path = cfg.entity.review_file
    if not path.exists():
        return None
    rows = f"""SELECT *, row_number() OVER () + 1 AS line_no
               FROM read_csv('{path}', header=true, all_varchar=true)"""
    if not latest:
        return f"({rows})"
    return f"""(SELECT * EXCLUDE (row_no) FROM (
                   SELECT *, row_number() OVER (
                       PARTITION BY node_id, lei ORDER BY reviewed_at DESC, line_no DESC) row_no
                   FROM ({rows})) WHERE row_no = 1)"""


def _node_queries(cfg: AppConfig) -> list[str]:
    queries: list[str] = []
    gleif = cfg.gleif.processed_dir / "gleif_entities.parquet"
    if gleif.exists():
        queries.append(f"""
            SELECT 'lei:' || lei AS node_id, '{NodeType.LEGAL_ENTITY}' AS node_type,
                   legal_name AS display_name, entity_status AS status,
                   'gleif' AS source, lei AS source_record_ref,
                   source_file, snapshot_date, ingested_at
            FROM read_parquet('{gleif}')
        """)

    submissions = cfg.sec_submissions.processed_dir / "sec_submissions.parquet"
    if submissions.exists():
        queries.append(f"""
            SELECT 'cik:' || cik AS node_id, '{NodeType.LEGAL_ENTITY}' AS node_type,
                   name AS display_name, NULL AS status,
                   'sec_submissions' AS source, cik AS source_record_ref,
                   source_file, snapshot_date, ingested_at
            FROM read_parquet('{submissions}')
        """)

    series = cfg.sec_series_class.processed_dir / "sec_series_classes.parquet"
    if series.exists():
        queries.extend(
            [
                f"""
                    SELECT 'cik:' || cik AS node_id, '{NodeType.LEGAL_ENTITY}' AS node_type,
                           any_value(entity_name) AS display_name, NULL AS status,
                           'sec_series_class' AS source, cik AS source_record_ref,
                           any_value(source_file) AS source_file,
                           max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
                    FROM read_parquet('{series}') GROUP BY cik
                """,
                f"""
                    SELECT 'series:' || series_id AS node_id, '{NodeType.FUND_SERIES}' AS node_type,
                           any_value(series_name) AS display_name, NULL AS status,
                           'sec_series_class' AS source, series_id AS source_record_ref,
                           any_value(source_file) AS source_file,
                           max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
                    FROM read_parquet('{series}') GROUP BY series_id
                """,
                f"""
                    SELECT 'class:' || class_id AS node_id, '{NodeType.SHARE_CLASS}' AS node_type,
                           any_value(class_name) AS display_name, NULL AS status,
                           'sec_series_class' AS source, class_id AS source_record_ref,
                           any_value(source_file) AS source_file,
                           max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
                    FROM read_parquet('{series}')
                    WHERE class_id IS NOT NULL GROUP BY class_id
                """,
            ]
        )

    nport_funds = cfg.nport.processed_dir / "nport_funds.parquet"
    if nport_funds.exists():
        queries.append(f"""
            SELECT 'series:' || series_id AS node_id, '{NodeType.FUND_SERIES}' AS node_type,
                   any_value(series_name) AS display_name, NULL AS status,
                   'nport' AS source, series_id AS source_record_ref,
                   any_value(source_file) AS source_file,
                   max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
            FROM read_parquet('{nport_funds}') WHERE series_id IS NOT NULL GROUP BY series_id
        """)

    nport_holdings = cfg.nport.processed_dir / "nport_holdings.parquet"
    if nport_holdings.exists():
        queries.append(f"""
            SELECT 'security:cusip:' || issuer_cusip AS node_id, '{NodeType.SECURITY}' AS node_type,
                   any_value(coalesce(issuer_title, issuer_name)) AS display_name, NULL AS status,
                   'nport' AS source, issuer_cusip AS source_record_ref,
                   any_value(source_file) AS source_file,
                   max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
            FROM read_parquet('{nport_holdings}')
            WHERE issuer_cusip IS NOT NULL GROUP BY issuer_cusip
        """)

    openfigi = cfg.openfigi.processed_dir / "openfigi_mappings.parquet"
    if openfigi.exists():
        queries.append(f"""
            SELECT 'figi:' || figi AS node_id, '{NodeType.SECURITY}' AS node_type,
                   any_value(name) AS display_name, NULL AS status,
                   'openfigi' AS source, figi AS source_record_ref,
                   any_value(source_file) AS source_file,
                   max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
            FROM read_parquet('{openfigi}') WHERE figi IS NOT NULL GROUP BY figi
        """)

    filings = cfg.sec_13f.processed_dir / "sec_13f_filings.parquet"
    effective_holdings = cfg.sec_13f.processed_dir / "sec_13f_effective_holdings.parquet"
    if filings.exists():
        queries.append(f"""
            SELECT 'cik:' || cik AS node_id, '{NodeType.LEGAL_ENTITY}' AS node_type,
                   arg_max(filer_name, filing_date) AS display_name, NULL AS status,
                   'sec_13f' AS source, cik AS source_record_ref,
                   any_value(source_file) AS source_file,
                   max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
            FROM read_parquet('{filings}') GROUP BY cik
        """)
    if effective_holdings.exists():
        queries.append(f"""
            SELECT 'security:cusip:' || cusip AS node_id, '{NodeType.SECURITY}' AS node_type,
                   any_value(name_of_issuer) AS display_name, NULL AS status,
                   'sec_13f' AS source, cusip AS source_record_ref,
                   any_value(source_file) AS source_file,
                   max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
            FROM read_parquet('{effective_holdings}')
            WHERE cusip IS NOT NULL GROUP BY cusip
        """)

    insiders = cfg.sec_insiders.processed_dir / "sec_insider_relationships.parquet"
    if insiders.exists():
        queries.extend(
            [
                f"""
                    SELECT 'owner-cik:' || owner_cik AS node_id, '{NodeType.REPORTING_OWNER}' AS node_type,
                           any_value(owner_name) AS display_name, NULL AS status,
                           'sec_insiders' AS source, owner_cik AS source_record_ref,
                           any_value(source_file) AS source_file,
                           max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
                    FROM read_parquet('{insiders}') GROUP BY owner_cik
                """,
                f"""
                    SELECT 'cik:' || issuer_cik AS node_id, '{NodeType.LEGAL_ENTITY}' AS node_type,
                           any_value(issuer_name) AS display_name, NULL AS status,
                           'sec_insiders' AS source, issuer_cik AS source_record_ref,
                           any_value(source_file) AS source_file,
                           max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
                    FROM read_parquet('{insiders}') GROUP BY issuer_cik
                """,
            ]
        )

    companies = cfg.companies_house.processed_dir / "companies_house_companies.parquet"
    if companies.exists():
        queries.append(f"""
            SELECT 'uk-company:' || company_number AS node_id, '{NodeType.LEGAL_ENTITY}' AS node_type,
                   company_name AS display_name, company_status AS status,
                   'companies_house' AS source, company_number AS source_record_ref,
                   source_file, snapshot_date, ingested_at FROM read_parquet('{companies}')
        """)
    psc = cfg.companies_house.processed_dir / "companies_house_psc.parquet"
    if psc.exists():
        queries.append(f"""
            SELECT 'ch-psc:' || psc_id AS node_id, '{NodeType.REPORTING_OWNER}' AS node_type,
                   name AS display_name, CASE WHEN ceased_on IS NULL THEN 'ACTIVE' ELSE 'CEASED' END status,
                   'companies_house_psc' AS source, psc_id AS source_record_ref,
                   source_file, snapshot_date, ingested_at FROM read_parquet('{psc}')
        """)

    ownership = cfg.sec_13dg.processed_dir / "sec_13dg_ownership.parquet"
    if ownership.exists():
        queries.extend(
            [
                f"""
                    SELECT {_OWNER_NODE} AS node_id,
                           CASE WHEN any_value(reporting_person_type) = 'IN' THEN '{NodeType.REPORTING_OWNER}'
                                ELSE '{NodeType.LEGAL_ENTITY}' END AS node_type,
                           arg_max(reporting_person_name, filing_date) AS display_name, NULL AS status,
                           'sec_13dg' AS source, any_value(reporting_person_cik) AS source_record_ref,
                           arg_max(source_file, filing_date) AS source_file,
                           max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
                    FROM read_parquet('{ownership}') WHERE reporting_person_cik IS NOT NULL GROUP BY 1
                """,
                f"""
                    SELECT 'cik:' || issuer_cik AS node_id, '{NodeType.LEGAL_ENTITY}' AS node_type,
                           arg_max(issuer_name, filing_date) AS display_name, NULL AS status,
                           'sec_13dg' AS source, issuer_cik AS source_record_ref,
                           arg_max(source_file, filing_date) AS source_file,
                           max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
                    FROM read_parquet('{ownership}') GROUP BY issuer_cik
                """,
                f"""
                    SELECT 'security:cusip:' || issuer_cusip AS node_id, '{NodeType.SECURITY}' AS node_type,
                           arg_max(issuer_name, filing_date) AS display_name, NULL AS status,
                           'sec_13dg' AS source, issuer_cusip AS source_record_ref,
                           arg_max(source_file, filing_date) AS source_file,
                           max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
                    FROM read_parquet('{ownership}') WHERE length(issuer_cusip) = 9 GROUP BY issuer_cusip
                """,
            ]
        )

    nic = cfg.ffiec_nic.processed_dir / "ffiec_nic_institutions.parquet"
    if nic.exists():
        queries.append(f"""
            SELECT 'rssd:' || rssd_id AS node_id, '{NodeType.LEGAL_ENTITY}' AS node_type,
                   legal_name AS display_name,
                   CASE WHEN closed_on IS NULL THEN 'ACTIVE' ELSE 'CLOSED' END AS status,
                   'ffiec_nic' AS source, rssd_id AS source_record_ref,
                   source_file, snapshot_date, ingested_at FROM read_parquet('{nic}')
        """)
    return queries


def _edge_queries(cfg: AppConfig) -> list[str]:
    queries: list[str] = []
    relationships = cfg.gleif.processed_dir / "gleif_relationships.parquet"
    if relationships.exists():
        queries.append(f"""
            SELECT 'lei:' || start_node_id AS start_node_id,
                   'lei:' || end_node_id AS end_node_id,
                   CASE relationship_type
                       WHEN 'IS_DIRECTLY_CONSOLIDATED_BY' THEN '{EdgeType.ACCOUNTING_PARENT}'
                       WHEN 'IS_ULTIMATELY_CONSOLIDATED_BY' THEN '{EdgeType.ACCOUNTING_ULTIMATE_PARENT}'
                       WHEN 'IS_FUND-MANAGED_BY' THEN '{EdgeType.FUND_MANAGED_BY}'
                       WHEN 'IS_SUBFUND_OF' THEN '{EdgeType.SUBFUND_OF}'
                       WHEN 'IS_INTERNATIONAL_BRANCH_OF' THEN '{EdgeType.BRANCH_OF}'
                       ELSE '{EdgeType.GLEIF_RELATIONSHIP}'
                   END AS edge_type,
                   start_date AS valid_from, end_date AS valid_to,
                   'gleif' AS source,
                   start_node_id || ':' || end_node_id || ':' || relationship_type AS source_record_ref,
                   source_file, snapshot_date, ingested_at
            FROM read_parquet('{relationships}')
            WHERE relationship_status = 'ACTIVE'
        """)
    series = cfg.sec_series_class.processed_dir / "sec_series_classes.parquet"
    if series.exists():
        queries.extend(
            [
                f"""
                    SELECT DISTINCT 'series:' || series_id AS start_node_id,
                           'cik:' || cik AS end_node_id,
                           '{EdgeType.SERIES_OF_REGISTRANT}' AS edge_type,
                           NULL AS valid_from, NULL AS valid_to,
                           'sec_series_class' AS source,
                           series_id || ':' || cik AS source_record_ref,
                           source_file, snapshot_date, ingested_at
                    FROM read_parquet('{series}')
                """,
                f"""
                    SELECT DISTINCT 'class:' || class_id AS start_node_id,
                           'series:' || series_id AS end_node_id,
                           '{EdgeType.CLASS_OF_SERIES}' AS edge_type,
                           NULL AS valid_from, NULL AS valid_to,
                           'sec_series_class' AS source,
                           class_id || ':' || series_id AS source_record_ref,
                           source_file, snapshot_date, ingested_at
                    FROM read_parquet('{series}') WHERE class_id IS NOT NULL
                """,
            ]
        )

    crosswalk = cfg.sec_13f.processed_dir / "crosswalk_sec_13f_gleif.parquet"
    reviews = _reviews(cfg, latest=True)
    if crosswalk.exists():
        rejected = ""
        if reviews:
            rejected = f"""AND NOT EXISTS (
                SELECT 1 FROM {reviews} r
                WHERE r.node_id = 'cik:' || x.cik AND r.lei = x.lei AND upper(r.outcome) = 'REJECTED')"""
        queries.append(f"""
            SELECT DISTINCT 'cik:' || cik AS start_node_id, 'lei:' || lei AS end_node_id,
                   '{EdgeType.SAME_AS}' AS edge_type, NULL AS valid_from, NULL AS valid_to,
                   'sec_13f_crosswalk' AS source, cik || ':' || lei AS source_record_ref,
                   source_file, snapshot_date, ingested_at
            FROM read_parquet('{crosswalk}') x
            WHERE lei IS NOT NULL AND decision = 'AUTO_MATCH' {rejected}
        """)
    if reviews:
        queries.append(f"""
            SELECT node_id AS start_node_id, 'lei:' || lei AS end_node_id,
                   '{EdgeType.SAME_AS}' AS edge_type, NULL AS valid_from, NULL AS valid_to,
                   'human_review' AS source, reviewer || ':' || reviewed_at AS source_record_ref,
                   '{cfg.entity.review_file.name}' AS source_file, reviewed_at AS snapshot_date,
                   NULL AS ingested_at
            FROM {reviews} WHERE upper(outcome) = 'CONFIRMED'
        """)

    nport_funds = cfg.nport.processed_dir / "nport_funds.parquet"
    if nport_funds.exists():
        queries.extend(
            [
                f"""
                    SELECT DISTINCT 'cik:' || cik AS start_node_id,
                           'lei:' || registrant_lei AS end_node_id,
                           '{EdgeType.SAME_AS}' AS edge_type, NULL AS valid_from, NULL AS valid_to,
                           'nport' AS source, accession_number AS source_record_ref,
                           source_file, report_date AS snapshot_date, ingested_at
                    FROM read_parquet('{nport_funds}')
                    WHERE cik IS NOT NULL AND registrant_lei IS NOT NULL
                """,
                f"""
                    SELECT DISTINCT 'series:' || series_id AS start_node_id,
                           'lei:' || series_lei AS end_node_id,
                           '{EdgeType.SAME_AS}' AS edge_type, NULL AS valid_from, NULL AS valid_to,
                           'nport' AS source, accession_number AS source_record_ref,
                           source_file, report_date AS snapshot_date, ingested_at
                    FROM read_parquet('{nport_funds}')
                    WHERE series_id IS NOT NULL AND series_lei IS NOT NULL
                """,
            ]
        )

    nport_holdings = cfg.nport.processed_dir / "nport_holdings.parquet"
    if nport_holdings.exists():
        queries.extend(
            [
                f"""
                    SELECT DISTINCT 'security:cusip:' || issuer_cusip AS start_node_id,
                           'lei:' || issuer_lei AS end_node_id,
                           '{EdgeType.ISSUED_BY}' AS edge_type, NULL AS valid_from, NULL AS valid_to,
                           'nport' AS source, holding_id AS source_record_ref,
                           source_file, snapshot_date, ingested_at
                    FROM read_parquet('{nport_holdings}')
                    WHERE issuer_cusip IS NOT NULL AND issuer_lei IS NOT NULL
                """,
                f"""
                    SELECT DISTINCT 'series:' || f.series_id AS start_node_id,
                           'security:cusip:' || h.issuer_cusip AS end_node_id,
                           '{EdgeType.REPORTED_HOLDING}' AS edge_type, NULL AS valid_from, NULL AS valid_to,
                           'nport' AS source, h.holding_id AS source_record_ref,
                           h.source_file, f.report_date AS snapshot_date, h.ingested_at
                    FROM read_parquet('{nport_holdings}') h
                    JOIN read_parquet('{nport_funds}') f USING (accession_number)
                    WHERE f.series_id IS NOT NULL AND h.issuer_cusip IS NOT NULL
                """,
            ]
        )

    openfigi = cfg.openfigi.processed_dir / "openfigi_mappings.parquet"
    if openfigi.exists():
        queries.append(f"""
            SELECT 'security:cusip:' || cusip AS start_node_id,
                   'figi:' || min(figi) AS end_node_id,
                   '{EdgeType.SAME_AS}' AS edge_type, NULL AS valid_from, NULL AS valid_to,
                   'openfigi' AS source, cusip AS source_record_ref,
                   any_value(source_file) AS source_file,
                   max(snapshot_date) AS snapshot_date, max(ingested_at) AS ingested_at
            FROM read_parquet('{openfigi}') WHERE figi IS NOT NULL
            GROUP BY cusip HAVING count(DISTINCT figi) = 1
        """)

    insiders = cfg.sec_insiders.processed_dir / "sec_insider_relationships.parquet"
    if insiders.exists():
        queries.append(f"""
            SELECT DISTINCT 'owner-cik:' || owner_cik AS start_node_id,
                   'cik:' || issuer_cik AS end_node_id,
                   '{EdgeType.INSIDER_OF}' AS edge_type, NULL AS valid_from, NULL AS valid_to,
                   'sec_insiders' AS source, accession_number AS source_record_ref,
                   source_file, filing_date AS snapshot_date, ingested_at
            FROM read_parquet('{insiders}')
        """)

    effective_holdings = cfg.sec_13f.processed_dir / "sec_13f_effective_holdings.parquet"
    if effective_holdings.exists():
        queries.append(f"""
            SELECT DISTINCT 'cik:' || cik AS start_node_id,
                   'security:cusip:' || cusip AS end_node_id,
                   '{EdgeType.REPORTED_HOLDING}' AS edge_type,
                   period_of_report AS valid_from, period_of_report AS valid_to,
                   'sec_13f' AS source, accession_number || ':' || infotable_sk AS source_record_ref,
                   source_file, snapshot_date, ingested_at
            FROM read_parquet('{effective_holdings}')
            WHERE cusip IS NOT NULL AND put_call IS NULL
        """)

    companies = cfg.companies_house.processed_dir / "companies_house_companies.parquet"
    gleif = cfg.gleif.processed_dir / "gleif_entities.parquet"
    if companies.exists() and gleif.exists():
        queries.append(f"""
            SELECT DISTINCT 'uk-company:' || c.company_number AS start_node_id,
                   'lei:' || g.lei AS end_node_id, '{EdgeType.SAME_AS}' AS edge_type,
                   NULL AS valid_from, NULL AS valid_to, 'gleif_registration_id' AS source,
                   c.company_number || ':' || g.lei AS source_record_ref,
                   g.source_file, g.snapshot_date, g.ingested_at
            FROM read_parquet('{companies}') c
            JOIN read_parquet('{gleif}') g
              ON upper(trim(g.registration_id)) = upper(trim(c.company_number))
            WHERE g.jurisdiction LIKE 'GB%'
        """)
    psc = cfg.companies_house.processed_dir / "companies_house_psc.parquet"
    if psc.exists():
        queries.append(f"""
            SELECT 'ch-psc:' || psc_id AS start_node_id,
                   'uk-company:' || company_number AS end_node_id,
                   '{EdgeType.SIGNIFICANT_CONTROL}' AS edge_type,
                   notified_on AS valid_from, ceased_on AS valid_to,
                   'companies_house_psc' AS source, psc_id AS source_record_ref,
                   source_file, snapshot_date, ingested_at FROM read_parquet('{psc}')
        """)

    if gleif.exists() and "successor_lei" in _columns(gleif):
        queries.append(f"""
            SELECT 'lei:' || lei AS start_node_id, 'lei:' || successor_lei AS end_node_id,
                   '{EdgeType.SUCCEEDED_BY}' AS edge_type, NULL AS valid_from, NULL AS valid_to,
                   'gleif' AS source, lei || ':' || successor_lei AS source_record_ref,
                   source_file, snapshot_date, ingested_at
            FROM read_parquet('{gleif}') WHERE successor_lei IS NOT NULL
        """)

    ownership = cfg.sec_13dg.processed_dir / "sec_13dg_ownership.parquet"
    if ownership.exists():
        queries.extend(
            [
                # The newest filing per owner/issuer pair wins the dedupe in run_all.
                # An amendment reporting under 5% closes the edge rather than deleting it.
                f"""
                    SELECT {_OWNER_NODE} AS start_node_id, 'cik:' || issuer_cik AS end_node_id,
                           '{EdgeType.BENEFICIAL_OWNER}' AS edge_type, event_date AS valid_from,
                           CASE WHEN percent_of_class < 5 THEN event_date END AS valid_to,
                           'sec_13dg' AS source,
                           accession_number || ':' || cast(person_index AS VARCHAR) AS source_record_ref,
                           source_file, snapshot_date, ingested_at
                    FROM read_parquet('{ownership}') WHERE reporting_person_cik IS NOT NULL
                """,
                f"""
                    SELECT DISTINCT 'security:cusip:' || issuer_cusip AS start_node_id,
                           'cik:' || issuer_cik AS end_node_id,
                           '{EdgeType.ISSUED_BY}' AS edge_type, NULL AS valid_from, NULL AS valid_to,
                           'sec_13dg' AS source, accession_number AS source_record_ref,
                           source_file, snapshot_date, ingested_at
                    FROM read_parquet('{ownership}') WHERE length(issuer_cusip) = 9
                """,
            ]
        )

    nic = cfg.ffiec_nic.processed_dir / "ffiec_nic_institutions.parquet"
    if nic.exists():
        queries.append(f"""
            SELECT 'rssd:' || rssd_id AS start_node_id, 'lei:' || lei AS end_node_id,
                   '{EdgeType.SAME_AS}' AS edge_type, NULL AS valid_from, NULL AS valid_to,
                   'ffiec_nic' AS source, rssd_id || ':' || lei AS source_record_ref,
                   source_file, snapshot_date, ingested_at
            FROM read_parquet('{nic}') WHERE lei IS NOT NULL
        """)
    nic_relationships = cfg.ffiec_nic.processed_dir / "ffiec_nic_relationships.parquet"
    if nic_relationships.exists():
        queries.append(f"""
            SELECT 'rssd:' || offspring_rssd_id AS start_node_id, 'rssd:' || parent_rssd_id AS end_node_id,
                   '{EdgeType.BANK_CONTROL_PARENT}' AS edge_type,
                   start_date AS valid_from, end_date AS valid_to,
                   'ffiec_nic' AS source, parent_rssd_id || ':' || offspring_rssd_id AS source_record_ref,
                   source_file, snapshot_date, ingested_at
            FROM read_parquet('{nic_relationships}') WHERE controlled AND end_date IS NULL
        """)
    nic_transformations = cfg.ffiec_nic.processed_dir / "ffiec_nic_transformations.parquet"
    if nic_transformations.exists():
        queries.append(f"""
            SELECT 'rssd:' || predecessor_rssd_id AS start_node_id, 'rssd:' || successor_rssd_id AS end_node_id,
                   '{EdgeType.SUCCEEDED_BY}' AS edge_type,
                   transformation_date AS valid_from, NULL AS valid_to,
                   'ffiec_nic' AS source, predecessor_rssd_id || ':' || successor_rssd_id AS source_record_ref,
                   source_file, snapshot_date, ingested_at
            FROM read_parquet('{nic_transformations}')
        """)
    return queries


def _identifier_queries(cfg: AppConfig) -> list[str]:
    queries: list[str] = []
    gleif = cfg.gleif.processed_dir / "gleif_entities.parquet"
    if gleif.exists():
        queries.append(f"""
            SELECT 'lei:' || lei AS node_id, 'LEI' AS identifier_type, lei AS identifier_value,
                   'SOURCE' AS confidence, 'gleif' AS source, lei AS source_record_ref,
                   source_file, snapshot_date, ingested_at FROM read_parquet('{gleif}')
        """)
    mappings = cfg.gleif.processed_dir / "gleif_external_identifiers.parquet"
    if mappings.exists():
        queries.append(f"""
            SELECT 'lei:' || lei AS node_id, identifier_type, identifier_value,
                   'SOURCE' AS confidence, 'gleif_mapping' AS source,
                   lei || ':' || identifier_value AS source_record_ref,
                   source_file, snapshot_date, ingested_at FROM read_parquet('{mappings}')
        """)
    series = cfg.sec_series_class.processed_dir / "sec_series_classes.parquet"
    if series.exists():
        queries.extend(
            [
                f"""
                    SELECT DISTINCT 'series:' || series_id AS node_id, 'SEC_SERIES_ID' AS identifier_type,
                           series_id AS identifier_value, 'SOURCE' AS confidence,
                           'sec_series_class' AS source, series_id AS source_record_ref,
                           source_file, snapshot_date, ingested_at FROM read_parquet('{series}')
                """,
                f"""
                    SELECT DISTINCT 'class:' || class_id AS node_id, 'TICKER' AS identifier_type,
                           class_ticker AS identifier_value, 'SOURCE' AS confidence,
                           'sec_series_class' AS source, class_id AS source_record_ref,
                           source_file, snapshot_date, ingested_at FROM read_parquet('{series}')
                    WHERE class_id IS NOT NULL AND class_ticker IS NOT NULL
                """,
            ]
        )
    companies = cfg.companies_house.processed_dir / "companies_house_companies.parquet"
    if companies.exists():
        queries.append(f"""
            SELECT 'uk-company:' || company_number AS node_id,
                   'COMPANIES_HOUSE_NUMBER' AS identifier_type,
                   company_number AS identifier_value, 'SOURCE' AS confidence,
                   'companies_house' AS source, company_number AS source_record_ref,
                   source_file, snapshot_date, ingested_at FROM read_parquet('{companies}')
        """)
    nic = cfg.ffiec_nic.processed_dir / "ffiec_nic_institutions.parquet"
    if nic.exists():
        queries.append(f"""
            SELECT 'rssd:' || rssd_id AS node_id, 'RSSD_ID' AS identifier_type,
                   rssd_id AS identifier_value, 'SOURCE' AS confidence,
                   'ffiec_nic' AS source, rssd_id AS source_record_ref,
                   source_file, snapshot_date, ingested_at FROM read_parquet('{nic}')
        """)
    return queries


def _match_decision_facts(cfg: AppConfig) -> list[str]:
    """The crosswalk's decisions as facts, so "this 13F filer is that LEI" can
    cite the score, the gap to the runner-up, each feature's contribution and
    the config that produced them - not just the bare link."""
    crosswalk = cfg.sec_13f.processed_dir / "crosswalk_sec_13f_gleif.parquet"
    if not crosswalk.exists():
        return []
    columns = _columns(crosswalk)
    values = [
        "('match.decision', decision, NULL, 'decision')",
        "('match.score', cast(score AS VARCHAR), 'points', 'score')",
        "('match.runner_up_gap', cast(gap AS VARCHAR), 'points', 'gap')",
    ]
    if "config_hash" in columns:
        values += [
            "('match.runner_up_lei', runner_up_lei, NULL, 'runner_up_lei')",
            "('match.config_hash', config_hash, NULL, 'config_hash')",
        ]
    queries = [
        f"""
        SELECT sha256('crosswalk:' || cik || ':' || fact.predicate) AS fact_id,
               'cik:' || cik AS subject_node_id, 'lei:' || lei AS object_node_id,
               fact.predicate, fact.value, fact.unit, snapshot_date AS as_of,
               'sec_13f_crosswalk' AS source, 'crosswalk_sec_13f_gleif.parquet' AS document_id,
               cik AS source_record_ref,
               'crosswalk_sec_13f_gleif.parquet:cik=' || cik || ':' || fact.field AS locator,
               source_file, snapshot_date, ingested_at
        FROM read_parquet('{crosswalk}')
        CROSS JOIN LATERAL (VALUES {", ".join(values)}) fact(predicate, value, unit, field)
        WHERE fact.value IS NOT NULL
        """
    ]
    if "feature_contributions" in columns:
        queries.append(f"""
            SELECT sha256('crosswalk:' || cik || ':feature:' || feature) AS fact_id,
                   'cik:' || cik AS subject_node_id, 'lei:' || lei AS object_node_id,
                   'match.feature.' || feature AS predicate,
                   json_extract_string(feature_contributions, '$."' || feature || '"') AS value,
                   'points' AS unit, snapshot_date AS as_of,
                   'sec_13f_crosswalk' AS source, 'crosswalk_sec_13f_gleif.parquet' AS document_id,
                   cik AS source_record_ref,
                   'crosswalk_sec_13f_gleif.parquet:cik=' || cik || ':feature_contributions.' || feature AS locator,
                   source_file, snapshot_date, ingested_at
            FROM (
                SELECT *, unnest(json_keys(feature_contributions)) AS feature
                FROM read_parquet('{crosswalk}') WHERE feature_contributions IS NOT NULL
            )
        """)

    reviews = _reviews(cfg)
    if reviews:
        queries.append(f"""
            SELECT sha256('review:' || cast(line_no AS VARCHAR) || ':' || fact.predicate) AS fact_id,
                   node_id AS subject_node_id, 'lei:' || lei AS object_node_id,
                   fact.predicate, fact.value, NULL AS unit, reviewed_at AS as_of,
                   'human_review' AS source, '{cfg.entity.review_file.name}' AS document_id,
                   reviewer AS source_record_ref,
                   '{cfg.entity.review_file.name}:line=' || cast(line_no AS VARCHAR) || ':' || fact.predicate AS locator,
                   '{cfg.entity.review_file.name}' AS source_file, reviewed_at AS snapshot_date,
                   NULL AS ingested_at
            FROM {reviews}
            CROSS JOIN LATERAL (
                VALUES ('review.outcome', upper(outcome)), ('review.reviewer', reviewer),
                       ('review.rationale', rationale)
            ) fact(predicate, value)
            WHERE fact.value IS NOT NULL
        """)
    return queries


def _fact_queries(cfg: AppConfig) -> list[str]:
    holdings = cfg.nport.processed_dir / "nport_holdings.parquet"
    funds = cfg.nport.processed_dir / "nport_funds.parquet"
    queries: list[str] = []
    if holdings.exists() and funds.exists():
        queries.append(f"""
        SELECT sha256('nport:' || h.holding_id || ':' || fact.predicate) AS fact_id,
               'series:' || f.series_id AS subject_node_id,
               'security:cusip:' || h.issuer_cusip AS object_node_id,
               fact.predicate, fact.value, fact.unit, f.report_date AS as_of,
               'nport' AS source, h.accession_number AS document_id,
               h.holding_id AS source_record_ref,
               'FUND_REPORTED_HOLDING.tsv:HOLDING_ID=' || h.holding_id || ':' || fact.field AS locator,
               h.source_file, h.snapshot_date, h.ingested_at
        FROM read_parquet('{holdings}') h
        JOIN read_parquet('{funds}') f USING (accession_number)
        CROSS JOIN LATERAL (
            VALUES
                ('holding.balance', cast(h.balance AS VARCHAR), h.unit, 'BALANCE'),
                ('holding.currency_value', cast(h.currency_value AS VARCHAR), h.currency_code, 'CURRENCY_VALUE'),
                ('holding.portfolio_percentage', cast(h.percentage AS VARCHAR), 'percent', 'PERCENTAGE')
        ) fact(predicate, value, unit, field)
        WHERE f.series_id IS NOT NULL AND fact.value IS NOT NULL
        """)

    transactions = cfg.sec_insiders.processed_dir / "sec_insider_transactions.parquet"
    if transactions.exists():
        queries.append(f"""
            SELECT sha256('sec-insider:' || transaction_id || ':' || owner_cik || ':' || fact.predicate) fact_id,
                   'owner-cik:' || owner_cik AS subject_node_id,
                   'cik:' || issuer_cik AS object_node_id,
                   fact.predicate, fact.value, fact.unit, transaction_date AS as_of,
                   'sec_insiders' AS source, accession_number AS document_id,
                   transaction_id AS source_record_ref,
                   'transaction:' || transaction_id || ':' || fact.field AS locator,
                   source_file, snapshot_date, ingested_at
            FROM read_parquet('{transactions}')
            CROSS JOIN LATERAL (
                VALUES
                    ('insider.transaction_shares', cast(shares AS VARCHAR), 'shares', 'TRANS_SHARES'),
                    ('insider.price_per_share', cast(price_per_share AS VARCHAR), NULL, 'TRANS_PRICEPERSHARE'),
                    ('insider.shares_following', cast(shares_following AS VARCHAR), 'shares', 'SHRS_OWND_FOLWNG_TRANS')
            ) fact(predicate, value, unit, field)
            WHERE fact.value IS NOT NULL
        """)
    effective_holdings = cfg.sec_13f.processed_dir / "sec_13f_effective_holdings.parquet"
    if effective_holdings.exists():
        queries.append(f"""
            SELECT sha256('sec-13f:' || accession_number || ':' || infotable_sk || ':value_usd') fact_id,
                   'cik:' || cik AS subject_node_id,
                   'security:cusip:' || cusip AS object_node_id,
                   'holding.reported_value' AS predicate, cast(value_usd AS VARCHAR) AS value,
                   'USD' AS unit, period_of_report AS as_of,
                   'sec_13f' AS source, accession_number AS document_id,
                   infotable_sk AS source_record_ref,
                   'INFOTABLE.tsv:INFOTABLE_SK=' || infotable_sk || ':VALUE' AS locator,
                   source_file, snapshot_date, ingested_at
            FROM read_parquet('{effective_holdings}')
            WHERE value_usd IS NOT NULL AND put_call IS NULL
        """)

    ownership = cfg.sec_13dg.processed_dir / "sec_13dg_ownership.parquet"
    if ownership.exists():
        queries.append(f"""
            SELECT sha256('sec-13dg:' || accession_number || ':' || cast(person_index AS VARCHAR) || ':' || fact.predicate)
                       AS fact_id,
                   {_OWNER_NODE} AS subject_node_id, 'cik:' || issuer_cik AS object_node_id,
                   fact.predicate, fact.value, fact.unit, event_date AS as_of,
                   'sec_13dg' AS source, accession_number AS document_id,
                   accession_number || ':' || cast(person_index AS VARCHAR) AS source_record_ref,
                   'primary_doc.xml:' || fact.path AS locator,
                   source_file, snapshot_date, ingested_at
            FROM (
                SELECT *, form_type LIKE 'SCHEDULE 13D%' AS is_13d,
                       CASE WHEN form_type LIKE 'SCHEDULE 13D%' THEN 'reportingPersonInfo'
                            ELSE 'coverPageHeaderReportingPersonDetails' END
                           || '[' || cast(person_index AS VARCHAR) || ']/' AS person_path
                FROM read_parquet('{ownership}') WHERE reporting_person_cik IS NOT NULL
            )
            CROSS JOIN LATERAL (
                VALUES
                    ('ownership.percent_of_class', cast(percent_of_class AS VARCHAR), 'percent',
                     person_path || CASE WHEN is_13d THEN 'percentOfClass' ELSE 'classPercent' END),
                    ('ownership.aggregate_shares', cast(aggregate_shares AS VARCHAR), 'shares',
                     person_path || CASE WHEN is_13d THEN 'aggregateAmountOwned'
                          ELSE 'reportingPersonBeneficiallyOwnedAggregateNumberOfShares' END),
                    ('ownership.filing_intent', filing_intent, NULL, 'headerData/submissionType')
            ) fact(predicate, value, unit, path)
            WHERE fact.value IS NOT NULL
        """)

    nic_relationships = cfg.ffiec_nic.processed_dir / "ffiec_nic_relationships.parquet"
    if nic_relationships.exists():
        queries.append(f"""
            SELECT sha256('nic:' || parent_rssd_id || ':' || offspring_rssd_id || ':equity') fact_id,
                   'rssd:' || offspring_rssd_id AS subject_node_id, 'rssd:' || parent_rssd_id AS object_node_id,
                   'bank_control.equity_percent' AS predicate, cast(equity_percent AS VARCHAR) AS value,
                   'percent' AS unit, start_date AS as_of, 'ffiec_nic' AS source,
                   source_file AS document_id, parent_rssd_id || ':' || offspring_rssd_id AS source_record_ref,
                   'ID_RSSD_PARENT=' || parent_rssd_id || ':ID_RSSD_OFFSPRING=' || offspring_rssd_id
                       || ':PCT_EQUITY' AS locator,
                   source_file, snapshot_date, ingested_at
            FROM read_parquet('{nic_relationships}')
            WHERE controlled AND end_date IS NULL AND equity_percent IS NOT NULL
        """)
    return queries + _match_decision_facts(cfg)


def _write_union(path, queries: list[str], *, dedupe: str | None = None) -> int:
    if not queries:
        if path.exists():
            path.unlink()
        return 0
    union = "\nUNION ALL BY NAME\n".join(queries)
    select = union
    if dedupe:
        select = f"""
            SELECT * EXCLUDE (row_no) FROM (
                SELECT *, row_number() OVER (PARTITION BY {dedupe} ORDER BY snapshot_date DESC NULLS LAST) row_no
                FROM ({union})
            ) WHERE row_no = 1
        """
    con = duckdb.connect()
    con.execute(f"COPY ({select}) TO '{path}' (FORMAT PARQUET)")
    (count,) = con.sql(f"SELECT count(*) FROM read_parquet('{path}')").fetchone()
    con.close()
    return count


def run_all(cfg: AppConfig) -> dict[str, int]:
    cfg.entity.processed_dir.mkdir(parents=True, exist_ok=True)
    nodes = _write_union(
        cfg.entity.processed_dir / "knowledge_nodes.parquet",
        _node_queries(cfg),
        dedupe="node_id",
    )
    edges = _write_union(
        cfg.entity.processed_dir / "knowledge_edges.parquet",
        _edge_queries(cfg),
        dedupe="start_node_id, end_node_id, edge_type, source",
    )
    identifiers = _write_union(
        cfg.entity.processed_dir / "knowledge_identifiers.parquet",
        _identifier_queries(cfg),
        dedupe="node_id, identifier_type, identifier_value, source",
    )
    facts = _write_union(
        cfg.entity.processed_dir / "knowledge_facts.parquet",
        _fact_queries(cfg),
        dedupe="fact_id",
    )
    logger.info(
        "knowledge graph: %d nodes, %d edges, %d identifiers, %d facts",
        nodes,
        edges,
        identifiers,
        facts,
    )
    return {"nodes": nodes, "edges": edges, "identifiers": identifiers, "facts": facts}
