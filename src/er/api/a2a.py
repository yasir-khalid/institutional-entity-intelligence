"""A2A (Agent2Agent protocol) binding for the research agent.

Same rule as the rest of er.api: this is protocol wiring only. One A2A
message becomes one er.agent.orchestrator.ask() run, through the same `ask`
callable /api/ask uses, so an agent talking A2A gets the identical answer,
citations and Jev verification the web UI does. The answer artifact carries a
markdown text part plus a data part with the evidence, facts, derivations and
verification behind it, so a calling agent keeps the provenance instead of
just the prose.

Earlier turns come from completed tasks in the same A2A contextId - the task
store is the conversation memory. It is in-memory, so a restart forgets
conversations; nothing here is a system of record.
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable
from typing import Any

from a2a.helpers.proto_helpers import get_message_text, new_data_part, new_task_from_user_message, new_text_part
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import add_a2a_routes_to_fastapi, create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    HTTPAuthSecurityScheme,
    ListTasksRequest,
    Role,
    SecurityRequirement,
    SecurityScheme,
    TaskState,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from google.protobuf.json_format import MessageToDict

from er.agent.models import AskResult

RPC_PATH = "/a2a"
ANSWER_ARTIFACT = "answer"
# AskRequest.history holds at most 8 turns: 4 question/answer pairs.
MAX_HISTORY_TASKS = 4
# Progress events worth relaying as `working` updates. tool_result repeats
# its tool_call's message and trace spans are web-only developer detail.
RELAYED_EVENTS = {"status", "tool_call", "verification"}

AskFn = Callable[..., Awaitable[AskResult]]


def build_agent_card(public_url: str, *, require_auth: bool) -> AgentCard:
    card = AgentCard(
        name="Institutional Entity Intelligence",
        description=(
            "Answers questions about legal entities and institutions from public records: GLEIF "
            "identity and corporate hierarchy, SEC 13F reported holdings, 13D/G beneficial owners, "
            "N-PORT funds, Form ADV, FFIEC bank control and Companies House. Every figure in an "
            "answer is cited to a source record and the answer is independently verified."
        ),
        version="0.1.0",
        provider=AgentProvider(organization="Institutional Entity Intelligence", url=public_url),
        supported_interfaces=[
            AgentInterface(url=public_url.rstrip("/") + RPC_PATH, protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text/plain"],
        default_output_modes=["text/markdown", "application/json"],
        skills=[
            AgentSkill(
                id="entity_research",
                name="Entity research",
                description=(
                    "Resolve an institution by name, LEI or CUSIP and answer questions about its "
                    "identity, parents and subsidiaries, ownership, fund structure and latest "
                    "reported 13F holdings. Put an LEI in message metadata as `entity_id` to scope "
                    "the question to one entity."
                ),
                tags=["entity resolution", "LEI", "corporate hierarchy", "SEC 13F", "beneficial ownership"],
                examples=[
                    "Who is the ultimate parent of BlackRock Fund Advisors?",
                    "What were Vanguard's largest 13F positions last quarter?",
                    "Who reports beneficial ownership of Apple Inc.?",
                ],
            )
        ],
    )
    if require_auth:
        card.security_schemes["bearer"].CopyFrom(
            SecurityScheme(http_auth_security_scheme=HTTPAuthSecurityScheme(scheme="Bearer"))
        )
        card.security_requirements.append(SecurityRequirement(schemes={"bearer": {}}))
    return card


def answer_data(result: AskResult) -> dict[str, Any]:
    # Same exclusion as er.api.app's VerificationOut: token usage and cost are
    # operator telemetry, not part of the answer.
    return result.model_dump(mode="json", exclude={"answer": True, "verification": {"usage"}})


class ResearchAgentExecutor(AgentExecutor):
    def __init__(self, ask: AskFn, task_store: TaskStore) -> None:
        self._ask = ask
        self._task_store = task_store

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        if context.current_task is None:
            await event_queue.enqueue_event(new_task_from_user_message(context.message))
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)

        question = context.get_user_input().strip()
        if not question:
            await updater.reject(updater.new_agent_message([new_text_part("Send the question as a text part.")]))
            return
        metadata = MessageToDict(context.message.metadata)
        history = await self._history(context)

        async def on_event(event: dict) -> None:
            if event.get("type") in RELAYED_EVENTS and event.get("message"):
                message = updater.new_agent_message([new_text_part(event["message"])])
                await updater.update_status(TaskState.TASK_STATE_WORKING, message)

        await updater.start_work()
        try:
            result = await self._ask(
                question=question, entity_id=metadata.get("entity_id"), history=history, on_event=on_event
            )
        except Exception as exc:
            await updater.failed(updater.new_agent_message([new_text_part(str(exc) or type(exc).__name__)]))
            return

        await updater.add_artifact(
            [new_text_part(result.answer, media_type="text/markdown"), new_data_part(answer_data(result))],
            name=ANSWER_ARTIFACT,
        )
        await updater.complete()

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        await TaskUpdater(event_queue, context.task_id, context.context_id).cancel()

    async def _history(self, context: RequestContext) -> list[dict[str, str]]:
        listed = await self._task_store.list(
            ListTasksRequest(
                context_id=context.context_id,
                status=TaskState.TASK_STATE_COMPLETED,
                include_artifacts=True,
                page_size=MAX_HISTORY_TASKS,
            ),
            context.call_context,
        )
        turns: list[dict[str, str]] = []
        for task in reversed(listed.tasks):  # listed newest first
            question = next((get_message_text(m) for m in task.history if m.role == Role.ROLE_USER), "")
            answer = next(
                (p.text for a in task.artifacts if a.name == ANSWER_ARTIFACT for p in a.parts if p.text), ""
            )
            if question and answer:
                turns += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
        return turns


def mount_a2a(app: FastAPI, ask: AskFn, public_url: str, api_key: str | None = None) -> None:
    """Serve the agent card at /.well-known/agent-card.json and JSON-RPC at
    /a2a. With `api_key`, /a2a requires `Authorization: Bearer <api_key>`;
    the card stays public so a client can discover that requirement."""
    task_store = InMemoryTaskStore()
    card = build_agent_card(public_url, require_auth=api_key is not None)
    handler = DefaultRequestHandler(
        agent_executor=ResearchAgentExecutor(ask, task_store), task_store=task_store, agent_card=card
    )
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=RPC_PATH),
    )
    if api_key is None:
        return

    expected = f"Bearer {api_key}".encode()

    @app.middleware("http")
    async def require_bearer(request: Request, call_next):
        if request.url.path == RPC_PATH:
            supplied = request.headers.get("authorization", "").encode()
            if not hmac.compare_digest(supplied, expected):
                return JSONResponse(status_code=401, content={"detail": "Missing or invalid bearer token"})
        return await call_next(request)
