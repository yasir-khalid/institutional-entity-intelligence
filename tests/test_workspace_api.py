"""The HTTP/lifespan boundary owns job startup, wire shapes and agent history.

Only the MCP/provider boundary and remote storage are substituted. The real
saved runner, API adapters, worker and conditional writes execute together.
"""
import asyncio

import httpx

from er.agent.models import AskResult, Citation, Evidence
from er.api import app as api
from er.config import load_config
from er.serving.store import MemoryStore


def test_saved_research_survives_api_restart_and_uses_existing_agent_path(monkeypatch):
    store = MemoryStore()
    cfg = load_config().model_copy(deep=True)
    cfg.workspace.poll_seconds = 0.01
    calls = []

    class Mcp:
        async def __aexit__(self, *args):
            pass

    async def connect():
        return Mcp()

    async def ask(client, cfg, question, entity_id, **options):
        calls.append({"question": question, "entity_id": entity_id, "history": options["history"], "trace": options["trace"]})
        await options["on_event"]({"type": "status", "message": "Looking up source evidence"})
        return AskResult(answer="Source-backed answer [1]", citations=[Citation(marker=1, evidence_id="ev1")],
                         evidence={"ev1": Evidence(evidence_id="ev1", source="gleif", fact_type="lookup", query_hash="h")})

    monkeypatch.setattr(api, "_cfg", lambda: cfg)
    monkeypatch.setattr(api, "get_store", lambda cfg: store)
    monkeypatch.setattr(api, "_connect_mcp_client", connect)
    monkeypatch.setattr(api, "agent_ask", ask)

    async def run():
        async with api.lifespan(api.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
                missing = await client.get("/api/investigations/does-not-exist")
                assert missing.status_code == 404
                payload = {"question": "Who owns Acme?", "request_id": "request-first", "entity_id": "LEI1"}
                first = await client.post("/api/investigations", json=payload)
                assert first.status_code == 202
                investigation_id = first.json()["id"]
                assert "lease_owner" not in first.json() and "revision" not in first.json()
                duplicate = await client.post("/api/investigations", json=payload)
                assert duplicate.json()["id"] == investigation_id
                conflict = await client.post("/api/investigations", json={**payload, "question": "Different question"})
                assert conflict.status_code == 409
                whitespace = await client.patch(f"/api/investigations/{investigation_id}", json={"title": "   "})
                assert whitespace.status_code == 400
                for turn in range(6):
                    for _ in range(200):
                        doc = (await client.get(f"/api/investigations/{investigation_id}")).json()
                        if doc["status"] not in ("queued", "running"):
                            break
                        await asyncio.sleep(0.01)
                    assert doc["status"] == "succeeded", doc.get("error")
                    assert len(doc["turns"]) == turn + 1
                    if turn < 5:
                        following = await client.post("/api/investigations", json={"question": f"Follow-up {turn}",
                            "request_id": f"request-next-{turn}", "investigation_id": investigation_id, "entity_id": "LEI1", "trace": turn == 4})
                        assert following.status_code == 202
        # A new API lifecycle reads the same server-owned conversation.
        async with api.lifespan(api.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://test") as client:
                restored = (await client.get(f"/api/investigations/{investigation_id}")).json()
                assert len(restored["turns"]) == 6
                assert restored["turns"][0]["result"]["evidence"]["ev1"]["source"] == "gleif"
                listing = (await client.get("/api/investigations")).json()["items"]
                assert listing[0]["id"] == investigation_id

    asyncio.run(run())
    assert len(calls) == 6  # the idempotent POST never schedules another run
    assert calls[1]["history"] == [{"role": "user", "content": "Who owns Acme?"},
                                    {"role": "assistant", "content": "Source-backed answer [1]"}]
    assert len(calls[-1]["history"]) == 8
    assert calls[-1]["entity_id"] == "LEI1"
    assert [call["trace"] for call in calls] == [False, False, False, False, False, True]
