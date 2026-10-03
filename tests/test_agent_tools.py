"""Unit tests for er.agent.tools' Evidence construction, driven from an
in-memory serving store (er.serving.store.MemoryStore) - no live OpenSearch
needed for get_entity_profile_tool/get_relationship_hierarchy.
search_entity's name-search path needs live OpenSearch + er.matching.matcher,
so it's exercised manually (python -m er.cli.ask), not here.
"""

import asyncio
from types import SimpleNamespace

import pytest

from er.agent import orchestrator
from er.agent.tools import get_entity_profile_tool, get_relationship_hierarchy
from er.config import (
    AppConfig,
    BenchmarkConfig,
    EntityConfig,
    GleifConfig,
    OpenSearchConfig,
    SearchConfig,
    Sec13FConfig,
)
from er.serving.store import ENTITIES, RELATIONSHIPS, MemoryStore


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


@pytest.fixture
def store():
    return MemoryStore()


# --- get_entity_profile_tool: reads the published entity document ---


def _write_canonical_entity(store, entity_id, name, identifiers=()):
    store.put(
        ENTITIES,
        entity_id,
        {
            "entity_id": entity_id,
            "canonical_name": name,
            "entity_status": "ACTIVE",
            "registration_status": "ISSUED",
            "gleif_snapshot_date": "2026-09-11",
            "identifiers": list(identifiers),
            "identifier_total": len(identifiers),
            "ciks": [],
        },
    )


def test_profile_not_found_returns_warning_evidence(store):
    _write_canonical_entity(store, "LEI_A", "A Corp")

    result = get_entity_profile_tool(store, "LEI_MISSING")

    assert result.data == {"found": False}
    assert len(result.evidence) == 1
    assert result.evidence[0].result_count == 0
    assert "No canonical entity found" in result.evidence[0].warnings[0]


def test_profile_found_emits_identity_and_lineage_evidence(store):
    _write_canonical_entity(store, "LEI_A", "A Corp")

    result = get_entity_profile_tool(store, "LEI_A")

    assert result.data["found"] is True
    assert result.data["profile"]["canonical_name"] == "A Corp"
    sources = [e.source for e in result.evidence]
    assert "GLEIF entity record" in sources
    assert "GLEIF registration lineage" in sources
    assert all(e.query_hash for e in result.evidence)  # every evidence entry is reproducible
    # No identifiers/sec_13f data was written, so those evidence entries must not appear.
    assert "Attached source identifiers" not in sources
    assert "SEC 13F filing" not in sources


def test_profile_with_identifiers_emits_identifier_evidence(store):
    _write_canonical_entity(
        store,
        "LEI_A",
        "A Corp",
        identifiers=[
            {
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

    result = get_entity_profile_tool(store, "LEI_A")

    identifier_evidence = next(e for e in result.evidence if e.source == "Attached source identifiers")
    assert identifier_evidence.result_count == 1
    assert identifier_evidence.record_refs == ["LEI_A"]


# --- get_relationship_hierarchy: reads relationship documents + entity names ---


def test_hierarchy_evidence_counts_every_node_in_the_tree(store):
    # depth=1 (immediate neighbors shown, not expanded further - see
    # test_graph.py's own depth=1 test) keeps this a clean "root + one parent"
    # count; depth=2 would also re-expand B and re-discover A as B's
    # unexpanded child via the same relationship row read in reverse (see
    # test_graph.py's cycle-protection tests), which is correct but not what
    # this test is checking.
    _write_canonical_entity(store, "LEI_A", "A")
    _write_canonical_entity(store, "LEI_B", "B")
    store.put(
        RELATIONSHIPS,
        "LEI_A:LEI_B:IS_DIRECTLY_CONSOLIDATED_BY",
        {
            "start_node_id": "LEI_A",
            "end_node_id": "LEI_B",
            "relationship_type": "IS_DIRECTLY_CONSOLIDATED_BY",
            "relationship_status": "ACTIVE",
        },
    )

    result = get_relationship_hierarchy(store, "LEI_A", depth=1)

    assert result.data["tree"]["lei"] == "LEI_A"
    assert len(result.evidence) == 1
    ev = result.evidence[0]
    assert ev.source == "GLEIF relationship/exception records"
    assert ev.result_count == 2  # root + one parent
    assert "Depth = 1" in ev.criteria


def test_hierarchy_query_hash_is_stable_for_same_args(store):
    _write_canonical_entity(store, "LEI_A", "A")

    r1 = get_relationship_hierarchy(store, "LEI_A", depth=1)
    r2 = get_relationship_hierarchy(store, "LEI_A", depth=1)

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
    first_messages = []

    async def fake_call(_cfg, _messages, _tools, tool_choice=None):
        tool_choices.append(tool_choice)
        if not first_messages:
            first_messages.extend(_messages)
        return next(responses)

    monkeypatch.setattr(orchestrator, "_call_openrouter", fake_call)

    result = asyncio.run(
        orchestrator.ask(
            FakeClient(),
            cfg,
            "Find Point72",
            history=[
                {"role": "user", "content": "Tell me about Point72."},
                {"role": "assistant", "content": "I found the entity."},
            ],
        )
    )

    assert tool_choices[0]["function"]["name"] == "search_entity"
    assert [(message["role"], message["content"]) for message in first_messages[1:3]] == [
        ("user", "Tell me about Point72."),
        ("assistant", "I found the entity."),
    ]
    assert result.citations[0].evidence_id == "ev_test"
