"""Tests for the three entity-agent enrichments:
- provisional private-entity registry (SPVs without LEIs)
- reverse N-PORT holder lookup
- SEC EDGAR full-text filing passages
"""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from er.agent.tools import (
    get_private_entity,
    get_security_holders,
    lookup_private_entity,
    search_filings,
)
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


def _write_nport(processed: Path) -> None:
    funds = pa.table({
        "accession_number": ["0000000001-26-000001", "0000000002-26-000002"],
        "registrant_name": ["PIMCO Funds", "BlackRock Funds V"],
        "series_name": ["PIMCO Income Fund", "BlackRock High Yield Portfolio"],
        "report_date": ["31-MAR-2026", "31-MAR-2026"],
        "filing_date": ["29-MAY-2026", "28-MAY-2026"],
    })
    holdings = pa.table({
        "accession_number": ["0000000001-26-000001", "0000000002-26-000002", "0000000001-26-000001"],
        "holding_id": ["h1", "h2", "h3"],
        "issuer_name": ["BEIGNET INVESTOR LLC", "Beignet Investor LLC", "US TREASURY"],
        "issuer_title": ["BEIGNET INVESTOR LLC SR SECURED 144A 05/49 6.581", "Beignet Investor LLC", "T-BILL"],
        "issuer_cusip": ["076912AA2", "076912AA2", "912797XX"],
        "currency_value": [4_226_779_408.12, 408_698_238.56, 1_000_000.0],
    })
    pq.write_table(funds, processed / "nport_funds.parquet")
    pq.write_table(holdings, processed / "nport_holdings.parquet")


def test_private_entity_registry_is_explicitly_provisional():
    result = lookup_private_entity("Beignet Investor LLC")
    assert result.data["found"] is True
    match = result.data["matches"][0]
    assert match["entity_id"] == "provisional:beignet-investor"
    assert match["provisional"] is True
    assert match["resolution_status"] == "PROVISIONAL"
    assert match["lei"] is None
    assert match["relationships"]
    assert any(r["direction"] == "incoming" and r["type"] == "owns" and r["pct"] == 100
               for r in match["relationships"])
    assert any(f.predicate == "private_relationship.incoming.owns.pct" for f in result.facts)
    assert any("PROVISIONAL" in w for w in result.evidence[0].warnings)


def test_private_entity_registry_includes_registered_project_company():
    result = get_private_entity("provisional:laidley")
    assert result.data["found"] is True
    entity = result.data["entity"]
    assert entity["name"] == "Laidley LLC"
    assert entity["registration_id"] == "46043373Q"
    assert entity["jurisdiction"] == "US-LA"
    assert any(r["type"] == "landlord_of" for r in entity["relationships"])


def test_reverse_nport_holders(cfg):
    _write_nport(cfg.entity.processed_dir)
    result = get_security_holders(cfg, "Beignet", id_type="name")
    data = result.data
    assert data["found"] is True
    assert data["fund_reports"] == 2
    assert data["registrants"] == 2
    assert round(data["reported_value_usd"], 2) == 4_635_477_646.68
    assert {h["registrant_name"] for h in data["holders"]} == {"PIMCO Funds", "BlackRock Funds V"}
    assert any("N-PORT" in w for w in result.evidence[0].warnings)
    assert any(f.predicate == "nport.holder_value_usd" for f in result.facts)


def test_reverse_nport_holders_by_cusip(cfg):
    _write_nport(cfg.entity.processed_dir)
    result = get_security_holders(cfg, "076912AA2", id_type="cusip")
    assert result.data["found"] is True
    assert result.data["fund_reports"] == 2
    assert all(h["cusip"] == "076912AA2" for h in result.data["holders"])


class _FakeResponse:
    def __init__(self, payload=None, text: str = "") -> None:
        self._payload = payload
        self.text = text

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, fts: dict, document: str) -> None:
        self.fts = fts
        self.document = document
        self.calls: list[str] = []

    def get(self, url, params=None, headers=None):
        self.calls.append(url)
        if url.endswith("/LATEST/search-index"):
            return _FakeResponse(payload=self.fts)
        return _FakeResponse(text=self.document)


def test_sec_filing_text_search(cfg):
    fts = {"hits": {"hits": [{
        "_id": "0001628280-25-047240:meta-20250930.htm",
        "_source": {
            "form": "10-Q", "file_date": "2025-10-30", "ciks": ["0001326801"],
            "adsh": "0001628280-25-047240", "file_type": "10-Q",
            "display_names": ["Meta Platforms, Inc."],
        },
    }]}}
    html = "<html><body><p>Meta entered into a joint venture with an affiliate of funds managed by Blue Owl Capital.</p></body></html>"
    client = _FakeClient(fts, html)
    result = search_filings(cfg, "Beignet Investor", cik="1326801", forms=["10-Q"], client=client)
    data = result.data
    assert data["found"] is True
    hit = data["hits"][0]
    assert hit["form"] == "10-Q"
    assert "meta-20250930.htm" in hit["url"]
    assert "joint venture" in hit["passage"]
    assert any("EDGAR full-text" in w for w in result.evidence[0].warnings)
    assert any(f.predicate == "filing.form" for f in result.facts)


def test_passage_anchors_on_rarest_query_term():
    from er.knowledge.sec_filings import _passage

    text = ("value " * 80) + "the residual value guarantee threshold declines over time " + ("value " * 80)
    passage, start, _ = _passage(text, "residual value guarantee", radius=100)
    assert "residual value guarantee" in passage
    assert start > 0


def test_mcp_server_exposes_enrichment_tools():
    import asyncio

    from er.agent.mcp_server import mcp

    names = {tool.name for tool in asyncio.run(mcp.list_tools())}
    assert {"lookup_private_entity", "get_private_entity", "get_security_holders", "search_filings"} <= names
