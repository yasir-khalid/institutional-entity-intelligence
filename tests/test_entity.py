"""Unit tests for the canonical entity layer - build.py's DuckDB assembly and
sources.py's graceful-degradation-when-missing behavior. Uses small synthetic
Parquet fixtures, same pattern as tests/test_graph.py and tests/test_benchmark.py -
no live OpenSearch needed."""

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from er.config import (
    AppConfig,
    BenchmarkConfig,
    EntityConfig,
    GleifConfig,
    OpenSearchConfig,
    SearchConfig,
    Sec13FConfig,
)
from er.entity.build import build_entities, build_identifiers
from er.entity.sources import isin_identifiers_sql, sec_13f_identifiers_sql


@pytest.fixture
def cfg(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    benchmark_dir = tmp_path / "benchmark"
    benchmark_dir.mkdir()
    return AppConfig(
        gleif=GleifConfig(
            raw_dir=tmp_path / "raw",
            processed_dir=processed,
            entities_zip="e.zip",
            relationships_zip="r.zip",
            exceptions_zip="x.zip",
            isin_lei_zip="i.zip",
        ),
        sec_13f=Sec13FConfig(raw_dir=tmp_path / "sec_13f_raw", processed_dir=processed),
        entity=EntityConfig(processed_dir=processed),
        opensearch=OpenSearchConfig(index_name="test"),
        search=SearchConfig(),
        benchmark=BenchmarkConfig(output_dir=benchmark_dir),
    )


_ENTITIES_SCHEMA = pa.schema(
    [
        ("lei", pa.string()),
        ("legal_name", pa.string()),
        ("entity_category", pa.string()),
        ("jurisdiction", pa.string()),
        ("legal_country", pa.string()),
        ("entity_status", pa.string()),
    ]
)


def _write_entities(cfg):
    table = pa.Table.from_pylist(
        [
            {
                "lei": "LEI_A",
                "legal_name": "Acme Capital LLC",
                "entity_category": "GENERAL",
                "jurisdiction": "US-DE",
                "legal_country": "US",
                "entity_status": "ACTIVE",
            },
            {
                "lei": "LEI_B",
                "legal_name": "Beta Fund LP",
                "entity_category": "FUND",
                "jurisdiction": "KY",
                "legal_country": "KY",
                "entity_status": "ACTIVE",
            },
        ],
        schema=_ENTITIES_SCHEMA,
    )
    pq.write_table(table, cfg.gleif.processed_dir / "gleif_entities.parquet")


def test_build_entities_seeds_one_row_per_gleif_lei(cfg):
    _write_entities(cfg)
    n = build_entities(cfg)
    assert n == 2

    con_table = pq.read_table(cfg.entity.processed_dir / "entities.parquet").to_pylist()
    by_id = {r["entity_id"]: r for r in con_table}
    assert by_id["LEI_A"]["canonical_name"] == "Acme Capital LLC"
    assert by_id["LEI_A"]["primary_lei"] == "LEI_A"
    assert by_id["LEI_B"]["entity_type"] == "FUND"


def test_isin_source_returns_none_when_bridge_missing(cfg):
    assert isin_identifiers_sql(cfg) is None


def test_sec_13f_source_returns_none_when_crosswalk_missing(cfg):
    assert sec_13f_identifiers_sql(cfg) is None


def test_build_identifiers_unions_available_sources_and_skips_unmatched(cfg):
    isin_table = pa.Table.from_pylist(
        [{"lei": "LEI_A", "isin": "US0001", "source_file": "x", "snapshot_date": "2026-01-01", "ingested_at": "x"}],
        schema=pa.schema(
            [
                ("lei", pa.string()),
                ("isin", pa.string()),
                ("source_file", pa.string()),
                ("snapshot_date", pa.string()),
                ("ingested_at", pa.string()),
            ]
        ),
    )
    pq.write_table(isin_table, cfg.gleif.processed_dir / "isin_lei.parquet")

    crosswalk_table = pa.Table.from_pylist(
        [
            {"lei": "LEI_A", "cik": "0000001", "decision": "AUTO_MATCH"},
            {"lei": "LEI_B", "cik": "0000002", "decision": "UNMATCHED"},
            {"lei": None, "cik": "0000003", "decision": "UNMATCHED"},
        ],
        schema=pa.schema([("lei", pa.string()), ("cik", pa.string()), ("decision", pa.string())]),
    )
    pq.write_table(crosswalk_table, cfg.sec_13f.processed_dir / "crosswalk_sec_13f_gleif.parquet")

    n = build_identifiers(cfg)
    assert n == 2  # 1 ISIN + 1 AUTO_MATCH CIK; the UNMATCHED/null-lei rows are excluded

    rows = pq.read_table(cfg.entity.processed_dir / "entity_identifiers.parquet").to_pylist()
    types = {(r["entity_id"], r["identifier_type"]) for r in rows}
    assert ("LEI_A", "ISIN") in types
    assert ("LEI_A", "CIK") in types
    assert ("LEI_B", "CIK") not in types


def test_build_identifiers_returns_zero_when_no_sources_available(cfg):
    n = build_identifiers(cfg)
    assert n == 0
