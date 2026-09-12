"""Auto-generate ER benchmark data from deterministic identifier bridges.

The core idea: any GLEIF entity that also appears in the ISIN<->LEI mapping has an
independently-known correct answer (its LEI) that did not come from our own name
normalization logic - that's a trustworthy positive label. Combined with intra-GLEIF
"confusable" entity groups (same core name, different fund number / master-feeder
flag), this bootstraps a large, adversarial-aware evaluation set without manual
labeling. See the project plan for the full rationale.

DuckDB does the heavy lifting (joins, self-joins, group-bys, sampling) directly over
the Parquet files - no need to load multi-million-row tables into Python or fight
pyarrow's Acero join limitations (it refuses to join on list-typed columns, which
ruled out a naive pyarrow group_by/join approach here). Only the already-tiny final
`evaluation_pairs` sample (~a few thousand rows) touches plain Python, for the
per-row query-variant assignment.

Outputs (data/benchmark/):
    positives.parquet        - every GLEIF entity independently confirmed via ISIN
    hard_negatives.parquet   - pairs of distinct entities that look confusably similar
    evaluation_pairs.parquet - curated, right-sized sample of both, ready for a
                               future Recall@K / matcher-scoring harness to consume
"""

from __future__ import annotations

import logging
import time
import zlib
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from er.config import AppConfig, load_config
from er.normalisation.names import normalize_name

logger = logging.getLogger(__name__)

EVALUATION_PAIRS_SCHEMA = pa.schema(
    [
        ("pair_id", pa.string()),
        ("query_name", pa.string()),
        ("query_name_norm", pa.string()),
        ("query_country", pa.string()),
        ("expected_lei", pa.string()),
        ("confusable_lei", pa.string()),
        ("case_type", pa.string()),
        ("difficulty", pa.string()),
        ("source", pa.string()),
    ]
)


def _seed_fraction(seed: int) -> float:
    """Map an integer seed into DuckDB setseed()'s required [-1.0, 1.0] range."""
    return ((seed % 20_000) - 10_000) / 10_000.0


def generate_positives(cfg: AppConfig) -> Path:
    """Every entity with an independently-known-correct LEI via the ISIN bridge."""
    entities = cfg.gleif.processed_dir / "gleif_entities.parquet"
    isin_lei = cfg.gleif.processed_dir / "isin_lei.parquet"
    out_path = cfg.benchmark.output_dir / "positives.parquet"

    con = duckdb.connect()
    con.execute(f"""
        COPY (
            SELECT
                e.lei, e.legal_name, e.legal_name_norm, e.legal_name_core,
                e.jurisdiction, e.legal_country, e.entity_status,
                MIN(i.isin) AS sample_isin,
                COUNT(i.isin) AS isin_count
            FROM read_parquet('{entities}') e
            JOIN read_parquet('{isin_lei}') i ON e.lei = i.lei
            GROUP BY
                e.lei, e.legal_name, e.legal_name_norm, e.legal_name_core,
                e.jurisdiction, e.legal_country, e.entity_status
        ) TO '{out_path}' (FORMAT PARQUET)
    """)
    (row_count,) = con.sql(f"SELECT COUNT(*) FROM read_parquet('{out_path}')").fetchone()
    con.close()
    logger.info("positives: %d entities confirmed via ISIN bridge -> %s", row_count, out_path)
    return out_path


def generate_hard_negatives(cfg: AppConfig) -> Path:
    """Pairs of distinct entities that share a core name but differ in a way that
    should prevent a matcher from conflating them (fund number, master/feeder)."""
    entities = cfg.gleif.processed_dir / "gleif_entities.parquet"
    out_path = cfg.benchmark.output_dir / "hard_negatives.parquet"
    min_tokens = cfg.benchmark.min_core_tokens
    max_group = cfg.benchmark.max_confusable_group_size

    con = duckdb.connect()
    con.execute(f"""
        COPY (
            WITH candidates AS (
                SELECT lei, legal_name_core, jurisdiction, fund_number, is_master, is_feeder
                FROM read_parquet('{entities}')
                WHERE legal_name_core IS NOT NULL
                  -- token count = space count + 1 (legal_name_core is single-space-joined)
                  AND length(legal_name_core) - length(replace(legal_name_core, ' ', '')) + 1 >= {min_tokens}
            ),
            group_sizes AS (
                SELECT legal_name_core, COUNT(*) AS grp_size
                FROM candidates
                GROUP BY legal_name_core
                HAVING COUNT(*) BETWEEN 2 AND {max_group}
            )
            SELECT
                a.lei AS lei_a, b.lei AS lei_b, a.legal_name_core, a.jurisdiction,
                a.fund_number AS fund_number_a, b.fund_number AS fund_number_b,
                a.is_master AS is_master_a, a.is_feeder AS is_feeder_a,
                b.is_master AS is_master_b, b.is_feeder AS is_feeder_b,
                CASE
                    WHEN a.fund_number IS NOT NULL AND b.fund_number IS NOT NULL
                         AND a.fund_number != b.fund_number THEN 'fund_number'
                    WHEN a.is_master != b.is_master OR a.is_feeder != b.is_feeder THEN 'master_feeder'
                    ELSE 'other_same_core'
                END AS conflict_type
            FROM candidates a
            JOIN candidates b ON a.legal_name_core = b.legal_name_core AND a.lei < b.lei
            JOIN group_sizes g ON a.legal_name_core = g.legal_name_core
        ) TO '{out_path}' (FORMAT PARQUET)
    """)
    (row_count,) = con.sql(f"SELECT COUNT(*) FROM read_parquet('{out_path}')").fetchone()
    con.close()
    logger.info("hard_negatives: %d confusable pairs -> %s", row_count, out_path)
    return out_path


def _name_variant(legal_name: str, legal_name_core: str, seed_key: str) -> tuple[str, str]:
    """Deterministically assign one of three query perturbations. Returns (query, difficulty).

    Uses crc32 rather than the builtin hash() - str hashing is salted per-process by
    default (PYTHONHASHSEED), which would make variant assignment non-reproducible.
    """
    bucket = zlib.crc32(seed_key.encode()) % 3
    if bucket == 0:
        return legal_name, "easy"
    if bucket == 1:
        return legal_name_core, "medium"
    return legal_name_core.replace(" ", ""), "medium"


def build_evaluation_pairs(cfg: AppConfig, positives_path: Path, hard_negatives_path: Path) -> Path:
    out_path = cfg.benchmark.output_dir / "evaluation_pairs.parquet"
    eval_size = cfg.benchmark.eval_sample_size
    neg_size = max(1, eval_size // 5)
    seed_fraction = _seed_fraction(cfg.benchmark.seed)

    con = duckdb.connect()
    con.execute("SELECT setseed(?)", [seed_fraction])

    (n_jurisdictions,) = con.sql(
        f"SELECT COUNT(DISTINCT jurisdiction) FROM read_parquet('{positives_path}')"
    ).fetchone()
    per_bucket = max(1, eval_size // max(1, n_jurisdictions))

    # Stratified sample: cap per jurisdiction first so no single jurisdiction dominates,
    # then top up from the leftover pool if the cap left us short of eval_size.
    con.execute(f"""
        CREATE TEMP TABLE capped AS
        SELECT lei, legal_name, legal_name_core, legal_country
        FROM (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY jurisdiction ORDER BY random()) AS rn
            FROM read_parquet('{positives_path}')
        )
        WHERE rn <= {per_bucket}
    """)
    (capped_count,) = con.sql("SELECT COUNT(*) FROM capped").fetchone()

    if capped_count < eval_size:
        con.execute(f"""
            CREATE TEMP TABLE topup AS
            SELECT lei, legal_name, legal_name_core, legal_country
            FROM read_parquet('{positives_path}')
            WHERE lei NOT IN (SELECT lei FROM capped)
            ORDER BY random()
            LIMIT {eval_size - capped_count}
        """)
        pos_rows = con.sql("SELECT * FROM capped UNION ALL SELECT * FROM topup").fetchall()
    else:
        pos_rows = con.sql(f"SELECT * FROM capped ORDER BY random() LIMIT {eval_size}").fetchall()

    neg_rows = con.sql(f"""
        SELECT lei_a, lei_b, legal_name_core, jurisdiction
        FROM read_parquet('{hard_negatives_path}')
        ORDER BY random()
        LIMIT {neg_size}
    """).fetchall()
    con.close()

    rows = []
    for i, (lei, legal_name, legal_name_core, legal_country) in enumerate(pos_rows):
        query, difficulty = _name_variant(legal_name, legal_name_core, lei)
        rows.append(
            {
                "pair_id": f"pos_{i:07d}",
                "query_name": query,
                "query_name_norm": normalize_name(query),
                "query_country": legal_country,
                "expected_lei": lei,
                "confusable_lei": None,
                "case_type": "isin_confirmed",
                "difficulty": difficulty,
                "source": "positives",
            }
        )

    for i, (lei_a, lei_b, legal_name_core, jurisdiction) in enumerate(neg_rows):
        rows.append(
            {
                "pair_id": f"neg_{i:07d}",
                "query_name": legal_name_core,
                "query_name_norm": normalize_name(legal_name_core),
                "query_country": jurisdiction,
                "expected_lei": lei_a,
                "confusable_lei": lei_b,
                "case_type": "confusable_pair",
                "difficulty": "hard",
                "source": "hard_negatives",
            }
        )

    table = pa.Table.from_pylist(rows, schema=EVALUATION_PAIRS_SCHEMA)
    pq.write_table(table, out_path)
    logger.info(
        "evaluation_pairs: %d positive-derived + %d hard-negative-derived = %d total -> %s",
        len(pos_rows),
        len(neg_rows),
        len(rows),
        out_path,
    )
    return out_path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    cfg.benchmark.output_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    positives_path = generate_positives(cfg)
    hard_negatives_path = generate_hard_negatives(cfg)
    build_evaluation_pairs(cfg, positives_path, hard_negatives_path)
    logger.info("benchmark generation complete in %.0fs", time.monotonic() - started)


if __name__ == "__main__":
    main()
