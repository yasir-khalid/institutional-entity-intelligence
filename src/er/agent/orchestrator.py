"""OpenRouter tool-calling loop wired to the er.agent MCP server over the real
MCP protocol (an mcp.Client, not a direct Python import of er.agent.tools) -
the agent is deliberately just another MCP client, the same one Claude
Desktop or any other tool would use to talk to er.agent.mcp_server.

This module owns no entity-resolution logic and no Evidence-construction
logic - it only turns the server's tools into OpenAI-style function schemas,
drives the model through calling them, and enforces that the model's final
answer cites only evidence_ids that a tool call actually returned earlier in
the same conversation (never an invented one).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from mcp import Client, StdioServerParameters
from mcp_types import Tool as MCPTool

from er.config import REPO_ROOT, AppConfig

from .models import AskResult, Citation, Evidence

# One progress event, emitted as the tool-calling loop runs. The web API turns
# these into an SSE stream so the UI can show what is happening (which tool is
# being called, how many records came back) instead of a blank spinner. This
# is deliberately not a trace of model internals - it is the same
# business-readable language the Evidence layer uses.
ProgressEvent = dict[str, Any]
EventCallback = Callable[[ProgressEvent], Awaitable[None]]


def _tool_message(name: str, args: dict[str, Any]) -> str:
    if name == "search_entity":
        query = args.get("query", "")
        search_type = args.get("search_type", "name")
        return f'Searching {search_type} for \u201c{query}\u201d'
    if name == "get_entity_profile":
        return f"Reading the full profile for {args.get('entity_id', 'the entity')}"
    if name == "get_relationship_hierarchy":
        direction = args.get("direction", "all")
        return f"Tracing {direction} relationships around {args.get('entity_id', 'the entity')}"
    return f"Calling {name}"

SYSTEM_PROMPT = """You are an assistant answering questions about legal entities \
(companies, funds, managers) using GLEIF and SEC 13F data, via tools that query \
that data directly. Always call a tool to look up real data before stating a \
fact - never invent identifiers, dates, counts, or relationships.

Every tool result contains an `evidence` array of objects with an `evidence_id` \
field (looking like "ev_xxxxxxxxxx") - that exact string, copied verbatim, is \
the only thing you may ever put in a citation. Never cite an entity_id, a CIK, \
or anything else that merely looks like an identifier.

When you are ready to answer, call the `submit_answer` tool exactly once. Its \
`answer` text should use inline citation markers like [1], [2] next to every \
specific factual claim (a count, a date, a status, a relationship, an \
identifier). Its `citations` list must map each marker number to the exact \
evidence_id (copied from a tool result's `evidence` array) that supports that \
claim - never a made-up or guessed string. Do not state a numeric confidence \
score; if the data is incomplete or ambiguous, say so in the answer text \
instead."""

SUBMIT_ANSWER_TOOL: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_answer",
        "description": (
            "Submit your final answer with citations. Call this exactly once, "
            "after you have gathered enough evidence via the other tools."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {
                    "type": "string",
                    "description": "The final answer text, with inline [n] citation markers.",
                },
                "citations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "marker": {"type": "integer"},
                            "evidence_id": {"type": "string"},
                        },
                        "required": ["marker", "evidence_id"],
                    },
                },
            },
            "required": ["answer", "citations"],
        },
    },
}


def mcp_stdio_params(cfg: AppConfig) -> StdioServerParameters:
    command, *args = cfg.agent.mcp_server_command
    return StdioServerParameters(command=command, args=args, cwd=str(REPO_ROOT))


def _mcp_tool_to_openai_schema(tool: MCPTool) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.input_schema,
        },
    }


async def _call_openrouter(
    cfg: AppConfig,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    tool_choice: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": cfg.agent.openrouter_model,
        "messages": messages,
        "tools": tools,
    }
    if tool_choice is not None:
        payload["tool_choice"] = tool_choice
    async with httpx.AsyncClient(timeout=90) as http:
        resp = await http.post(
            f"{cfg.agent.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.openrouter_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def _emit(on_event: EventCallback | None, event: ProgressEvent) -> None:
    if on_event is not None:
        await on_event(event)


async def ask(
    client: Client,
    cfg: AppConfig,
    question: str,
    entity_id: str | None = None,
    on_event: EventCallback | None = None,
) -> AskResult:
    """Run the tool-calling loop for one question. `client` must already be
    connected (entered as an async context manager) to a running
    er.agent.mcp_server instance. If `on_event` is given it is awaited with a
    progress event before/after every tool call, so a streaming caller can
    render what the agent is doing."""
    tools_result = await client.list_tools()
    tools_schema = [_mcp_tool_to_openai_schema(t) for t in tools_result.tools] + [SUBMIT_ANSWER_TOOL]
    force_submit_answer = {"type": "function", "function": {"name": "submit_answer"}}
    # The model is not allowed to answer from the system prompt alone. A
    # generic question such as "what data sources can you access?" previously
    # sometimes skipped MCP entirely, then called submit_answer with zero
    # citations. Force a real lookup before it can submit an answer.
    force_search_entity = {"type": "function", "function": {"name": "search_entity"}}

    user_content = question
    if entity_id:
        user_content = f"(The user is currently viewing entity_id={entity_id}.)\n{question}"

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    evidence_store: dict[str, Evidence] = {}
    nudged_to_submit = False
    must_gather_evidence = True

    await _emit(on_event, {"type": "status", "message": "Planning the research…"})

    for _ in range(cfg.agent.max_tool_turns):
        # DeepSeek doesn't reliably choose to call submit_answer on its own -
        # it sometimes just answers in plain text with [n] markers already in
        # it. Rather than trust that (citations would come back empty), force
        # the *next* call to go through submit_answer once that happens, so
        # citations are always structured rather than scraped from text.
        response = await _call_openrouter(
            cfg,
            messages,
            tools_schema,
            tool_choice=force_search_entity if must_gather_evidence else force_submit_answer if nudged_to_submit else None,
        )
        message = response["choices"][0]["message"]
        tool_calls = message.get("tool_calls") or []
        messages.append(message)

        if not tool_calls:
            if must_gather_evidence:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Before answering, use search_entity to look up relevant records. "
                            "Your answer must be grounded in a tool result from this conversation."
                        ),
                    }
                )
                continue
            if nudged_to_submit:
                # Already forced it once and it still didn't - return the
                # free text uncited rather than looping forever.
                return AskResult(answer=message.get("content") or "", citations=[], evidence=evidence_store)
            messages.append(
                {"role": "user", "content": "Call the submit_answer tool now with your final answer and citations."}
            )
            nudged_to_submit = True
            continue

        final_result: AskResult | None = None
        for call in tool_calls:
            name = call["function"]["name"]
            args = json.loads(call["function"]["arguments"] or "{}")

            if name == "submit_answer":
                await _emit(on_event, {"type": "status", "message": "Composing the answer…"})
                citations = [Citation(**c) for c in args.get("citations", [])]
                valid_citations = [c for c in citations if c.evidence_id in evidence_store]
                if must_gather_evidence or not valid_citations:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": (
                                "Submission rejected. First call an MCP data tool, then cite at least one "
                                "evidence_id that tool returned in your final answer."
                            ),
                        }
                    )
                    must_gather_evidence = not bool(evidence_store)
                    nudged_to_submit = bool(evidence_store)
                    continue
                final_result = AskResult(
                    answer=args.get("answer", ""),
                    # Only accept citations to evidence this conversation actually produced -
                    # this is the enforcement point for "never an invented evidence_id."
                    citations=valid_citations,
                    evidence=evidence_store,
                )
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": "submitted"})
                continue

            await _emit(on_event, {"type": "tool_call", "tool": name, "message": _tool_message(name, args)})
            result = await client.call_tool(name, args)
            payload = result.structured_content or {}
            for raw_evidence in payload.get("evidence", []):
                ev = Evidence.model_validate(raw_evidence)
                evidence_store[ev.evidence_id] = ev
            if evidence_store:
                must_gather_evidence = False
            new_evidence = payload.get("evidence", [])
            await _emit(
                on_event,
                {
                    "type": "tool_result",
                    "tool": name,
                    "message": _tool_message(name, args),
                    "source": new_evidence[0].get("source") if new_evidence else None,
                    "count": new_evidence[0].get("result_count") if new_evidence else None,
                    "evidence_ids": [e["evidence_id"] for e in new_evidence],
                },
            )
            # The model must see the real evidence_id strings to cite them -
            # sending only `data` back (as an earlier version of this did)
            # left it nothing to cite but a guess (e.g. the entity_id itself),
            # which the evidence_store membership check then correctly, but
            # uselessly, rejected as an invented citation.
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(
                        {"data": payload.get("data", {}), "evidence": payload.get("evidence", [])}
                    ),
                }
            )

        if final_result is not None:
            return final_result

    raise RuntimeError(f"agent did not produce a final answer within {cfg.agent.max_tool_turns} tool-call turns")
