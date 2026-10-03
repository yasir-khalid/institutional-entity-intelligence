"""OpenRouter tool-calling loop wired to the er.agent MCP server over the real
MCP protocol (an mcp.Client, not a direct Python import of er.agent.tools) -
the agent is deliberately just another MCP client, the same one Claude
Desktop or any other tool would use to talk to er.agent.mcp_server.

This module owns no entity-resolution logic and no Evidence-construction
logic - it only turns the server's tools into OpenAI-style function schemas,
drives the model through calling them, enforces that the model's final answer
cites only evidence_ids that a tool call actually returned earlier in the same
conversation (never an invented one), and then hands the finished answer plus
the full tool transcript to er.agent.verifier for an independent check (see
that module for why a decision model rather than a second chat model).
"""

from __future__ import annotations

import asyncio
import itertools
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from mcp import Client, StdioServerParameters
from mcp_types import Tool as MCPTool

from er.config import REPO_ROOT, AppConfig

from .facts import normalise_placeholders, referenced_fact_ids, render_answer, same_source_value
from .models import AskResult, Citation, Derivation, Evidence, Fact
from .payloads import fit
from .retry import error_message, is_transient, timeout
from .trace import TraceSpan, llm_span, submit_span, tool_span, verifier_span
from .verifier import verify_answer

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
    if name == "search_adv_documents":
        return f"Searching Form ADV brochures for “{args.get('query', '')}”"
    if name == "get_position_history":
        return f"Reading 13F position history for CUSIP {args.get('cusip', '')}"
    if name == "get_entity_connections":
        return f"Reading ownership and control records for {args.get('entity_id', 'the entity')}"
    if name == "get_beneficial_owners":
        return "Reading Schedule 13D/G beneficial owners"
    return f"Calling {name}"

SYSTEM_PROMPT = """You are an assistant answering questions about legal entities \
(companies, funds, managers) using GLEIF and SEC filing data, via tools that query \
that data directly. Always call a tool to look up real data before stating a \
fact - never invent identifiers, dates, counts, or relationships. What an \
adviser says about itself (fees, strategy, conflicts) comes from its Form ADV \
brochure text, through search_adv_documents.

Every tool result contains an `evidence` array of objects with an `evidence_id` \
field (looking like "ev_xxxxxxxxxx") - that exact string, copied verbatim, is \
the only thing you may ever put in a citation. Never cite an entity_id, a CIK, \
or anything else that merely looks like an identifier.

Prior user and assistant turns may be supplied as conversational context. They
are not evidence for the current answer: resolve follow-ups with current tool
calls and cite only evidence returned during this run.

Tool results may also contain a `facts` array. To state a number, date, or other \
digit-only value from a fact, copy its placeholder exactly as `{{f:fact_id}}`; \
never type the literal value yourself. The submission gate replaces placeholders \
with their values after checking their source evidence was cited. Standalone \
numeric literals are rejected, except an identifier or date copied whole from a \
cited fact or from the question. Placeholders render with their unit ($1,234 or \
5.2%), so write the placeholder alone, without your own $ or %. Never compute a number yourself (a change, a \
percentage, a total): use a derived fact a tool returned, which records the \
formula and the facts it was computed from.

"Owner", "holder" and "parent" are different relationships here. A 13F holding \
means the manager reported investment discretion over the position; an N-PORT \
holding is a position in a registered fund's own portfolio; a Schedule \
13D/G owner reported beneficial ownership of more than 5% of a class; a UK \
person with significant control is a Companies House PSC filing; a GLEIF \
parent is an accounting-consolidation parent. Name the one the evidence shows.

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
    async with httpx.AsyncClient(timeout=timeout(90, cfg.agent.openrouter_connect_timeout_seconds)) as http:
        resp = await http.post(
            f"{cfg.agent.openrouter_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.openrouter_api_key}"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def _backoff(seconds: float) -> None:
    # Its own function so tests can skip the wait without patching asyncio.
    await asyncio.sleep(seconds)


class ModelUnavailableError(RuntimeError):
    """The model provider kept failing transiently until retries ran out.

    Its message is what the user sees (the API streams it verbatim), so it
    names the provider and says it is probably temporary - unlike the raw
    httpx message it replaces, "Server disconnected without sending a
    response.", which doesn't say which server. The raw error stays on
    `__cause__` and in the developer trace."""


def _describe(exc: BaseException) -> str:
    """One line a developer can act on. An HTTP error says which status and
    which endpoint; anything else says its type, since a bare message like
    "timed out" is useless without knowing what timed out."""
    if isinstance(exc, httpx.HTTPStatusError):
        base = f"HTTP {exc.response.status_code} from {exc.request.url.path}"
        reason = error_message(exc.response)
        return f"{base}: {reason}" if reason else base
    message = str(exc).strip()
    return f"{type(exc).__name__}: {message}" if message else type(exc).__name__


def _model_view(data: Any, max_chars: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """What the model is sent in place of a tool's `data`, and - when that
    differs from the real thing - a note saying how.

    The note is not decoration. A trimmed subsidiary list reads exactly like a
    short one, so without it a model can truthfully summarise what it was
    shown and still be wrong ("it has 12 subsidiaries"). The evidence records'
    `result_count` is never trimmed, so the true count is always available.
    """
    size = len(json.dumps(data, default=str))
    shown, trimmed = fit(data, max_chars)
    if not trimmed:
        return {"data": data}, None
    note = {
        "original_chars": size,
        "sent_chars": len(json.dumps(shown, default=str)) if shown is not None else 0,
    }
    if shown is None:
        note["note"] = (
            "This result was too large to include at all. Rely on the evidence records' result_count, "
            "and make a narrower call (e.g. direction='parents', or a smaller depth) for detail."
        )
        return {"data": None, "data_truncated": note}, note
    note["note"] = (
        "Long lists in this result were trimmed to fit; each trimmed list ends with a marker "
        "saying how many items were left out. Do not present a trimmed list as complete, and take "
        "counts from the evidence records' result_count, not from the list length."
    )
    return {"data": shown, "data_truncated": note}, note


def _tool_error(result: Any) -> str | None:
    """An MCP tool can fail without raising - the server returns is_error with
    the message as text content. The loop carries on either way (the model
    sees the empty result and can recover), but the trace must not show that
    as a clean call."""
    if not getattr(result, "is_error", False):
        return None
    texts = [getattr(item, "text", "") for item in getattr(result, "content", None) or []]
    return " ".join(text for text in texts if text) or "Tool returned an error with no message"


async def _emit(on_event: EventCallback | None, event: ProgressEvent) -> None:
    if on_event is not None:
        await on_event(event)


def _used_facts(
    fact_ids: set[str], fact_store: dict[str, Fact], derivation_store: dict[str, Derivation]
) -> dict[str, Any]:
    """The facts an answer used plus, for any derived one, its derivation and
    input facts, walked back to source facts."""
    facts: dict[str, Fact] = {}
    derivations: dict[str, Derivation] = {}
    pending = list(fact_ids)
    while pending:
        fact_id = pending.pop()
        if fact_id in facts or fact_id not in fact_store:
            continue
        facts[fact_id] = fact_store[fact_id]
        if fact_id in derivation_store:
            derivations[fact_id] = derivation_store[fact_id]
            pending.extend(derivation_store[fact_id].inputs)
    return {"facts": dict(sorted(facts.items())), "derivations": derivations}


async def _recheck_facts(
    client: Client,
    answer: str,
    fact_store: dict[str, Fact],
    tool_transcript: list[dict[str, Any]],
) -> str | None:
    requested = referenced_fact_ids(answer)
    if not requested:
        return None

    origins: dict[str, tuple[str, dict[str, Any]]] = {}
    for call in tool_transcript:
        for raw_fact in call.get("facts", []):
            fact_id = raw_fact.get("fact_id")
            if fact_id in requested:
                origins[fact_id] = (call["tool"], call["arguments"])

    missing_origins = requested - origins.keys()
    if missing_origins:
        return f"facts have no retrieval address: {', '.join(sorted(missing_origins))}"

    groups: dict[tuple[str, str], set[str]] = {}
    for fact_id, (tool, arguments) in origins.items():
        key = (tool, json.dumps(arguments, sort_keys=True, separators=(",", ":")))
        groups.setdefault(key, set()).add(fact_id)

    for (tool, encoded_arguments), fact_ids in groups.items():
        result = await client.call_tool(tool, json.loads(encoded_arguments))
        if _tool_error(result):
            return f"source re-check failed for {tool}"
        payload = result.structured_content or {}
        refreshed = {
            fact.fact_id: fact
            for fact in (Fact.model_validate(raw) for raw in payload.get("facts", []))
        }
        for fact_id in fact_ids:
            if fact_id not in refreshed:
                return f"source address no longer resolves: {fact_id}"
            if not same_source_value(fact_store[fact_id], refreshed[fact_id]):
                return f"source value changed during answer generation: {fact_id}"
    return None


async def ask(
    client: Client,
    cfg: AppConfig,
    question: str,
    entity_id: str | None = None,
    history: list[dict[str, str]] | None = None,
    on_event: EventCallback | None = None,
    trace: bool = False,
) -> AskResult:
    """Run the tool-calling loop for one question. `client` must already be
    connected (entered as an async context manager) to a running
    er.agent.mcp_server instance. If `on_event` is given it is awaited with a
    progress event before/after every tool call, so a streaming caller can
    render what the agent is doing.

    Every return path goes through `_finalise`, so an answer can never reach a
    caller unverified-but-unmarked: it either carries a verification verdict
    or carries an explicit "not checked".

    With `trace=True`, `on_event` additionally receives a `{"type": "trace",
    "span": ...}` event as each LLM call, tool call, submission and
    verification completes - see er.agent.trace. Spans are only *built* when
    tracing is on, so an untraced run pays nothing for them (a relationship
    tree's trace preview costs a full serialisation of up to ~1.2M chars)."""
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

    prior_messages = [
        {"role": turn["role"], "content": turn["content"]}
        for turn in (history or [])[-8:]
        if turn.get("role") in {"user", "assistant"} and turn.get("content")
    ]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *prior_messages,
        {"role": "user", "content": user_content},
    ]

    evidence_store: dict[str, Evidence] = {}
    fact_store: dict[str, Fact] = {}
    derivation_store: dict[str, Derivation] = {}
    # What the verifier judges the answer against: every tool call made, with
    # its arguments and what came back. Kept separately from `messages`
    # because that list also carries the model's own prose, which would let a
    # confident-sounding assistant turn count as its own supporting record.
    tool_transcript: list[dict[str, Any]] = []
    nudged_to_submit = False
    must_gather_evidence = True

    run_started = time.monotonic()
    span_ids = itertools.count(1)

    def _ms(at: float) -> int:
        return int((at - run_started) * 1000)

    # The LLM call currently being acted on. Tool calls and submissions it
    # requested record it as `requested_by` - provenance only; the trace itself
    # is a flat sequence of steps under the run.
    llm_span_id: str | None = None

    async def _trace(build: Callable[[str], TraceSpan], requested_by: str | None = None) -> str | None:
        # Takes a builder rather than a span so nothing is serialised unless
        # someone is actually listening. Returns the span's id so an LLM call
        # can be recorded as what requested the steps after it.
        if not trace:
            return None
        span = build(f"s{next(span_ids)}")
        span.requested_by = requested_by
        await _emit(on_event, {"type": "trace", "span": span.model_dump()})
        return span.id

    async def _finalise(result: AskResult) -> AskResult:
        await _emit(on_event, {"type": "status", "message": "Verifying the answer against the records\u2026"})
        started = time.monotonic()
        verification = await verify_answer(cfg, question, result, tool_transcript)
        finished = time.monotonic()
        await _trace(
            lambda span_id: verifier_span(span_id, _ms(started), int((finished - started) * 1000), verification)
        )
        result.verification = verification
        await _emit(
            on_event,
            {
                "type": "verification",
                "status": verification.status,
                "message": verification.headline,
                "detail": verification.detail,
            },
        )
        return result

    await _emit(on_event, {"type": "status", "message": "Planning the research…"})

    for turn in range(1, cfg.agent.max_tool_turns + 2):
        # The extra turn exists only to resubmit an answer the gate rejected on
        # the last turn - the budget caps research, not fixing a citation.
        if turn > cfg.agent.max_tool_turns and not nudged_to_submit:
            break
        # DeepSeek doesn't reliably choose to call submit_answer on its own -
        # it sometimes just answers in plain text with [n] markers already in
        # it. Rather than trust that (citations would come back empty), force
        # the *next* call to go through submit_answer once that happens, so
        # citations are always structured rather than scraped from text.
        # A model still exploring on its last turn would otherwise run out the
        # budget with evidence in hand and no answer.
        out_of_turns = turn >= cfg.agent.max_tool_turns and bool(evidence_store)
        if must_gather_evidence:
            tool_choice = force_search_entity
        elif nudged_to_submit or out_of_turns:
            tool_choice = force_submit_answer
        else:
            tool_choice = None
        attempts = cfg.agent.openrouter_retries + 1
        for attempt in range(1, attempts + 1):
            started = time.monotonic()
            try:
                response = await _call_openrouter(cfg, messages, tools_schema, tool_choice=tool_choice)
                break
            except Exception as exc:
                failed = time.monotonic()
                retrying = is_transient(exc) and attempt < attempts
                error = _describe(exc) + (f" \u00b7 retrying (attempt {attempt} of {attempts})" if retrying else "")
                await _trace(
                    lambda span_id: llm_span(
                        span_id, turn, cfg.agent.openrouter_model, tool_choice,
                        _ms(started), int((failed - started) * 1000), error=error,
                    )
                )
                if retrying:
                    await _emit(
                        on_event,
                        {"type": "status", "message": "The model provider dropped the request \u2014 retrying\u2026"},
                    )
                    await _backoff(cfg.agent.openrouter_retry_backoff_seconds * 2 ** (attempt - 1))
                    continue
                if is_transient(exc):
                    raise ModelUnavailableError(
                        f"The model provider (OpenRouter) failed {attempts} times in a row "
                        f"({_describe(exc)}). This is usually temporary \u2014 try again in a moment."
                    ) from exc
                raise
        finished = time.monotonic()
        llm_span_id = await _trace(
            lambda span_id: llm_span(
                span_id, turn, cfg.agent.openrouter_model, tool_choice,
                _ms(started), int((finished - started) * 1000), response=response,
            )
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
                rendered, error = render_answer(message.get("content") or "", fact_store, set(), question)
                answer = rendered if error is None else "I couldn't produce a source-addressed answer."
                return await _finalise(
                    AskResult(answer=answer, citations=[], evidence=evidence_store)
                )
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
                args["answer"] = normalise_placeholders(args.get("answer", ""), fact_store)
                citations = [Citation(**c) for c in args.get("citations", [])]
                valid_citations = [c for c in citations if c.evidence_id in evidence_store]
                if must_gather_evidence or not valid_citations:
                    reason = (
                        "no data tool had been called yet"
                        if must_gather_evidence
                        else "no citation matched evidence returned in this conversation"
                    )
                    await _trace(
                        lambda span_id: submit_span(
                            span_id, _ms(time.monotonic()), args, list(evidence_store), accepted=False, reason=reason
                        ),
                        requested_by=llm_span_id,
                    )
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
                rendered_answer, fact_error = render_answer(
                    args.get("answer", ""),
                    fact_store,
                    {citation.evidence_id for citation in valid_citations},
                    question,
                )
                if fact_error:
                    await _trace(
                        lambda span_id: submit_span(
                            span_id,
                            _ms(time.monotonic()),
                            args,
                            list(evidence_store),
                            accepted=False,
                            reason=fact_error,
                        ),
                        requested_by=llm_span_id,
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": f"Submission rejected. {fact_error}",
                        }
                    )
                    nudged_to_submit = True
                    continue
                await _emit(on_event, {"type": "status", "message": "Re-checking cited source addresses…"})
                recheck_error = await _recheck_facts(
                    client,
                    args.get("answer", ""),
                    fact_store,
                    tool_transcript,
                )
                if recheck_error:
                    await _trace(
                        lambda span_id: submit_span(
                            span_id,
                            _ms(time.monotonic()),
                            args,
                            list(evidence_store),
                            accepted=False,
                            reason=recheck_error,
                        ),
                        requested_by=llm_span_id,
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call["id"],
                            "content": f"Submission rejected. {recheck_error}",
                        }
                    )
                    nudged_to_submit = True
                    continue
                await _trace(
                    lambda span_id: submit_span(span_id, _ms(time.monotonic()), args, list(evidence_store), accepted=True),
                    requested_by=llm_span_id,
                )
                final_result = AskResult(
                    answer=rendered_answer or "",
                    # Only accept citations to evidence this conversation actually produced -
                    # this is the enforcement point for "never an invented evidence_id."
                    citations=valid_citations,
                    evidence=evidence_store,
                    **_used_facts(referenced_fact_ids(args.get("answer", "")), fact_store, derivation_store),
                )
                messages.append({"role": "tool", "tool_call_id": call["id"], "content": "submitted"})
                continue

            await _emit(on_event, {"type": "tool_call", "tool": name, "message": _tool_message(name, args)})
            started = time.monotonic()
            try:
                result = await client.call_tool(name, args)
            except Exception as exc:
                failed = time.monotonic()
                await _trace(
                    lambda span_id: tool_span(
                        span_id, name, args, _ms(started), int((failed - started) * 1000), error=_describe(exc)
                    ),
                    requested_by=llm_span_id,
                )
                raise
            finished = time.monotonic()
            payload = result.structured_content or {}
            tool_error = _tool_error(result)
            model_data, trimmed = _model_view(payload.get("data", {}), cfg.agent.max_tool_result_chars)
            await _trace(
                lambda span_id: tool_span(
                    span_id, name, args, _ms(started), int((finished - started) * 1000),
                    payload=payload, error=tool_error, sent_to_model=trimmed,
                ),
                requested_by=llm_span_id,
            )
            for raw_evidence in payload.get("evidence", []):
                ev = Evidence.model_validate(raw_evidence)
                evidence_store[ev.evidence_id] = ev
            for raw_fact in payload.get("facts", []):
                fact = Fact.model_validate(raw_fact)
                fact_store[fact.fact_id] = fact
            for raw_derivation in payload.get("derivations", []):
                derivation = Derivation.model_validate(raw_derivation)
                derivation_store[derivation.fact_id] = derivation
            if evidence_store:
                must_gather_evidence = False
            new_evidence = payload.get("evidence", [])
            tool_transcript.append(
                {
                    "tool": name,
                    "arguments": args,
                    "result": payload.get("data", {}),
                    "evidence": new_evidence,
                    "facts": payload.get("facts", []),
                }
            )
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
                    # `data` may be a trimmed view (see _model_view); evidence
                    # never is - it is small, and the model needs every
                    # evidence_id to cite.
                    "content": json.dumps(
                        {
                            **model_data,
                            "evidence": payload.get("evidence", []),
                            "facts": payload.get("facts", []),
                        },
                        default=str,
                    ),
                }
            )

        if final_result is not None:
            return await _finalise(final_result)

    raise RuntimeError(f"agent did not produce a final answer within {cfg.agent.max_tool_turns} tool-call turns")
