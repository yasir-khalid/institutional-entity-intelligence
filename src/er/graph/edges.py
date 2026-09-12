"""Raw data access for the relationship graph - one LEI in, matching rows out.
No business logic here (that's build.py); just parameterized DuckDB lookups
against the processed Parquet tables.
"""

from __future__ import annotations

import duckdb

from er.config import AppConfig


def fetch_relationships(cfg: AppConfig, lei: str) -> list[dict]:
    path = cfg.gleif.processed_dir / "gleif_relationships.parquet"
    con = duckdb.connect()
    rows = con.execute(
        f"""
        SELECT start_node_id, end_node_id, relationship_type, relationship_status
        FROM read_parquet('{path}')
        WHERE start_node_id = ? OR end_node_id = ?
        """,
        [lei, lei],
    ).fetchall()
    con.close()
    return [
        {
            "start_node_id": r[0],
            "end_node_id": r[1],
            "relationship_type": r[2],
            "relationship_status": r[3],
        }
        for r in rows
    ]


def fetch_exceptions(cfg: AppConfig, lei: str) -> list[dict]:
    path = cfg.gleif.processed_dir / "gleif_relationship_exceptions.parquet"
    con = duckdb.connect()
    rows = con.execute(
        f"""
        SELECT exception_category, exception_reason
        FROM read_parquet('{path}')
        WHERE lei = ?
        """,
        [lei],
    ).fetchall()
    con.close()
    return [{"exception_category": r[0], "exception_reason": r[1]} for r in rows]


def fetch_entity_names(cfg: AppConfig, leis: list[str]) -> dict[str, str]:
    if not leis:
        return {}
    path = cfg.gleif.processed_dir / "gleif_entities.parquet"
    con = duckdb.connect()
    placeholders = ", ".join("?" for _ in leis)
    rows = con.execute(
        f"SELECT lei, legal_name FROM read_parquet('{path}') WHERE lei IN ({placeholders})",
        leis,
    ).fetchall()
    con.close()
    return {r[0]: r[1] for r in rows}


def fetch_entity_name(cfg: AppConfig, lei: str) -> str | None:
    return fetch_entity_names(cfg, [lei]).get(lei)
