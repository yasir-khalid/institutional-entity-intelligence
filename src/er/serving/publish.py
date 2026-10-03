"""Publishes the processed Parquet tables into the OpenSearch indexes the API
reads at runtime (er.serving.store). Documents are shaped per read - one rich
document per entity rather than a copy of every table - so a page view is a
handful of lookups, never a join.

Each index is built under a dated name and swapped in behind its alias only
once fully loaded, so a failed or partial publish never serves half a dataset.
The reviews index is never touched here: it is written by the API.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator
from datetime import datetime, timezone

import duckdb
from opensearchpy import OpenSearch, helpers

from er.config import AppConfig
from er.indexing.opensearch_index import get_client

from .store import ADV_DOCUMENTS, ADV_PAGES, ENTITIES, FILERS, HOLDINGS, OWNERSHIP, RELATIONSHIPS


logger = logging.getLogger(__name__)

IDENTIFIERS_PER_TYPE = 200
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
    FILERS: {"cik": _KEYWORD, "lei": _KEYWORD, "top_reported_holdings": _STORED_ONLY},
    HOLDINGS: {
        "cik": _KEYWORD,
        "cusip": _KEYWORD,
        "accession_number": _KEYWORD,
        "put_call": _KEYWORD,
        "period_date": {"type": "date"},
        "value_usd": {"type": "long"},
    },
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
                   row_number() OVER (w ORDER BY {percent} DESC NULLS LAST, t.valid_from DESC NULLS LAST,
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


def relationship_documents(cfg: AppConfig) -> Iterator[tuple[str, dict]]:
    path = cfg.gleif.processed_dir / "gleif_relationships.parquet"
    if not path.exists():
        return
    for row in _rows(f"""
        SELECT start_node_id, end_node_id, relationship_type, relationship_status, start_date, end_date
        FROM read_parquet('{path}')
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


BUILDERS: dict[str, Callable[[AppConfig], Iterator[tuple[str, dict]]]] = {
    ENTITIES: entity_documents,
    FILERS: filer_documents,
    HOLDINGS: holding_documents,
    RELATIONSHIPS: relationship_documents,
    OWNERSHIP: ownership_documents,
    ADV_DOCUMENTS: adv_document_documents,
    ADV_PAGES: adv_page_documents,
}


def _has_column(path, column: str) -> bool:
    con = duckdb.connect()
    names = {row[0] for row in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()}
    con.close()
    return column in names


def _publish_index(client: OpenSearch, cfg: AppConfig, name: str) -> int:
    alias = f"{cfg.serving.prefix}_{name}"
    index = f"{alias}_{datetime.now(timezone.utc):%Y%m%d%H%M%S}"
    client.indices.create(
        index=index,
        body={
            "settings": {"number_of_shards": 1, "number_of_replicas": 0, "refresh_interval": "-1"},
            "mappings": {"dynamic": False, "properties": MAPPINGS[name]},
        },
    )
    actions = (
        {"_index": index, "_id": doc_id, "_source": doc} for doc_id, doc in BUILDERS[name](cfg)
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

    client.indices.put_settings(index=index, body={"index": {"refresh_interval": "1s"}})
    client.indices.refresh(index=index)
    previous = list(client.indices.get_alias(name=alias)) if client.indices.exists_alias(name=alias) else []
    client.indices.update_aliases(
        body={
            "actions": [{"remove": {"index": old, "alias": alias}} for old in previous]
            + [{"add": {"index": index, "alias": alias}}]
        }
    )
    for old in previous:
        client.indices.delete(index=old)
    logger.info("%s -> %s (%d documents)", alias, index, count)
    return count


def run_all(cfg: AppConfig, only: list[str] | None = None) -> dict[str, int]:
    client = get_client(cfg)
    return {name: _publish_index(client, cfg, name) for name in BUILDERS if not only or name in only}
