"""Isolated browser-test API: real routes/jobs, fixture store and model boundary.

Only launched explicitly by web/playwright.config.ts. No live OpenSearch or
provider requests; production modules have no test flags or alternate paths.
"""
import asyncio
import hashlib

from er.agent.models import AskResult, Citation, Derivation, Evidence, Fact, FactAddress, GateCheck
from er.api import app as api
from er.config import load_config
from er.serving.store import COVERAGE, DECISIONS, ENTITIES, FILERS, RELATIONSHIPS, MemoryStore

LEI = "254900TESTENTITY00001"
decision = {"node_id": "cik:0000000001", "source_name": "Acme Capital", "lei": LEI, "decision": "REVIEW",
            "score": 120.0, "gap": 2.0, "reason": "Close candidate scores", "runner_up_lei": None,
            "runner_up_name": None, "runner_up_score": None, "config_hash": "fixture-config", "decided_on": "2026-06-30",
            "feature_contributions": {"name_exact": 100.0, "country_match": 20.0}}
entity = {"entity_id": LEI, "canonical_name": "Acme Capital Management", "legal_country": "US", "jurisdiction": "US",
          "entity_status": "ACTIVE", "registration_status": "ISSUED", "gleif_snapshot_date": "2026-06-30",
          "identifiers": [], "ciks": ["0000000001"], "connections": {"linked_records": [], "groups": []},
          "match_decisions": [decision], "exceptions": []}
store = MemoryStore({ENTITIES: {LEI: entity}, DECISIONS: {decision["node_id"]: decision}, RELATIONSHIPS: {}, FILERS: {
    "0000000001": {"cik": "0000000001", "latest_period_of_report": "30-JUN-2026", "latest_filing_date": "14-AUG-2026",
                   "reported_security_count": 1, "value_unit": "USD", "top_reported_holdings": [{"name_of_issuer": "Apple Inc", "value": 1234567, "cusip": "037833100"}]}
}, COVERAGE: {"current": {"generation": "aaaaaaaa11111111", "previous_generation": None, "published_at": "2026-10-11T12:00:00+00:00",
    "partial": False, "indexes": {"entities": {"index": "fixture_entities", "count": 1}}, "decisions": {"REVIEW": 1},
    "sources": [{"source": "gleif", "label": "GLEIF LEI", "available": True, "as_of": "2026-06-30", "quarantined": 0,
                 "caveat": "Legal identity and accounting relationships", "tables": [{"name": "gleif_entities", "record_count": 1,
                 "as_of": "2026-06-30", "schema": [{"name": "lei", "type": "VARCHAR"}]}]}]}}})
cfg = load_config().model_copy(deep=True)
cfg.workspace.poll_seconds = 0.05


class Mcp:
    async def __aexit__(self, *args):
        pass


async def connect():
    return Mcp()


async def ask(client, cfg, question, entity_id, **options):
    await options["on_event"]({"type": "status", "message": "Reading the GLEIF source record"})
    if "failure" in question.lower():
        raise RuntimeError("Fixture provider unavailable")
    if "slow" in question.lower():
        await asyncio.sleep(5)
    else:
        await asyncio.sleep(0.1)
    evidence_id = "ev_" + hashlib.sha256(question.encode()).hexdigest()[:12]
    xbrl_id = "ev_xbrl_" + hashlib.sha256(question.encode()).hexdigest()[:8]
    return AskResult(
        answer=(
            "Acme Capital Management is registered in the United States. [1] Its reported total assets "
            "rose to $1,100,000 as of 30 June 2026, a 10% increase on the prior year. [2]"
        ),
        citations=[Citation(marker=1, evidence_id=evidence_id), Citation(marker=2, evidence_id=xbrl_id)],
        evidence={
            evidence_id: Evidence(
                evidence_id=evidence_id, source="gleif", fact_type="lookup", query_hash="fixture-query",
                record_refs=[LEI], criteria=["Exact LEI lookup"], fields_used=["legal_country"],
                result_count=1, source_timestamp="2026-06-30"),
            xbrl_id: Evidence(
                evidence_id=xbrl_id, source="sec_xbrl", fact_type="derivation", query_hash="fixture-xbrl",
                record_refs=["0000000001"], criteria=["CIK 0000000001 · us-gaap:Assets"],
                fields_used=["val"], result_count=2, source_timestamp="2026-06-30"),
        },
        facts={
            "f_country": Fact(
                fact_id="f_country", evidence_id=evidence_id, subject=LEI, predicate="legal_country", value="US",
                address=FactAddress(source="gleif", document_id=LEI, locator="entity", field="legal_country")),
            "f_assets_prior": Fact(
                fact_id="f_assets_prior", evidence_id=xbrl_id, subject="0000000001", predicate="xbrl.Assets.value",
                value=1_000_000, unit="USD", as_of="2025-06-30",
                address=FactAddress(source="sec_xbrl", document_id="0000000001-25-000001",
                                   locator="companyfacts/us-gaap/Assets@2025-06-30", field="val")),
            "f_assets_latest": Fact(
                fact_id="f_assets_latest", evidence_id=xbrl_id, subject="0000000001", predicate="xbrl.Assets.value",
                value=1_100_000, unit="USD", as_of="2026-06-30",
                address=FactAddress(source="sec_xbrl", document_id="0000000001-26-000001",
                                   locator="companyfacts/us-gaap/Assets@2026-06-30", field="val")),
            "f_assets_change": Fact(
                fact_id="f_assets_change", evidence_id=xbrl_id, subject="0000000001",
                predicate="xbrl.Assets.percent_change", value=10.0, unit="percent", as_of="2026-06-30",
                provenance_class="DERIVED_FACT",
                address=FactAddress(source="sec_xbrl", document_id="0000000001-26-000001",
                                   locator="derived:percent_change", field="value")),
        },
        derivations={
            "f_assets_change": Derivation(
                fact_id="f_assets_change", formula_id="percent_change",
                expression="(1,100,000 − 1,000,000) / 1,000,000 × 100",
                inputs=["f_assets_prior", "f_assets_latest"]),
        },
        gates=[
            GateCheck(key="addressed", label="Every value is addressed", passed=True),
            GateCheck(key="dated", label="Every value is dated", passed=True),
            GateCheck(key="derivation_inputs", label="Derivation inputs present", passed=True),
            GateCheck(key="provenance", label="Provenance class consistent", passed=True),
            GateCheck(key="units", label="Units compatible", passed=True),
            GateCheck(key="recomputes", label="Derived values recompute", passed=True),
        ],
    )


api._cfg = lambda: cfg
api.get_store = lambda cfg: store
api._connect_mcp_client = connect
api.agent_ask = ask
app = api.app
