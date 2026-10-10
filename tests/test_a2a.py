"""The A2A binding (er.api.a2a), driven through the a2a-sdk client over HTTP
so the agent card, JSON-RPC routing and task store are the real ones. Only
er.agent.orchestrator.ask is replaced - no model or MCP server is involved."""

import asyncio

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers.proto_helpers import get_data_parts, new_text_message
from a2a.types import Role, SendMessageRequest, TaskState
from fastapi import FastAPI

from er.agent.models import AskResult, Citation, Evidence
from er.api.a2a import mount_a2a

BASE = "http://agent.test"


def _app(calls: list[dict], api_key: str | None = None) -> FastAPI:
    async def fake_ask(*, question, entity_id, history, on_event):
        calls.append({"question": question, "entity_id": entity_id, "history": history})
        await on_event({"type": "tool_call", "message": "Searching entities"})
        return AskResult(
            answer=f"Answer to: {question}",
            citations=[Citation(marker=1, evidence_id="ev1")],
            evidence={"ev1": Evidence(evidence_id="ev1", source="gleif", fact_type="lookup", query_hash="h")},
        )

    app = FastAPI()
    mount_a2a(app, fake_ask, BASE, api_key)
    return app


async def _send(client, text: str, context_id: str | None = None, metadata: dict | None = None):
    message = new_text_message(text, context_id=context_id, role=Role.ROLE_USER)
    if metadata:
        message.metadata.update(metadata)
    events = [e async for e in client.send_message(SendMessageRequest(message=message))]
    return next(e.task for e in reversed(events) if e.HasField("task"))


def test_follow_up_in_same_context_carries_the_earlier_turn():
    calls: list[dict] = []

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(calls)), base_url=BASE) as http:
            client = await create_client(BASE, ClientConfig(httpx_client=http, streaming=False))
            first = await _send(client, "Who owns Acme?", metadata={"entity_id": "LEI_ACME"})
            second = await _send(client, "And its parent?", context_id=first.context_id)
            return first, second

    first, second = asyncio.run(run())

    assert first.status.state == TaskState.TASK_STATE_COMPLETED
    answer = first.artifacts[0]
    assert answer.parts[0].text == "Answer to: Who owns Acme?"
    assert get_data_parts(answer.parts)[0]["evidence"]["ev1"]["source"] == "gleif"
    assert calls[0]["entity_id"] == "LEI_ACME"
    assert calls[1]["history"] == [
        {"role": "user", "content": "Who owns Acme?"},
        {"role": "assistant", "content": "Answer to: Who owns Acme?"},
    ]
    assert second.status.state == TaskState.TASK_STATE_COMPLETED


def test_rpc_requires_bearer_token_but_card_stays_public():
    calls: list[dict] = []

    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_app(calls, "s3cret")), base_url=BASE) as http:
            card = await http.get("/.well-known/agent-card.json")
            rpc = await http.post("/a2a", json={"jsonrpc": "2.0", "id": 1, "method": "SendMessage", "params": {}})
            return card, rpc

    card, rpc = asyncio.run(run())

    assert card.status_code == 200
    assert "bearer" in card.json()["securitySchemes"]
    assert rpc.status_code == 401
    assert calls == []
