"""Unit tests for er.agent.tools' Evidence construction, driven entirely from
temp Parquet fixtures (same fixture style as test_graph.py) - no live
OpenSearch needed for get_entity_profile_tool/get_relationship_hierarchy.
search_entity's name-search path needs live OpenSearch + er.matching.matcher,
so it's exercised manually (python -m er.cli.ask), not here.
"""

import asyncio
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from er.agent.tools import get_entity_profile_tool, get_relationship_hierarchy
from er.agent import orchestrator
from er.config import (
    AppConfig,
    BenchmarkConfig,
    EntityConfig,
    GleifConfig,
    OpenSearchConfig,
    SearchConfig,
    Sec13FConfig,
)


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


# --- get_entity_profile_tool: reads entity/entities.parquet + entity_identifiers.parquet ---

_ENTITIES_SCHEMA = pa.schema(
    [
        ("entity_id", pa.string()),
        ("primary_lei", pa.string()),
        ("canonical_name", pa.string()),
        ("entity_type", pa.string()),
        ("jurisdiction", pa.string()),
        ("legal_country", pa.string()),
        ("entity_status", pa.string()),
        ("entity_creation_date", pa.string()),
        ("initial_registration_date", pa.string()),
        ("last_update_date", pa.string()),
        ("next_renewal_date", pa.string()),
        ("registration_status", pa.string()),
        ("gleif_snapshot_date", pa.string()),
    ]
)

_IDENTIFIERS_SCHEMA = pa.schema(
    [
        ("entity_id", pa.string()),
        ("identifier_type", pa.string()),
        ("identifier_value", pa.string()),
        ("confidence", pa.string()),
        ("source", pa.string()),
        ("source_file", pa.string()),
        ("snapshot_date", pa.string()),
        ("ingested_at", pa.string()),
    ]
)


def _write_canonical_entity(cfg, entity_id, name, **overrides):
    row = {
        "entity_id": entity_id,
        "primary_lei": entity_id,
        "canonical_name": name,
        "entity_type": None,
        "jurisdiction": None,
        "legal_country": None,
        "entity_status": "ACTIVE",
        "entity_creation_date": None,
        "initial_registration_date": None,
        "last_update_date": None,
        "next_renewal_date": None,
        "registration_status": "ISSUED",
        "gleif_snapshot_date": "2026-09-11",
    }
    row.update(overrides)
    pq.write_table(pa.Table.from_pylist([row], schema=_ENTITIES_SCHEMA), cfg.entity.processed_dir / "entities.parquet")


def _write_identifiers(cfg, rows):
    pq.write_table(
        pa.Table.from_pylist(rows, schema=_IDENTIFIERS_SCHEMA if not rows else None),
        cfg.entity.processed_dir / "entity_identifiers.parquet",
    )


_GLEIF_ENTITIES_SCHEMA = pa.schema([("lei", pa.string()), ("legal_name", pa.string())])
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


def _write_gleif_relationship_tables(cfg, entity_id, name):
    # get_entity_profile_tool's profile always includes GLEIF relationship
    # data (er.entity.profile.get_entity_profile calls build_hierarchy
    # unconditionally) - these three tables must exist even for a
    # relationship-free profile test.
    pq.write_table(pa.Table.from_pylist([{"lei": entity_id, "legal_name": name}], schema=_GLEIF_ENTITIES_SCHEMA), cfg.gleif.processed_dir / "gleif_entities.parquet")
    pq.write_table(pa.Table.from_pylist([], schema=_RELATIONSHIPS_SCHEMA), cfg.gleif.processed_dir / "gleif_relationships.parquet")
    pq.write_table(pa.Table.from_pylist([], schema=_EXCEPTIONS_SCHEMA), cfg.gleif.processed_dir / "gleif_relationship_exceptions.parquet")


def test_profile_not_found_returns_warning_evidence(cfg):
    _write_canonical_entity(cfg, "LEI_A", "A Corp")
    _write_gleif_relationship_tables(cfg, "LEI_A", "A Corp")

    result = get_entity_profile_tool(cfg, "LEI_MISSING")

    assert result.data == {"found": False}
    assert len(result.evidence) == 1
    assert result.evidence[0].result_count == 0
    assert "No canonical entity found" in result.evidence[0].warnings[0]


def test_profile_found_emits_identity_and_lineage_evidence(cfg):
    _write_canonical_entity(cfg, "LEI_A", "A Corp")
    _write_gleif_relationship_tables(cfg, "LEI_A", "A Corp")
    _write_identifiers(cfg, [])

    result = get_entity_profile_tool(cfg, "LEI_A")

    assert result.data["found"] is True
    assert result.data["profile"]["canonical_name"] == "A Corp"
    sources = [e.source for e in result.evidence]
    assert "GLEIF entity record" in sources
    assert "GLEIF registration lineage" in sources
    assert all(e.query_hash for e in result.evidence)  # every evidence entry is reproducible
    # No identifiers/sec_13f data was written, so those evidence entries must not appear.
    assert "Attached source identifiers" not in sources
    assert "SEC 13F filing" not in sources


def test_profile_with_identifiers_emits_identifier_evidence(cfg):
    _write_canonical_entity(cfg, "LEI_A", "A Corp")
    _write_gleif_relationship_tables(cfg, "LEI_A", "A Corp")
    _write_identifiers(
        cfg,
        [
            {
                "entity_id": "LEI_A",
                "identifier_type": "ISIN",
                "identifier_value": "US0000000001",
                "confidence": "SOURCE",
                "source": "gleif",
                "source_file": None,
                "snapshot_date": "2026-09-11",
                "ingested_at": None,
            }
        ],
    )

    result = get_entity_profile_tool(cfg, "LEI_A")

    identifier_evidence = next(e for e in result.evidence if e.source == "Attached source identifiers")
    assert identifier_evidence.result_count == 1
    assert identifier_evidence.record_refs == ["LEI_A"]


# --- get_relationship_hierarchy: reads gleif_entities/relationships/exceptions ---


def _write_gleif_entities(cfg, rows):
    pq.write_table(
        pa.Table.from_pylist(rows, schema=_GLEIF_ENTITIES_SCHEMA if not rows else None),
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


def test_hierarchy_evidence_counts_every_node_in_the_tree(cfg):
    # depth=1 (immediate neighbors shown, not expanded further - see
    # test_graph.py's own depth=1 test) keeps this a clean "root + one parent"
    # count; depth=2 would also re-expand B and re-discover A as B's
    # unexpanded child via the same relationship row read in reverse (see
    # test_graph.py's cycle-protection tests), which is correct but not what
    # this test is checking.
    _write_gleif_entities(cfg, [{"lei": "LEI_A", "legal_name": "A"}, {"lei": "LEI_B", "legal_name": "B"}])
    _write_relationships(cfg, [{"start_node_id": "LEI_A", "end_node_id": "LEI_B", "relationship_type": "IS_DIRECTLY_CONSOLIDATED_BY", "relationship_status": "ACTIVE"}])
    _write_exceptions(cfg, [])

    result = get_relationship_hierarchy(cfg, "LEI_A", depth=1)

    assert result.data["tree"]["lei"] == "LEI_A"
    assert len(result.evidence) == 1
    ev = result.evidence[0]
    assert ev.source == "GLEIF relationship/exception records"
    assert ev.result_count == 2  # root + one parent
    assert "Depth = 1" in ev.criteria


def test_hierarchy_query_hash_is_stable_for_same_args(cfg):
    _write_gleif_entities(cfg, [{"lei": "LEI_A", "legal_name": "A"}])
    _write_relationships(cfg, [])
    _write_exceptions(cfg, [])

    r1 = get_relationship_hierarchy(cfg, "LEI_A", depth=1)
    r2 = get_relationship_hierarchy(cfg, "LEI_A", depth=1)

    assert r1.evidence[0].query_hash == r2.evidence[0].query_hash


def test_agent_requires_an_mcp_lookup_and_valid_citation_before_submitting(cfg, monkeypatch):
    """Regression test for an OpenRouter response that tried to answer from
    the system prompt, without ever using the MCP server. The orchestrator
    must force a data-tool call first and reject uncited final answers."""

    class FakeClient:
        async def list_tools(self):
            return SimpleNamespace(
                tools=[SimpleNamespace(name="search_entity", description="search", input_schema={"type": "object"})]
            )

        async def call_tool(self, name, args):
            assert name == "search_entity"
            return SimpleNamespace(
                structured_content={
                    "data": {"matches": []},
                    "evidence": [
                        {
                            "evidence_id": "ev_test",
                            "source": "test source",
                            "fact_type": "lookup",
                            "criteria": [],
                            "record_refs": [],
                            "fields_used": [],
                            "result_count": 0,
                            "query_hash": "abc123",
                            "warnings": [],
                        }
                    ],
                }
            )

    responses = iter(
        [
            # A model tries to free-text answer. This must not be accepted.
            {"choices": [{"message": {"content": "I know this already."}}]},
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_search",
                                    "function": {"name": "search_entity", "arguments": '{"query": "Point72"}'},
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "id": "call_submit",
                                    "function": {
                                        "name": "submit_answer",
                                        "arguments": (
                                            '{"answer": "No matches [1]", '
                                            '"citations": [{"marker": 1, "evidence_id": "ev_test"}]}'
                                        ),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        ]
    )
    tool_choices = []

    async def fake_call(_cfg, _messages, _tools, tool_choice=None):
        tool_choices.append(tool_choice)
        return next(responses)

    monkeypatch.setattr(orchestrator, "_call_openrouter", fake_call)

    result = asyncio.run(orchestrator.ask(FakeClient(), cfg, "Find Point72"))

    assert tool_choices[0]["function"]["name"] == "search_entity"
    assert result.citations[0].evidence_id == "ev_test"
