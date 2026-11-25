"""Publishes the processed Parquet tables into the OpenSearch indexes the API
reads at runtime (er.serving.store). Documents are shaped per read - one rich
document per entity rather than a copy of every table - so a page view is a
handful of lookups, never a join.

Every selected index is staged and counted before one atomic alias transaction.
Full publications have one generation across all serving indexes; --only is
explicitly marked partial. Previous indexes are retained for rollback unless
serving.keep_previous_generation is off. Indexes listed in serving.packed are
written into one physical index, so a small cluster needs fewer shards.
Reviews and saved research metadata are never replaced by publication.
"""

from __future__ import annotations

import base64
import json
import fcntl
import logging
import zipfile
from collections import Counter
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from itertools import groupby
from pathlib import Path
from uuid import uuid4

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
from opensearchpy import OpenSearch, helpers

from er.config import AppConfig
from er.indexing.opensearch_index import get_client
from er.serving.coverage import build_coverage

from er.knowledge.build import _openfigi_securities

from .store import (
    ADV_DOCUMENTS,
    ADV_FIRMS,
    FAILS_TO_DELIVER,
    FORM_D,
    SECURITY_OWNERSHIP,
    SHORT_VOLUME,
    ADV_PAGES,
    ADV_PDFS,
    ENTITIES,
    FILERS,
    FUND_SERIES,
    HOLDINGS,
    NPORT_FUNDS,
    OWNERSHIP,
    RELATIONSHIPS,
    SECURITIES,
    XBRL_FACTS,
    XBRL_ISSUERS,
    COVERAGE,
    DECISIONS,
)


logger = logging.getLogger(__name__)

IDENTIFIERS_PER_TYPE = 200
PACKED = "packed"
CONNECTION_TYPES = ("BANK_CONTROL_PARENT", "BENEFICIAL_OWNER", "SIGNIFICANT_CONTROL", "INSIDER_OF", "SUCCEEDED_BY")

_KEYWORD = {"type": "keyword"}
_STORED_ONLY = {"type": "object", "enabled": False}

MAPPINGS = {
    ENTITIES: {
        "entity_id": _KEYWORD,
        "canonical_name": _KEYWORD,
        "ciks": _KEYWORD,
        "identifiers": _STORED_ONLY,
        "exceptions": _STORED_ONLY,
        "match_decisions": _STORED_ONLY,
        "connections": _STORED_ONLY,
    },
    DECISIONS: {
        "node_id": _KEYWORD, "lei": _KEYWORD, "decision": _KEYWORD,
        "source_name": {"type": "text"}, "source": _KEYWORD,
        "feature_contributions": _STORED_ONLY,
    },
    COVERAGE: {"generation": _KEYWORD, "sources": _STORED_ONLY,
               "indexes": _STORED_ONLY, "decisions": _STORED_ONLY},
    FILERS: {"cik": _KEYWORD, "lei": _KEYWORD, "top_reported_holdings": _STORED_ONLY},
    HOLDINGS: {
        "cik": _KEYWORD,
        "cusip": _KEYWORD,
        "accession_number": _KEYWORD,
        "put_call": _KEYWORD,
        "period_date": {"type": "date"},
        "value_usd": {"type": "long"},
    },
    NPORT_FUNDS: {"series_lei": _KEYWORD, "cik": _KEYWORD, "top_holdings": _STORED_ONLY},
    FUND_SERIES: {
        "series_id": _KEYWORD,
        "cik": _KEYWORD,
        "series_lei": _KEYWORD,
        "registrant_lei": _KEYWORD,
        "class_ids": _KEYWORD,
        "tickers": _KEYWORD,
        "classes": _STORED_ONLY,
    },
    SECURITIES: {"cusip": _KEYWORD, "tickers": _KEYWORD, "figis": _KEYWORD, "securities": _STORED_ONLY},
    RELATIONSHIPS: {
        "start_node_id": _KEYWORD,
        "end_node_id": _KEYWORD,
        "relationship_type": _KEYWORD,
        "relationship_status": _KEYWORD,
    },
    OWNERSHIP: {
        "issuer_cik": _KEYWORD,
        "reporting_person_cik": _KEYWORD,
        "accession_number": _KEYWORD,
        "filing_date": _KEYWORD,
    },
    ADV_DOCUMENTS: {
        "crd_number": _KEYWORD,
        "brochure_id": _KEYWORD,
        "pdf_file_name": _KEYWORD,
        "content_hash": _KEYWORD,
        "page_count": {"type": "integer"},
        "source_file": _KEYWORD,
        "snapshot_date": _KEYWORD,
    },
    ADV_PAGES: {
        "crd_number": _KEYWORD,
        "brochure_id": _KEYWORD,
        "pdf_file_name": _KEYWORD,
        "page_number": {"type": "integer"},
        "text": {"type": "text"},
        "content_hash": _KEYWORD,
        "source_file": _KEYWORD,
        "snapshot_date": _KEYWORD,
    },
    ADV_PDFS: {"pdf_file_name": _KEYWORD, "content_hash": _KEYWORD, "content": {"type": "binary"}},
    XBRL_FACTS: {
        "cik": _KEYWORD,
        "tag": _KEYWORD,
        "unit": _KEYWORD,
        "entity_name": _KEYWORD,
        "observations": _STORED_ONLY,
    },
    XBRL_ISSUERS: {
        "cik": _KEYWORD,
        "entity_name": _KEYWORD,
        "tickers": _KEYWORD,
        "former_names": _KEYWORD,
    },
    ADV_FIRMS: {
        "crd_number": _KEYWORD,
        "names": {"type": "text"},
        "lei": _KEYWORD,
        "cik": _KEYWORD,
        "thirteen_f_cik": _KEYWORD,
        "state": _KEYWORD,
        "firm_type": _KEYWORD,
        "fund_types": _KEYWORD,
        "raum": {"type": "double"},
        "private_fund_gross_assets": {"type": "double"},
        "history": _STORED_ONLY,
        "client_types": _STORED_ONLY,
    },
    FORM_D: {
        "accession_number": _KEYWORD,
        "issuer_cik": _KEYWORD,
        "issuer_name": {"type": "text"},
        "people_names": {"type": "text"},
        "recipient_names": {"type": "text"},
        "filing_date": _KEYWORD,
        "industry_group": _KEYWORD,
        "fund_type": _KEYWORD,
        "is_fund": {"type": "boolean"},
        "is_amendment": {"type": "boolean"},
        "state": _KEYWORD,
        "total_sold": {"type": "double"},
        "people": _STORED_ONLY,
        "recipients": _STORED_ONLY,
    },
    SECURITY_OWNERSHIP: {
        "cusip": _KEYWORD,
        "tickers": _KEYWORD,
        "issuer_name": {"type": "text"},
        "holder_count": {"type": "integer"},
        "periods": _STORED_ONLY,
        "holders": _STORED_ONLY,
    },
    SHORT_VOLUME: {"symbol": _KEYWORD, "days": _STORED_ONLY},
    FAILS_TO_DELIVER: {"cusip": _KEYWORD, "symbol": _KEYWORD, "fails": _STORED_ONLY},
}


def _rows(sql: str, params: list | None = None, batch_size: int = 20_000) -> Iterator[dict]:
    con = duckdb.connect()
    reader = con.execute(sql, params or []).to_arrow_reader(batch_size)
    for batch in reader:
        yield from batch.to_pylist()
    con.close()


def _source_url(source: str, record_ref: str | None, issuer_node: str | None) -> str | None:
    if not record_ref or not issuer_node or not issuer_node.startswith("cik:"):
        return None
    accession = record_ref.split(":")[0]
    folder = f"https://www.sec.gov/Archives/edgar/data/{int(issuer_node[4:])}/{accession.replace('-', '')}/"
    if source == "sec_13dg":
        return folder + "primary_doc.xml"
    if source == "sec_insiders":
        return folder
    return None


def build_connections(cfg: AppConfig) -> dict[str, dict]:
    """Per LEI: the records in other sources linked to it, and its typed
    relationships from the knowledge graph (capped per group, with the true
    total), from its own node and every node SAME_AS-linked to it."""
    processed = cfg.entity.processed_dir
    edges, nodes, facts = (processed / f"knowledge_{name}.parquet" for name in ("edges", "nodes", "facts"))
    if not (edges.exists() and nodes.exists()):
        return {}

    connections: dict[str, dict] = {}
    for row in _rows(f"""
        SELECT e.end_node_id AS lei_node, e.start_node_id AS node_id, n.display_name, e.source
        FROM read_parquet('{edges}') e LEFT JOIN read_parquet('{nodes}') n ON n.node_id = e.start_node_id
        WHERE e.edge_type = 'SAME_AS' AND e.end_node_id LIKE 'lei:%'
        ORDER BY e.end_node_id, e.start_node_id
    """):
        entry = connections.setdefault(row["lei_node"][4:], {"linked_records": [], "groups": []})
        entry["linked_records"].append(
            {"node_id": row["node_id"], "display_name": row["display_name"], "source": row["source"]}
        )

    percent = "NULL"
    percent_join = ""
    if facts.exists():
        percent = "p.percent"
        percent_join = f"""LEFT JOIN (
            SELECT source_record_ref, any_value(try_cast(value AS DOUBLE)) AS percent
            FROM read_parquet('{facts}')
            WHERE predicate IN ('ownership.percent_of_class', 'bank_control.equity_percent')
            GROUP BY source_record_ref
        ) p ON p.source_record_ref = t.source_record_ref"""

    groups: dict[tuple[str, str, str], dict] = {}
    for row in _rows(f"""
        WITH typed AS (SELECT * FROM read_parquet('{edges}') WHERE edge_type IN {CONNECTION_TYPES}),
        mine AS (
            SELECT end_node_id AS lei_node, start_node_id AS node_id FROM read_parquet('{edges}')
            WHERE edge_type = 'SAME_AS' AND end_node_id LIKE 'lei:%'
            UNION
            SELECT node, node FROM (
                SELECT start_node_id AS node FROM typed UNION SELECT end_node_id FROM typed
            ) WHERE node LIKE 'lei:%'
        ),
        touching AS (
            SELECT m.lei_node, 'outgoing' AS direction, t.end_node_id AS other_node_id, t.*
            FROM typed t JOIN mine m ON t.start_node_id = m.node_id
            UNION ALL
            SELECT m.lei_node, 'incoming', t.start_node_id, t.*
            FROM typed t JOIN mine m ON t.end_node_id = m.node_id
        ),
        ranked AS (
            SELECT t.lei_node, t.edge_type, t.direction, t.other_node_id, t.source, t.valid_from,
                   t.valid_to, t.source_record_ref, t.end_node_id, {percent} AS percent,
                   n.display_name AS other_name, n.node_type AS other_type,
                   count(*) OVER w AS total,
                   row_number() OVER (w ORDER BY t.valid_to IS NOT NULL, {percent} DESC NULLS LAST, t.valid_from DESC NULLS LAST,
                                      n.display_name) AS rank
            FROM touching t
            LEFT JOIN read_parquet('{nodes}') n ON n.node_id = t.other_node_id
            {percent_join}
            WINDOW w AS (PARTITION BY t.lei_node, t.edge_type, t.direction)
        )
        SELECT * FROM ranked WHERE rank <= {cfg.serving.connections_per_group}
        ORDER BY lei_node, edge_type, direction, rank
    """):
        lei = row["lei_node"][4:]
        key = (lei, row["edge_type"], row["direction"])
        if key not in groups:
            groups[key] = {
                "edge_type": row["edge_type"],
                "direction": row["direction"],
                "total": row["total"],
                "connections": [],
            }
            connections.setdefault(lei, {"linked_records": [], "groups": []})["groups"].append(groups[key])
        groups[key]["connections"].append(
            {
                "edge_type": row["edge_type"],
                "direction": row["direction"],
                "other_node_id": row["other_node_id"],
                "other_name": row["other_name"],
                "other_type": row["other_type"],
                "source": row["source"],
                "valid_from": row["valid_from"],
                "valid_to": row["valid_to"],
                "percent": row["percent"],
                "source_url": _source_url(row["source"], row["source_record_ref"], row["end_node_id"]),
            }
        )
    return connections


def build_match_decisions(cfg: AppConfig) -> dict[str, list[dict]]:
    """Per LEI: every 13F crosswalk decision that chose it, with the score,
    runner-up, feature points and config fingerprint behind it."""
    crosswalk = cfg.sec_13f.processed_dir / "crosswalk_sec_13f_gleif.parquet"
    gleif = cfg.gleif.processed_dir / "gleif_entities.parquet"
    if not crosswalk.exists():
        return {}
    # Crosswalks written before decisions were made citable lack these columns.
    detail = (
        "c.runner_up_lei, c.runner_up_score, c.feature_contributions, c.config_hash"
        if _has_column(crosswalk, "runner_up_lei")
        else "NULL AS runner_up_lei, NULL AS runner_up_score, NULL AS feature_contributions, NULL AS config_hash"
    )
    join = ""
    if gleif.exists() and "c.runner_up_lei" in detail:
        detail += ", g.legal_name AS runner_up_name"
        join = f"LEFT JOIN read_parquet('{gleif}') g ON g.lei = c.runner_up_lei"
    else:
        detail += ", NULL AS runner_up_name"
    decisions: dict[str, list[dict]] = {}
    for row in _rows(f"""
        SELECT c.cik, c.filer_name, c.lei, c.decision, c.score, c.gap, c.reason, c.snapshot_date, {detail}
        FROM read_parquet('{crosswalk}') c {join}
        WHERE c.lei IS NOT NULL ORDER BY c.lei, c.cik
    """):
        decisions.setdefault(row["lei"], []).append(
            {
                "node_id": f"cik:{row['cik']}",
                "source_name": row["filer_name"],
                "lei": row["lei"],
                "decision": row["decision"],
                "score": row["score"],
                "gap": row["gap"],
                "reason": row["reason"],
                "runner_up_lei": row["runner_up_lei"],
                "runner_up_name": row["runner_up_name"],
                "runner_up_score": row["runner_up_score"],
                "feature_contributions": json.loads(row["feature_contributions"] or "{}"),
                "config_hash": row["config_hash"],
                "decided_on": row["snapshot_date"],
            }
        )
    return decisions


def entity_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    processed = cfg.entity.processed_dir
    identifiers = processed / "entity_identifiers.parquet"
    exceptions = cfg.gleif.processed_dir / "gleif_relationship_exceptions.parquet"
    gleif = cfg.gleif.processed_dir / "gleif_entities.parquet"
    connections = build_connections(cfg)
    decisions = build_match_decisions(cfg)
    successor = "g.successor_lei" if gleif.exists() and _has_column(gleif, "successor_lei") else "NULL"

    for row in _rows(f"""
        WITH ids AS (
            SELECT entity_id, count(*) AS identifier_total,
                   list(identifier_value) FILTER (WHERE identifier_type = 'CIK') AS ciks,
                   list(struct_pack(identifier_type, identifier_value, confidence, source,
                                    source_file, snapshot_date, ingested_at)
                        ORDER BY identifier_type, identifier_value) FILTER (WHERE type_rank <= {IDENTIFIERS_PER_TYPE})
                       AS identifiers
            FROM (
                SELECT *, row_number() OVER (PARTITION BY entity_id, identifier_type
                                             ORDER BY identifier_value) AS type_rank
                FROM read_parquet('{identifiers}')
            ) GROUP BY entity_id
        ),
        exc AS (
            SELECT lei AS entity_id, list(struct_pack(exception_category, exception_reason)) AS exceptions
            FROM read_parquet('{exceptions}') GROUP BY lei
        )
        SELECT e.*, coalesce(ids.identifier_total, 0) AS identifier_total, ids.ciks, ids.identifiers,
               exc.exceptions, {successor} AS successor_lei
        FROM read_parquet('{processed / "entities.parquet"}') e
        LEFT JOIN ids USING (entity_id)
        LEFT JOIN exc USING (entity_id)
        {f"LEFT JOIN read_parquet('{gleif}') g ON g.lei = e.entity_id" if successor != "NULL" else ""}
    """):
        entity_id = row["entity_id"]
        row["ciks"] = row["ciks"] or []
        row["identifiers"] = row["identifiers"] or []
        row["exceptions"] = row["exceptions"] or []
        row["match_decisions"] = decisions.get(entity_id, [])
        row["connections"] = connections.get(entity_id, {"linked_records": [], "groups": []})
        yield entity_id, row


def filer_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    """Per 13F filer: the summary a profile shows - latest period, filing date,
    reported count, top long positions by CUSIP, quarantined filings and
    scale-suspect filings - computed once here instead of per request."""
    processed = cfg.sec_13f.processed_dir
    filings = processed / "sec_13f_filings.parquet"
    effective = processed / "sec_13f_effective_holdings.parquet"
    quarantine = processed / "sec_13f_quarantine.parquet"
    checks = processed / "sec_13f_scale_checks.parquet"
    crosswalk = processed / "crosswalk_sec_13f_gleif.parquet"
    if not (filings.exists() and effective.exists()):
        return
    quarantine_rows = (
        f"SELECT f.cik, list(q.accession_number || ': ' || array_to_string(q.errors, ', ') ORDER BY q.accession_number) AS items "
        f"FROM read_parquet('{quarantine}') q JOIN read_parquet('{filings}') f USING (accession_number) GROUP BY f.cik"
        if quarantine.exists() else "SELECT NULL::VARCHAR AS cik, NULL::VARCHAR[] AS items WHERE false"
    )
    suspect_rows = (
        f"SELECT cik, period_of_report, list(accession_number ORDER BY accession_number) AS items "
        f"FROM read_parquet('{checks}') WHERE looks_like_thousands GROUP BY ALL"
        if checks.exists() else "SELECT NULL::VARCHAR AS cik, NULL AS period_of_report, NULL::VARCHAR[] AS items WHERE false"
    )
    crosswalk_rows = (
        f"SELECT cik, lei, decision FROM read_parquet('{crosswalk}')"
        if crosswalk.exists() else "SELECT NULL::VARCHAR AS cik, NULL AS lei, NULL AS decision WHERE false"
    )
    for row in _rows(f"""
        WITH periods AS (
            SELECT h.cik, h.period_of_report, strptime(h.period_of_report, '%d-%b-%Y') AS period_date,
                   max(strptime(f.filing_date, '%d-%b-%Y')) AS filed, count(*) AS reported
            FROM read_parquet('{effective}') h JOIN read_parquet('{filings}') f USING (accession_number)
            GROUP BY ALL
        ),
        latest AS (
            SELECT * EXCLUDE (row_no) FROM (
                SELECT *, row_number() OVER (PARTITION BY cik ORDER BY period_date DESC) AS row_no FROM periods
            ) WHERE row_no = 1
        ),
        top AS (
            SELECT cik, list(struct_pack(name_of_issuer, value, cusip) ORDER BY value DESC NULLS LAST) AS holdings
            FROM (
                SELECT h.cik, h.cusip, any_value(h.name_of_issuer) AS name_of_issuer,
                       sum(h.value_usd)::BIGINT AS value,
                       row_number() OVER (PARTITION BY h.cik ORDER BY sum(h.value_usd) DESC NULLS LAST) AS rank
                FROM read_parquet('{effective}') h JOIN latest l USING (cik, period_of_report)
                WHERE h.put_call IS NULL GROUP BY h.cik, h.cusip
            ) WHERE rank <= 10 GROUP BY cik
        ),
        names AS (
            SELECT cik, arg_max(filer_name, strptime(filing_date, '%d-%b-%Y')) AS filer_name
            FROM read_parquet('{filings}') GROUP BY cik
        ),
        quarantined AS ({quarantine_rows}),
        suspect AS ({suspect_rows}),
        crosswalk AS ({crosswalk_rows})
        SELECT n.cik, n.filer_name, l.period_of_report AS latest_period_of_report,
               strftime(l.filed, '%d-%b-%Y') AS latest_filing_date,
               coalesce(l.reported, 0) AS reported_security_count, 'USD' AS value_unit,
               coalesce(t.holdings, []) AS top_reported_holdings,
               coalesce(q.items, []) AS quarantined_filings,
               coalesce(s.items, []) AS scale_suspect_filings,
               x.lei, x.decision
        FROM names n
        LEFT JOIN latest l USING (cik)
        LEFT JOIN top t USING (cik)
        LEFT JOIN quarantined q USING (cik)
        LEFT JOIN suspect s ON s.cik = n.cik AND s.period_of_report = l.period_of_report
        LEFT JOIN crosswalk x ON x.cik = n.cik
    """):
        yield row["cik"], row


def holding_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    processed = cfg.sec_13f.processed_dir
    effective = processed / "sec_13f_effective_holdings.parquet"
    checks = processed / "sec_13f_scale_checks.parquet"
    if not effective.exists():
        return
    flagged = (
        f"accession_number IN (SELECT accession_number FROM read_parquet('{checks}') WHERE looks_like_thousands)"
        if checks.exists() else "false"
    )
    for row in _rows(f"""
        SELECT accession_number, infotable_sk, cik, cusip, name_of_issuer, title_of_class, put_call,
               period_of_report, strftime(strptime(period_of_report, '%d-%b-%Y'), '%Y-%m-%d') AS period_date,
               value_usd, shares_or_principal_amount AS shares, shares_or_principal_type AS shares_type,
               source_file, snapshot_date, {flagged} AS scale_suspect
        FROM read_parquet('{effective}')
    """, batch_size=50_000):
        yield f"{row['accession_number']}:{row['infotable_sk']}", row


def nport_fund_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    """Per fund series LEI: its latest N-PORT report (an amendment replaces the
    original for the same report date) with net assets and the ten largest
    holdings by USD value. CURRENCY_VALUE in the SEC data set is the USD value:
    it equals the holding's percentage of net assets times net assets."""
    processed = cfg.nport.processed_dir
    funds = processed / "nport_funds.parquet"
    holdings = processed / "nport_holdings.parquet"
    if not (funds.exists() and holdings.exists()):
        return
    for row in _rows(f"""
        WITH latest AS (
            SELECT * EXCLUDE (row_no) FROM (
                SELECT *, row_number() OVER (
                    PARTITION BY series_lei
                    ORDER BY strptime(report_date, '%d-%b-%Y') DESC, strptime(filing_date, '%d-%b-%Y') DESC,
                             accession_number DESC) AS row_no
                FROM read_parquet('{funds}') WHERE series_lei IS NOT NULL
            ) WHERE row_no = 1
        ),
        ranked AS (
            SELECT h.accession_number, h.holding_id, h.issuer_name, h.issuer_lei, h.issuer_cusip AS cusip, h.isin,
                   h.asset_category, h.payoff_profile, h.currency_value AS value_usd, h.percentage,
                   count(*) OVER (PARTITION BY h.accession_number) AS holding_count,
                   row_number() OVER (PARTITION BY h.accession_number ORDER BY h.currency_value DESC NULLS LAST,
                                      h.holding_id) AS rank
            FROM read_parquet('{holdings}') h JOIN latest l USING (accession_number)
        ),
        top AS (
            SELECT accession_number, any_value(holding_count) AS holding_count,
                   list(struct_pack(holding_id, issuer_name, issuer_lei, cusip, isin, asset_category,
                                    payoff_profile, value_usd, percentage) ORDER BY rank)
                       FILTER (WHERE rank <= 10) AS top_holdings
            FROM ranked GROUP BY accession_number
        )
        SELECT l.series_lei, l.series_id, l.series_name, l.cik, l.registrant_name, l.registrant_lei,
               l.accession_number, l.report_date, l.filing_date, l.net_assets, l.total_assets,
               l.total_liabilities, coalesce(t.holding_count, 0) AS holding_count,
               coalesce(t.top_holdings, []) AS top_holdings, l.source_file
        FROM latest l LEFT JOIN top t USING (accession_number)
    """):
        yield row["series_lei"], row


def fund_series_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    """Per fund series: its registrant and share classes from SEC's series/class
    register, plus the series and registrant LEIs its N-PORT reports state. The
    registrant LEI is shared by all the registrant's series, including those
    with no N-PORT report of their own."""
    series = cfg.sec_series_class.processed_dir / "sec_series_classes.parquet"
    funds = cfg.nport.processed_dir / "nport_funds.parquet"
    if not series.exists():
        return
    leis = (
        f"""SELECT series_id, arg_max(series_lei, strptime(report_date, '%d-%b-%Y')) AS series_lei,
                   arg_max(registrant_lei, strptime(report_date, '%d-%b-%Y')) AS registrant_lei
            FROM read_parquet('{funds}') WHERE series_id IS NOT NULL GROUP BY series_id"""
        if funds.exists()
        else "SELECT NULL::VARCHAR AS series_id, NULL::VARCHAR AS series_lei, NULL::VARCHAR AS registrant_lei WHERE false"
    )
    for row in _rows(f"""
        WITH leis AS ({leis}),
        registrants AS (
            SELECT s.cik, any_value(l.registrant_lei) AS registrant_lei
            FROM read_parquet('{series}') s JOIN leis l USING (series_id)
            WHERE l.registrant_lei IS NOT NULL GROUP BY s.cik
        )
        SELECT s.series_id, any_value(s.series_name) AS series_name, any_value(s.cik) AS cik,
               any_value(s.entity_name) AS registrant_name, any_value(l.series_lei) AS series_lei,
               any_value(r.registrant_lei) AS registrant_lei,
               list(struct_pack(class_id := s.class_id, class_name := s.class_name, ticker := s.class_ticker)
                    ORDER BY s.class_id) AS classes,
               list(DISTINCT s.class_id) AS class_ids,
               coalesce(list(DISTINCT upper(s.class_ticker)) FILTER (WHERE s.class_ticker IS NOT NULL), []) AS tickers,
               max(s.snapshot_date) AS snapshot_date, any_value(s.source_file) AS source_file
        FROM read_parquet('{series}') s LEFT JOIN leis l USING (series_id) LEFT JOIN registrants r USING (cik)
        WHERE coalesce(s.series_id, '') <> ''
        GROUP BY s.series_id
    """):
        yield row["series_id"], row


def security_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    """Per 13F CUSIP sent to OpenFIGI: the securities it maps to, one entry per
    share class (er.knowledge.build._openfigi_securities). More than one is an
    ambiguous mapping; none is a CUSIP OpenFIGI didn't recognise."""
    path = cfg.openfigi.processed_dir / "openfigi_mappings.parquet"
    if not path.exists():
        return
    for row in _rows(f"""
        WITH listings AS ({_openfigi_securities(path)}),
        per_security AS (
            SELECT cusip, security_key, any_value(share_class_figi) AS share_class_figi,
                   coalesce(list(DISTINCT composite_figi) FILTER (WHERE composite_figi IS NOT NULL), []) AS composite_figis,
                   coalesce(any_value(name) FILTER (WHERE exchange_code = 'US'), any_value(name)) AS name,
                   coalesce(any_value(ticker) FILTER (WHERE exchange_code = 'US'), any_value(ticker)) AS ticker,
                   any_value(security_type) AS security_type, any_value(security_type_2) AS security_type_2,
                   any_value(market_sector) AS market_sector, count(*) AS listing_count
            FROM listings GROUP BY cusip, security_key
        ),
        cusips AS (
            SELECT cusip, max(snapshot_date) AS snapshot_date, any_value(source_file) AS source_file,
                   any_value(error) AS error
            FROM read_parquet('{path}') GROUP BY cusip
        )
        SELECT c.cusip, c.snapshot_date, c.source_file, c.error,
               coalesce(list(struct_pack(security_key := p.security_key, share_class_figi := p.share_class_figi,
                                         composite_figis := p.composite_figis, name := p.name, ticker := p.ticker,
                                         security_type := p.security_type, security_type_2 := p.security_type_2,
                                         market_sector := p.market_sector, listing_count := p.listing_count)
                             ORDER BY p.listing_count DESC, p.security_key)
                        FILTER (WHERE p.security_key IS NOT NULL), []) AS securities,
               coalesce(list(DISTINCT upper(p.ticker)) FILTER (WHERE p.ticker IS NOT NULL), []) AS tickers,
               coalesce(list(DISTINCT p.security_key) FILTER (WHERE p.security_key IS NOT NULL), [])
                   || coalesce(flatten(list(p.composite_figis)), []) AS figis
        FROM cusips c LEFT JOIN per_security p USING (cusip)
        GROUP BY c.cusip, c.snapshot_date, c.source_file, c.error
    """):
        count = len(row["securities"])
        row["status"] = "no_match" if count == 0 else "resolved" if count == 1 else "ambiguous"
        yield row["cusip"], row


def relationship_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    path = cfg.gleif.processed_dir / "gleif_relationships.parquet"
    if not path.exists():
        return
    # GLEIF can list one pair more than once (an ended period, then a current
    # one); the tree reads one edge per pair, so keep the active, newest one.
    for row in _rows(f"""
        SELECT start_node_id, end_node_id, relationship_type, relationship_status, start_date, end_date
        FROM read_parquet('{path}')
        QUALIFY row_number() OVER (
            PARTITION BY start_node_id, end_node_id, relationship_type
            ORDER BY relationship_status = 'ACTIVE' DESC, start_date DESC NULLS LAST) = 1
    """, batch_size=50_000):
        yield f"{row['start_node_id']}:{row['end_node_id']}:{row['relationship_type']}", row


def ownership_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    path = cfg.sec_13dg.processed_dir / "sec_13dg_ownership.parquet"
    if not path.exists():
        return
    for row in _rows(f"SELECT * EXCLUDE (ingested_at) FROM read_parquet('{path}')"):
        yield f"{row['accession_number']}:{row['person_index']}", row


def adv_document_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    path = cfg.sec_adv.processed_dir / "sec_adv_documents.parquet"
    if not path.exists():
        return
    for row in _rows(f"SELECT * EXCLUDE (ingested_at) FROM read_parquet('{path}')"):
        yield f"{row['content_hash']}:{row['source_file']}", row


def adv_page_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    path = cfg.sec_adv.processed_dir / "sec_adv_pages.parquet"
    if not path.exists():
        return
    for row in _rows(f"SELECT * EXCLUDE (ingested_at) FROM read_parquet('{path}')"):
        yield f"{row['content_hash']}:{row['page_number']}:{row['source_file']}", row


def adv_pdf_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    """The brochure PDFs themselves, read from the SEC monthly ZIPs the pages
    were extracted from, so the API can serve one without the raw files."""
    path = cfg.sec_adv.processed_dir / "sec_adv_documents.parquet"
    if not path.exists():
        return
    rows = _rows(f"""
        SELECT pdf_file_name, arg_max(content_hash, snapshot_date) AS content_hash,
               arg_max(source_file, snapshot_date) AS source_file
        FROM read_parquet('{path}') GROUP BY pdf_file_name ORDER BY source_file
    """)
    for archive_name, group in groupby(rows, key=lambda row: row["source_file"].partition(":")[0]):
        archive_path = cfg.sec_adv.raw_dir / archive_name
        if not archive_path.is_file():
            continue
        with zipfile.ZipFile(archive_path) as archive:
            members = set(archive.namelist())
            for row in group:
                member = row["source_file"].partition(":")[2]
                if member in members:
                    content = base64.b64encode(archive.read(member)).decode("ascii")
                    yield row["pdf_file_name"], {"pdf_file_name": row["pdf_file_name"],
                                                 "content_hash": row["content_hash"], "content": content}


def xbrl_fact_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    """Per (CIK, concept, unit): every dated observation of that concept, so a
    point-in-time question ("as filed, as of <date>") can be answered from the
    whole series rather than a latest-value snapshot. Restatements are kept -
    the same period_end can carry several values, each with the filing that
    reported it (filed) and its accession number."""
    path = cfg.sec_xbrl.processed_dir / "sec_xbrl_facts.parquet"
    if not path.exists():
        return
    for row in _rows(f"""
        SELECT cik, tag, unit, any_value(entity_name) AS entity_name,
               list(struct_pack(period_start, period_end, fiscal_year, fiscal_period, form,
                                filed, accession_number, frame, value)
                    ORDER BY period_end, filed, accession_number) AS observations
        FROM (
            SELECT DISTINCT cik, entity_name, tag, unit, period_start, period_end, fiscal_year,
                            fiscal_period, form, filed, accession_number, frame, value
            FROM read_parquet('{path}')
        )
        GROUP BY cik, tag, unit
    """):
        yield f"{row['cik']}:{row['tag']}:{row['unit']}", row


def xbrl_issuer_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    """Per issuer CIK: its name and, when EDGAR submissions have been ingested,
    the tickers and former names the tool resolves a name or ticker to a CIK by."""
    path = cfg.sec_xbrl.processed_dir / "sec_xbrl_issuers.parquet"
    if not path.exists():
        return
    for row in _rows(f"SELECT * EXCLUDE (ingested_at) FROM read_parquet('{path}')"):
        yield row["cik"], row


def decision_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    path = cfg.sec_13f.processed_dir / "crosswalk_sec_13f_gleif.parquet"
    if not path.exists():
        return
    for row in _rows(f"SELECT * FROM read_parquet('{path}')"):
        node_id = f"cik:{row['cik']}"
        contributions = row.get("feature_contributions") or {}
        if isinstance(contributions, str):
            contributions = json.loads(contributions)
        yield node_id, {**row, "node_id": node_id, "source_name": row.get("filer_name"),
                        "source": "sec_13f_crosswalk", "feature_contributions": contributions,
                        "decided_on": row.get("snapshot_date")}


FUND_TYPES = {
    "hedge_fund_count": "Hedge fund",
    "pe_fund_count": "Private equity",
    "vc_fund_count": "Venture capital",
    "real_estate_fund_count": "Real estate",
    "securitized_fund_count": "Securitized asset",
    "liquidity_fund_count": "Liquidity",
    "other_fund_count": "Other private fund",
}


def adv_firm_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    """Per adviser CRD: its latest Form ADV Part 1A answers, every snapshot's
    RAUM (the AUM history), the latest client-type breakdown, and the links
    the filings themselves state - its LEI (Item 1.P) and the 13F filer CIK
    whose cover page names this CRD."""
    processed = cfg.sec_adv_firms.processed_dir
    firms = processed / "sec_adv_firms.parquet"
    clients = processed / "sec_adv_client_types.parquet"
    filings = cfg.sec_13f.processed_dir / "sec_13f_filings.parquet"
    gleif = cfg.gleif.processed_dir / "gleif_entities.parquet"
    if not firms.exists():
        return
    thirteen_f = (
        f"""SELECT ltrim(crd_number, '0') AS crd_number,
                   arg_max(cik, strptime(filing_date, '%d-%b-%Y')) AS thirteen_f_cik
            FROM read_parquet('{filings}') WHERE crd_number IS NOT NULL GROUP BY 1"""
        if filings.exists() else "SELECT NULL::VARCHAR AS crd_number, NULL::VARCHAR AS thirteen_f_cik WHERE false"
    )
    entities = (
        f"SELECT lei, legal_name AS lei_name FROM read_parquet('{gleif}')"
        if gleif.exists() else "SELECT NULL::VARCHAR AS lei, NULL::VARCHAR AS lei_name WHERE false"
    )
    client_rows = (
        f"""SELECT c.crd_number, list(struct_pack(client_type := c.client_type, client_count := c.client_count,
                                                  fewer_than_five := c.fewer_than_five, raum := c.raum)
                                      ORDER BY c.raum DESC NULLS LAST, c.client_count DESC NULLS LAST) AS client_types
            FROM read_parquet('{clients}') c JOIN latest l USING (crd_number, snapshot_date) GROUP BY 1"""
        if clients.exists() else "SELECT NULL::VARCHAR AS crd_number, [] AS client_types WHERE false"
    )
    fund_types = ", ".join(f"CASE WHEN {column} > 0 THEN '{label}' END" for column, label in FUND_TYPES.items())
    for row in _rows(f"""
        WITH latest AS (
            SELECT * EXCLUDE (row_no) FROM (
                SELECT *, row_number() OVER (PARTITION BY crd_number ORDER BY snapshot_date DESC) AS row_no
                FROM read_parquet('{firms}')
            ) WHERE row_no = 1
        ),
        history AS (
            SELECT crd_number, list(struct_pack(snapshot_date, raum, raum_discretionary, accounts, employees,
                                                private_fund_count, private_fund_gross_assets, source_file)
                                    ORDER BY snapshot_date) AS history
            FROM read_parquet('{firms}') GROUP BY crd_number
        ),
        clients AS ({client_rows}),
        thirteen_f AS ({thirteen_f}),
        entities AS ({entities})
        SELECT l.* EXCLUDE (ingested_at), h.history, coalesce(c.client_types, []) AS client_types,
               t.thirteen_f_cik, e.lei_name,
               list_filter([l.business_name, l.legal_name], x -> x IS NOT NULL) AS names,
               list_filter([{fund_types}], x -> x IS NOT NULL) AS fund_types
        FROM latest l
        JOIN history h USING (crd_number)
        LEFT JOIN clients c USING (crd_number)
        LEFT JOIN thirteen_f t USING (crd_number)
        LEFT JOIN entities e USING (lei)
    """):
        yield row["crd_number"], row


def form_d_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    """Per Form D filing: the offering, its related persons and its
    sales-compensation recipients - so a feed row and its detail page are one
    read."""
    processed = cfg.sec_form_d.processed_dir
    offerings = processed / "sec_form_d_offerings.parquet"
    people = processed / "sec_form_d_people.parquet"
    recipients = processed / "sec_form_d_recipients.parquet"
    if not offerings.exists():
        return
    for row in _rows(f"""
        WITH people AS (
            SELECT accession_number, list(struct_pack(name, city, state, relationships, clarification)
                                          ORDER BY person_index) AS people
            FROM read_parquet('{people}') GROUP BY 1
        ),
        recipients AS (
            SELECT accession_number, list(struct_pack(name, crd_number, broker_dealer_name, broker_dealer_crd,
                                                      states, foreign_solicitation)
                                          ORDER BY recipient_index) AS recipients
            FROM read_parquet('{recipients}') GROUP BY 1
        )
        SELECT o.* EXCLUDE (ingested_at), coalesce(p.people, []) AS people, coalesce(r.recipients, []) AS recipients,
               array_to_string(list_transform(coalesce(p.people, []), x -> x.name), ' | ') AS people_names,
               array_to_string(list_transform(coalesce(r.recipients, []), x -> x.name), ' | ') AS recipient_names
        FROM read_parquet('{offerings}') o
        LEFT JOIN people p USING (accession_number)
        LEFT JOIN recipients r USING (accession_number)
    """):
        yield row["accession_number"], row


def security_ownership_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    """Per CUSIP: every 13F report period's holder count, total value and
    shares (long positions only), and the largest holders in the latest period
    beside what each reported for the period before. Changes are left to the
    readers' registered formulas. Only report periods at least half of all
    filers report are kept, so a late filing for an old quarter is not a period."""
    processed = cfg.sec_13f.processed_dir
    effective = processed / "sec_13f_effective_holdings.parquet"
    filings = processed / "sec_13f_filings.parquet"
    crosswalk = processed / "crosswalk_sec_13f_gleif.parquet"
    figi = cfg.openfigi.processed_dir / "openfigi_mappings.parquet"
    if not (effective.exists() and filings.exists()):
        return
    tickers = (
        f"""SELECT cusip, list(DISTINCT upper(ticker)) FILTER (WHERE ticker IS NOT NULL) AS tickers
            FROM read_parquet('{figi}') WHERE exchange_code = 'US' GROUP BY cusip"""
        if figi.exists() else "SELECT NULL::VARCHAR AS cusip, []::VARCHAR[] AS tickers WHERE false"
    )
    leis = (
        f"SELECT cik, lei FROM read_parquet('{crosswalk}') WHERE decision IN ('AUTO_MATCH', 'REVIEW')"
        if crosswalk.exists() else "SELECT NULL::VARCHAR AS cik, NULL::VARCHAR AS lei WHERE false"
    )
    for row in _rows(f"""
        WITH covered AS (
            -- The filing windows ingested also carry a few late filings for
            -- old quarters; only periods most filers report are compared.
            SELECT period_of_report FROM (
                SELECT period_of_report, count(DISTINCT cik) AS filers
                FROM read_parquet('{effective}') GROUP BY 1
            ) QUALIFY filers >= 0.5 * max(filers) OVER ()
        ),
        positions AS (
            SELECT cusip, cik, period_of_report, strptime(period_of_report, '%d-%b-%Y')::DATE AS period_date,
                   any_value(name_of_issuer) AS name_of_issuer, any_value(title_of_class) AS title_of_class,
                   sum(value_usd)::BIGINT AS value_usd, sum(shares_or_principal_amount) AS shares,
                   any_value(accession_number) AS accession_number
            FROM read_parquet('{effective}')
            WHERE put_call IS NULL AND cusip IS NOT NULL AND period_of_report IN (SELECT period_of_report FROM covered)
            GROUP BY cusip, cik, period_of_report
        ),
        ranked_periods AS (
            SELECT cusip, period_of_report, period_date,
                   dense_rank() OVER (PARTITION BY cusip ORDER BY period_date DESC) AS period_rank
            FROM (SELECT DISTINCT cusip, period_of_report, period_date FROM positions)
        ),
        periods AS (
            SELECT p.cusip, list(struct_pack(period_of_report := p.period_of_report,
                                             period_date := strftime(p.period_date, '%Y-%m-%d'),
                                             holder_count := p.holder_count, value_usd := p.value_usd,
                                             shares := p.shares) ORDER BY p.period_date) AS periods
            FROM (SELECT cusip, period_of_report, period_date, count(*) AS holder_count,
                         sum(value_usd)::BIGINT AS value_usd, sum(shares) AS shares
                  FROM positions GROUP BY ALL) p
            GROUP BY p.cusip
        ),
        latest AS (
            SELECT p.*, r.period_rank FROM positions p JOIN ranked_periods r USING (cusip, period_of_report)
            WHERE r.period_rank <= 2
        ),
        names AS (
            SELECT cik, arg_max(filer_name, strptime(filing_date, '%d-%b-%Y')) AS filer_name
            FROM read_parquet('{filings}') GROUP BY cik
        ),
        holders AS (
            SELECT cusip, list(struct_pack(cik := cik, filer_name := filer_name, lei := lei,
                                           value_usd := value_usd, shares := shares,
                                           accession_number := accession_number,
                                           previous_value_usd := previous_value_usd,
                                           previous_shares := previous_shares,
                                           previous_accession_number := previous_accession_number)
                               ORDER BY value_usd DESC NULLS LAST) AS holders
            FROM (
                SELECT c.cusip, c.cik, n.filer_name, x.lei, c.value_usd, c.shares, c.accession_number,
                       p.value_usd AS previous_value_usd, p.shares AS previous_shares,
                       p.accession_number AS previous_accession_number,
                       row_number() OVER (PARTITION BY c.cusip ORDER BY c.value_usd DESC NULLS LAST) AS holder_rank
                FROM latest c
                LEFT JOIN latest p ON p.cusip = c.cusip AND p.cik = c.cik AND p.period_rank = 2
                LEFT JOIN names n ON n.cik = c.cik
                LEFT JOIN ({leis}) x ON x.cik = c.cik
                WHERE c.period_rank = 1
            ) WHERE holder_rank <= {cfg.serving.holders_per_security}
            GROUP BY cusip
        ),
        issuers AS (
            SELECT cusip, arg_max(name_of_issuer, period_date) AS issuer_name,
                   arg_max(title_of_class, period_date) AS title_of_class
            FROM positions GROUP BY cusip
        ),
        current AS (
            SELECT cusip, period_of_report AS latest_period, count(*) AS holder_count
            FROM latest WHERE period_rank = 1 GROUP BY ALL
        ),
        previous AS (SELECT DISTINCT cusip, period_of_report AS previous_period FROM latest WHERE period_rank = 2)
        SELECT i.cusip, i.issuer_name, i.title_of_class, coalesce(t.tickers, []) AS tickers,
               c.latest_period, v.previous_period, c.holder_count, p.periods, coalesce(h.holders, []) AS holders
        FROM issuers i
        JOIN current c USING (cusip)
        JOIN periods p USING (cusip)
        LEFT JOIN previous v USING (cusip)
        LEFT JOIN holders h USING (cusip)
        LEFT JOIN ({tickers}) t USING (cusip)
    """, batch_size=2_000):
        yield row["cusip"], row


def short_volume_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    path = cfg.finra_short_volume.processed_dir / "finra_short_volume.parquet"
    if not path.exists():
        return
    for row in _rows(f"""
        SELECT symbol, list(struct_pack(trade_date, short_volume, short_exempt_volume, total_volume, source_file)
                            ORDER BY trade_date) AS days
        FROM read_parquet('{path}') GROUP BY symbol
    """):
        yield row["symbol"], row


def fails_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    path = cfg.sec_ftd.processed_dir / "sec_ftd.parquet"
    if not path.exists():
        return
    for row in _rows(f"""
        SELECT cusip, arg_max(symbol, settlement_date) AS symbol, arg_max(description, settlement_date) AS description,
               list(struct_pack(settlement_date, quantity, price, source_file) ORDER BY settlement_date) AS fails
        FROM read_parquet('{path}') GROUP BY cusip
    """):
        yield row["cusip"], row


BUILDERS: dict[str, Callable[[AppConfig], Iterator[tuple[str, dict]]]] = {
    ENTITIES: entity_documents,
    FILERS: filer_documents,
    HOLDINGS: holding_documents,
    NPORT_FUNDS: nport_fund_documents,
    FUND_SERIES: fund_series_documents,
    SECURITIES: security_documents,
    RELATIONSHIPS: relationship_documents,
    OWNERSHIP: ownership_documents,
    ADV_DOCUMENTS: adv_document_documents,
    ADV_PAGES: adv_page_documents,
    ADV_PDFS: adv_pdf_documents,
    XBRL_FACTS: xbrl_fact_documents,
    XBRL_ISSUERS: xbrl_issuer_documents,
    DECISIONS: decision_documents,
    ADV_FIRMS: adv_firm_documents,
    FORM_D: form_d_documents,
    SECURITY_OWNERSHIP: security_ownership_documents,
    SHORT_VOLUME: short_volume_documents,
    FAILS_TO_DELIVER: fails_documents,
}


def _has_column(path, column: str) -> bool:
    con = duckdb.connect()
    names = {row[0] for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()}
    con.close()
    return column in names


def _units(cfg: AppConfig, names: list[str]) -> list[str]:
    """The physical indexes behind these serving names: packed ones share one."""
    packed = set(cfg.serving.packed)
    return list(dict.fromkeys(PACKED if name in packed else name for name in names))


def _mapping(cfg: AppConfig, unit: str) -> dict:
    if unit != PACKED:
        return MAPPINGS[unit]
    merged = {"serving_kind": _KEYWORD}
    for name in cfg.serving.packed:
        for field, spec in MAPPINGS[name].items():
            if merged.setdefault(field, spec) != spec:
                raise ValueError(f"{name} maps {field!r} differently from another packed index; leave it unpacked")
    return merged


def _documents(cfg: AppConfig, unit: str, counts: Counter) -> Iterator[tuple[str, dict]]:
    names = cfg.serving.packed if unit == PACKED else [unit]
    for name in names:
        for doc_id, doc in BUILDERS[name](cfg):
            counts[name] += 1
            yield (f"{name}:{doc_id}", {**doc, "serving_kind": name}) if unit == PACKED else (doc_id, doc)


def _stage_index(client: OpenSearch, cfg: AppConfig, name: str, generation: str,
                 documents: Iterator[tuple[str, dict]], mapping: dict) -> tuple[str, int]:
    alias = f"{cfg.serving.prefix}_{name}"
    index = f"{alias}_{generation}"
    client.indices.create(
        index=index,
        body={
            "settings": {"number_of_shards": 1, "number_of_replicas": 0, "refresh_interval": "-1"},
            "mappings": {"dynamic": False, "properties": mapping, "_meta": {"generation": generation}},
        },
    )
    actions = (
        {"_index": index, "_id": doc_id, "_source": doc} for doc_id, doc in documents
    )
    count = 0
    try:
        for ok, item in helpers.parallel_bulk(
            client,
            actions,
            chunk_size=cfg.serving.bulk_batch_size,
            max_chunk_bytes=20 * 1024 * 1024,
            thread_count=3,
            raise_on_error=True,
        ):
            count += ok
            if count % 200_000 == 0:
                logger.info("%s: %d documents", index, count)
    except Exception:
        client.indices.delete(index=index, ignore_unavailable=True)
        raise

    try:
        client.indices.put_settings(index=index, body={"index": {"refresh_interval": "1s"}})
        client.indices.refresh(index=index)
        if client.count(index=index)["count"] != count:
            raise RuntimeError(f"{name}: staged document count does not reconcile; aliases were not changed")
    except Exception:
        client.indices.delete(index=index, ignore_unavailable=True)
        raise
    return index, count


def _aliases(client: OpenSearch, cfg: AppConfig, names: list[str]) -> dict[str, list[str]]:
    return {name: sorted(client.indices.get_alias(name=f"{cfg.serving.prefix}_{name}"))
            if client.indices.exists_alias(name=f"{cfg.serving.prefix}_{name}") else [] for name in names}


def _switch(client: OpenSearch, cfg: AppConfig, previous: dict[str, list[str]], indexes: dict[str, dict],
            retired: dict[str, list[str]] | None = None) -> None:
    """`retired` names aliases a packed index now replaces; they are dropped in
    the same transaction so a reader never sees both layouts."""
    if _aliases(client, cfg, list(indexes)) != previous:
        raise RuntimeError("Serving aliases changed during publication. Retry from the current generation.")
    actions = [{"remove": {"index": old, "alias": f"{cfg.serving.prefix}_{name}", "must_exist": True}}
               for name, olds in (retired or {}).items() for old in olds]
    for name, entry in indexes.items():
        alias = f"{cfg.serving.prefix}_{name}"
        actions.extend({"remove": {"index": old, "alias": alias, "must_exist": True}}
                       for old in previous[name])
        # The explicit single-write-index constraint also rejects competing
        # first publications (no old alias exists to conditionally remove).
        actions.append({"add": {"index": entry["index"], "alias": alias, "is_write_index": True}})
    # One OpenSearch alias transaction covers every index, including coverage.
    client.indices.update_aliases(body={"actions": actions})


def _inputs(cfg: AppConfig) -> dict[str, tuple[int, int]]:
    directories = {cfg.entity.processed_dir, *(getattr(cfg, source).processed_dir
                   for source in ("gleif", "sec_13f", "sec_submissions", "sec_series_class", "openfigi",
                                  "nport", "sec_insiders", "sec_adv", "companies_house", "sec_13dg",
                                  "ffiec_nic", "sec_xbrl", "sec_adv_firms", "sec_form_d",
                                  "finra_short_volume", "sec_ftd"))}
    return {str(path): (path.stat().st_size, path.stat().st_mtime_ns)
            for directory in directories for path in directory.glob("*.parquet")}


def _manifest(path: Path) -> dict:
    return json.loads(pq.read_table(path)["document"][0].as_py())


def _rollback(cfg: AppConfig, generation: str) -> dict[str, int]:
    """Restore a retained complete publication; never touch runtime metadata."""
    if not generation or any(char not in "0123456789abcdef-" for char in generation):
        raise ValueError("Invalid publication generation")
    path = cfg.entity.processed_dir / "serving_publications" / f"{generation}.parquet"
    doc = _manifest(path)
    if doc.get("partial"):
        raise ValueError("Rollback requires a complete publication generation")
    if doc.get("generation") != generation or set(doc["indexes"]) != {*_units(cfg, list(BUILDERS)), COVERAGE}:
        raise ValueError("Publication manifest does not describe a complete generation")
    if any(entry["index"] != f"{cfg.serving.prefix}_{name}_{generation}"
           for name, entry in doc["indexes"].items()):
        raise ValueError("Publication manifest belongs to a different serving prefix")
    client = get_client(cfg)
    for name, entry in doc["indexes"].items():
        if not client.indices.exists(index=entry["index"]):
            raise ValueError(f"Retained index for {name} is no longer available")
        if client.count(index=entry["index"])["count"] != entry["count"]:
            raise ValueError(f"Retained index for {name} no longer reconciles")
    _switch(client, cfg, _aliases(client, cfg, list(doc["indexes"])), doc["indexes"])
    return {name: entry["count"] for name, entry in doc["indexes"].items() if name != COVERAGE}


def rollback(cfg: AppConfig, generation: str) -> dict[str, int]:
    directory = cfg.entity.processed_dir / "serving_publications"
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return _rollback(cfg, generation)


def run_all(cfg: AppConfig, only: list[str] | None = None) -> dict[str, int]:
    names = list(BUILDERS) if not only else list(dict.fromkeys(only))
    if not names or any(name not in BUILDERS for name in names):
        raise ValueError("Select at least one known serving index")
    units = _units(cfg, names)
    directory = cfg.entity.processed_dir / "serving_publications"
    directory.mkdir(parents=True, exist_ok=True)
    # Serialize publishers using the same build directory. Conditional alias
    # removals also reject a conflicting publisher on a different machine.
    with (directory / "publish.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        client = get_client(cfg)
        generation = uuid4().hex
        previous = _aliases(client, cfg, units + [COVERAGE])
        retired = ({name: olds for name, olds in _aliases(client, cfg, cfg.serving.packed).items() if olds}
                   if PACKED in units else {})
        inputs = _inputs(cfg)
        doc = {**build_coverage(cfg), "generation": generation,
               "published_at": datetime.now(timezone.utc).isoformat(),
               "partial": set(units) != set(_units(cfg, list(BUILDERS))), "previous_generation": None, "indexes": {}}
        # Previous source profiles come from the build-time manifest, never
        # from a serving document treated as the system of record.
        if previous[COVERAGE]:
            prior_generation = previous[COVERAGE][0].removeprefix(f"{cfg.serving.prefix}_{COVERAGE}_")
            prior_path = directory / f"{prior_generation}.parquet"
            if prior_path.exists():
                prior = _manifest(prior_path)
                doc["previous_generation"] = prior_generation
                prior_sources = {source["source"]: source for source in prior["sources"]}
                for source in doc["sources"]:
                    old = prior_sources.get(source["source"], {})
                    source["schema_changed"] = bool(old.get("tables")) and (
                        [(t["name"], t["schema"]) for t in source["tables"]] !=
                        [(t["name"], t["schema"]) for t in old.get("tables", [])])
        counts: Counter = Counter()
        staged = []
        try:
            for unit in units:
                index, count = _stage_index(client, cfg, unit, generation, _documents(cfg, unit, counts),
                                            _mapping(cfg, unit))
                staged.append(index)
                doc["indexes"][unit] = {"index": index, "count": count}
            doc["documents"] = dict(counts)
            doc["indexes"][COVERAGE] = {"index": f"{cfg.serving.prefix}_{COVERAGE}_{generation}", "count": 1}
            coverage_index, _ = _stage_index(client, cfg, COVERAGE, generation, iter([("current", doc)]),
                                             MAPPINGS[COVERAGE])
            staged.append(coverage_index)
            if _inputs(cfg) != inputs:
                raise RuntimeError("Processed inputs changed during publication; aliases were not changed. Retry after the build finishes.")
            pq.write_table(pa.Table.from_pylist([{"generation": generation, "document": json.dumps(doc)}]),
                           directory / f"{generation}.parquet")
        except Exception:
            for index in staged:
                client.indices.delete(index=index, ignore_unavailable=True)
            raise
        # An ambiguous transport failure here must leave staged indexes intact:
        # the alias transaction may already have committed on the server.
        _switch(client, cfg, previous, doc["indexes"], retired)
        if cfg.serving.keep_previous_generation:
            logger.info("Published generation %s; previous indexes retained for rollback", generation)
        else:
            superseded = [old for olds in (*previous.values(), *retired.values()) for old in olds]
            for old in superseded:
                client.indices.delete(index=old, ignore_unavailable=True)
            logger.info("Published generation %s; deleted %d superseded indexes", generation, len(superseded))
        return dict(counts)
