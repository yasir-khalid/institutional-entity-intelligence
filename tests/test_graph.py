import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from er.config import AppConfig, BenchmarkConfig, GleifConfig, OpenSearchConfig, SearchConfig
from er.graph.build import build_hierarchy


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
        opensearch=OpenSearchConfig(index_name="test"),
        search=SearchConfig(),
        benchmark=BenchmarkConfig(output_dir=benchmark_dir),
    )


_ENTITIES_SCHEMA = pa.schema([("lei", pa.string()), ("legal_name", pa.string())])
_RELATIONSHIPS_SCHEMA = pa.schema(
    [
        ("start_node_id", pa.string()),
        ("end_node_id", pa.string()),
        ("relationship_type", pa.string()),
        ("relationship_status", pa.string()),
    ]
)
_EXCEPTIONS_SCHEMA = pa.schema(
    [("lei", pa.string()), ("exception_category", pa.string()), ("exception_reason", pa.string())]
)


def _write_entities(cfg, rows):
    pq.write_table(
        pa.Table.from_pylist(rows, schema=_ENTITIES_SCHEMA if not rows else None),
        cfg.gleif.processed_dir / "gleif_entities.parquet",
    )


def _write_relationships(cfg, rows):
    pq.write_table(
        pa.Table.from_pylist(rows, schema=_RELATIONSHIPS_SCHEMA if not rows else None),
        cfg.gleif.processed_dir / "gleif_relationships.parquet",
    )


def _write_exceptions(cfg, rows):
    pq.write_table(
        pa.Table.from_pylist(rows, schema=_EXCEPTIONS_SCHEMA if not rows else None),
        cfg.gleif.processed_dir / "gleif_relationship_exceptions.parquet",
    )


def _entity(lei, name):
    return {"lei": lei, "legal_name": name}


def _rel(start, end, rel_type, status="ACTIVE"):
    return {
        "start_node_id": start,
        "end_node_id": end,
        "relationship_type": rel_type,
        "relationship_status": status,
    }


def test_upward_relationship_resolves_parent_with_name(cfg):
    _write_entities(cfg, [_entity("LEI_CHILD", "Child Fund"), _entity("LEI_PARENT", "Parent Holdings")])
    _write_relationships(cfg, [_rel("LEI_CHILD", "LEI_PARENT", "IS_DIRECTLY_CONSOLIDATED_BY")])
    _write_exceptions(cfg, [])

    result = build_hierarchy(cfg, "LEI_CHILD")

    assert result.name == "Child Fund"
    assert len(result.upward) == 1
    edge = result.upward[0]
    assert edge.lei == "LEI_PARENT"
    assert edge.name == "Parent Holdings"
    assert edge.label == "Direct parent"
    assert result.downward == []


def test_downward_relationship_resolves_subsidiary_with_name(cfg):
    _write_entities(cfg, [_entity("LEI_MGR", "Manager LLP"), _entity("LEI_FUND", "Managed Fund")])
    _write_relationships(cfg, [_rel("LEI_FUND", "LEI_MGR", "IS_FUND-MANAGED_BY")])
    _write_exceptions(cfg, [])

    result = build_hierarchy(cfg, "LEI_MGR")

    assert result.upward == []
    assert len(result.downward) == 1
    edge = result.downward[0]
    assert edge.lei == "LEI_FUND"
    assert edge.name == "Managed Fund"
    assert edge.label == "Funds managed"


def test_inactive_relationships_are_excluded(cfg):
    _write_entities(cfg, [_entity("LEI_CHILD", "Child"), _entity("LEI_OLD_PARENT", "Old Parent")])
    _write_relationships(
        cfg, [_rel("LEI_CHILD", "LEI_OLD_PARENT", "IS_DIRECTLY_CONSOLIDATED_BY", status="INACTIVE")]
    )
    _write_exceptions(cfg, [])

    result = build_hierarchy(cfg, "LEI_CHILD")

    assert result.upward == []
    assert result.downward == []


def test_exception_reported_when_no_covering_relationship(cfg):
    _write_entities(cfg, [_entity("LEI_SOLO", "Solo Entity")])
    _write_relationships(cfg, [])
    _write_exceptions(
        cfg,
        [
            {
                "lei": "LEI_SOLO",
                "exception_category": "ULTIMATE_ACCOUNTING_CONSOLIDATION_PARENT",
                "exception_reason": "NO_KNOWN_PERSON",
            }
        ],
    )

    result = build_hierarchy(cfg, "LEI_SOLO")

    assert len(result.exceptions) == 1
    exc = result.exceptions[0]
    assert exc.label == "Ultimate parent"
    assert exc.reason_text == "no known parent"


def test_exception_suppressed_when_active_relationship_covers_it(cfg):
    # This is the specific safeguard the project keeps calling out: a missing
    # relationship row is not a confirmed absence of a parent, but the inverse
    # matters too - don't report a "gap" when an active relationship already
    # answers the question.
    _write_entities(cfg, [_entity("LEI_CHILD", "Child"), _entity("LEI_PARENT", "Parent")])
    _write_relationships(cfg, [_rel("LEI_CHILD", "LEI_PARENT", "IS_ULTIMATELY_CONSOLIDATED_BY")])
    _write_exceptions(
        cfg,
        [
            {
                "lei": "LEI_CHILD",
                "exception_category": "ULTIMATE_ACCOUNTING_CONSOLIDATION_PARENT",
                "exception_reason": "NO_KNOWN_PERSON",
            }
        ],
    )

    result = build_hierarchy(cfg, "LEI_CHILD")

    assert len(result.upward) == 1
    assert result.exceptions == []


def test_unknown_entity_with_no_data_returns_empty_result(cfg):
    _write_entities(cfg, [])
    _write_relationships(cfg, [])
    _write_exceptions(cfg, [])

    result = build_hierarchy(cfg, "LEI_NOWHERE")

    assert result.name is None
    assert result.upward == []
    assert result.downward == []
    assert result.exceptions == []
