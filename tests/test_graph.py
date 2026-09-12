import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from er.config import AppConfig, BenchmarkConfig, GleifConfig, OpenSearchConfig, SearchConfig
from er.graph.build import build_hierarchy, build_hierarchy_tree
from er.graph.edges import fetch_relationships_among


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


# --- build_hierarchy_tree (multi-hop) -------------------------------------------


def test_depth_1_matches_single_hop_behavior_leaves_unexpanded(cfg):
    # depth=1 (the default) must be identical in spirit to the original single-hop
    # build_hierarchy(): immediate neighbors are shown, but not expanded further.
    _write_entities(
        cfg,
        [
            _entity("LEI_A", "A"),
            _entity("LEI_B", "B"),
            _entity("LEI_C", "C"),
        ],
    )
    _write_relationships(
        cfg,
        [
            _rel("LEI_A", "LEI_B", "IS_DIRECTLY_CONSOLIDATED_BY"),
            _rel("LEI_B", "LEI_C", "IS_DIRECTLY_CONSOLIDATED_BY"),
        ],
    )
    _write_exceptions(cfg, [])

    root = build_hierarchy_tree(cfg, "LEI_A", depth=1)

    assert root.lei == "LEI_A"
    assert len(root.upward) == 1
    b = root.upward[0]
    assert b.lei == "LEI_B"
    assert b.expanded is False
    assert b.upward == []  # not expanded - would otherwise show LEI_C


def test_depth_2_expands_one_more_level(cfg):
    _write_entities(
        cfg,
        [
            _entity("LEI_A", "A"),
            _entity("LEI_B", "B"),
            _entity("LEI_C", "C"),
        ],
    )
    _write_relationships(
        cfg,
        [
            _rel("LEI_A", "LEI_B", "IS_DIRECTLY_CONSOLIDATED_BY"),
            _rel("LEI_B", "LEI_C", "IS_DIRECTLY_CONSOLIDATED_BY"),
        ],
    )
    _write_exceptions(cfg, [])

    root = build_hierarchy_tree(cfg, "LEI_A", depth=2)

    b = root.upward[0]
    assert b.expanded is True
    assert len(b.upward) == 1
    c = b.upward[0]
    assert c.lei == "LEI_C"
    assert c.expanded is False  # depth exhausted at this level


def test_cycle_does_not_infinite_loop(cfg):
    # A -> B -> A: a real (if unusual) possibility in GLEIF's relationship data.
    _write_entities(cfg, [_entity("LEI_A", "A"), _entity("LEI_B", "B")])
    _write_relationships(
        cfg,
        [
            _rel("LEI_A", "LEI_B", "IS_DIRECTLY_CONSOLIDATED_BY"),
            _rel("LEI_B", "LEI_A", "IS_DIRECTLY_CONSOLIDATED_BY"),
        ],
    )
    _write_exceptions(cfg, [])

    root = build_hierarchy_tree(cfg, "LEI_A", depth=5)  # would loop forever without protection

    b = root.upward[0]
    assert b.lei == "LEI_B"
    assert b.expanded is True
    a_again = b.upward[0]
    assert a_again.lei == "LEI_A"
    assert a_again.expanded is False  # already visited - not re-expanded


def test_max_nodes_budget_stops_expansion(cfg):
    # A chain of 5 entities; a budget of 2 expansions should only expand the root
    # and one more level before truncating.
    entities = [_entity(f"LEI_{i}", f"Entity {i}") for i in range(5)]
    rels = [_rel(f"LEI_{i}", f"LEI_{i+1}", "IS_DIRECTLY_CONSOLIDATED_BY") for i in range(4)]
    _write_entities(cfg, entities)
    _write_relationships(cfg, rels)
    _write_exceptions(cfg, [])

    root = build_hierarchy_tree(cfg, "LEI_0", depth=10, max_nodes=2)

    n1 = root.upward[0]
    assert n1.lei == "LEI_1"
    assert n1.expanded is True  # 2nd expansion (root was the 1st)
    n2 = n1.upward[0]
    assert n2.lei == "LEI_2"
    assert n2.expanded is False  # budget exhausted


def test_direction_children_only_expands_downward(cfg):
    _write_entities(cfg, [_entity("LEI_A", "A"), _entity("LEI_B", "B"), _entity("LEI_C", "C")])
    _write_relationships(
        cfg,
        [
            _rel("LEI_A", "LEI_B", "IS_DIRECTLY_CONSOLIDATED_BY"),  # A's parent is B (upward from A)
            _rel("LEI_C", "LEI_A", "IS_FUND-MANAGED_BY"),  # C's manager is A (downward from A)
        ],
    )
    _write_exceptions(cfg, [])

    root = build_hierarchy_tree(cfg, "LEI_A", depth=2, direction="children")

    assert root.upward == []
    assert len(root.downward) == 1
    assert root.downward[0].lei == "LEI_C"


# --- fetch_relationships_among (er.family's graph-confirmation query) ----------


def test_fetch_relationships_among_only_returns_edges_within_the_pool(cfg):
    _write_entities(cfg, [_entity("LEI_A", "A"), _entity("LEI_B", "B"), _entity("LEI_C", "C")])
    _write_relationships(
        cfg,
        [
            _rel("LEI_A", "LEI_B", "IS_FUND-MANAGED_BY"),  # both in pool - should be returned
            _rel("LEI_A", "LEI_C", "IS_FUND-MANAGED_BY"),  # LEI_C not in pool - should be excluded
        ],
    )
    _write_exceptions(cfg, [])

    edges = fetch_relationships_among(cfg, ["LEI_A", "LEI_B"])

    assert len(edges) == 1
    assert edges[0]["start_node_id"] == "LEI_A"
    assert edges[0]["end_node_id"] == "LEI_B"


def test_fetch_relationships_among_excludes_inactive(cfg):
    _write_entities(cfg, [_entity("LEI_A", "A"), _entity("LEI_B", "B")])
    _write_relationships(cfg, [_rel("LEI_A", "LEI_B", "IS_FUND-MANAGED_BY", status="INACTIVE")])
    _write_exceptions(cfg, [])

    assert fetch_relationships_among(cfg, ["LEI_A", "LEI_B"]) == []


def test_fetch_relationships_among_single_lei_returns_empty():
    # No config needed - a pool of <2 LEIs can't have an intra-pool edge, and the
    # function should short-circuit before ever querying.
    assert fetch_relationships_among(None, ["LEI_A"]) == []
