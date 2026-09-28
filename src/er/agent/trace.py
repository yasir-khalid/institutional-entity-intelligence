"""Developer trace for one er.agent run: every model turn, every MCP tool
call, every rejected submission, and the verifier - with timings, token
usage, arguments and payloads.

This is deliberately separate from the progress events the orchestrator
already emits. Those are the business-readable feed ("Searching name for
'Point72'") that the product shows every user; this is the raw material a
developer needs when an answer looks wrong - what the model was forced to
call, what it actually asked for, what came back, what was thrown away and
why. It is opt-in (`ask(..., trace=True)`), so a caller that doesn't ask pays
nothing for it.

Spans are built here, not in the orchestrator, so the orchestrator only
decides *when* a span happened; *what* a span says lives in one place.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel

from .models import Verification
from .payloads import fit

# A trace is streamed to a browser, so a tool result has to fit in something
# it can render. 20k chars keeps a whole entity profile (~2k) and a search
# (~3k) intact, while a 1.2M relationship tree arrives shape-preserved with
# its tail elided and marked.
MAX_PAYLOAD_CHARS = 20_000

SpanKind = Literal["llm", "tool", "submit", "verifier"]
SpanStatus = Literal["ok", "error", "rejected"]


class TraceSpan(BaseModel):
    """One step of a run. `start_ms` is relative to the start of the run, so a
    consumer can lay spans out as a waterfall without clock arithmetic.

    `parent_id` makes the run a tree: a tool call or submission points at the
    model turn that requested it; model turns and the verifier have no parent
    (they sit directly under the run)."""

    id: str
    parent_id: str | None = None
    kind: SpanKind
    name: str
    start_ms: int
    duration_ms: int
    status: SpanStatus = "ok"
    summary: str
    detail: dict[str, Any] = {}


def _payload(value: Any) -> dict[str, Any]:
    """A tool payload as the trace carries it: shrunk to fit, with the
    original size and whether anything was dropped, so a preview can never be
    mistaken for the whole result."""
    size = len(json.dumps(value, default=str))
    shown, truncated = fit(value, MAX_PAYLOAD_CHARS)
    return {
        "value": shown,
        "chars": size,
        "truncated": truncated,
    }


def _forced_tool(tool_choice: dict[str, Any] | None) -> str | None:
    if not tool_choice:
        return None
    return (tool_choice.get("function") or {}).get("name")


def llm_span(
    span_id: str,
    turn: int,
    requested_model: str,
    tool_choice: dict[str, Any] | None,
    start_ms: int,
    duration_ms: int,
    response: dict[str, Any] | None = None,
    error: str | None = None,
) -> TraceSpan:
    forced = _forced_tool(tool_choice)
    if error is not None:
        return TraceSpan(
            id=span_id,
            kind="llm",
            name=requested_model,
            start_ms=start_ms,
            duration_ms=duration_ms,
            status="error",
            summary=f"Turn {turn} failed: {error}",
            detail={"turn": turn, "forced_tool": forced, "error": error},
        )

    response = response or {}
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    requested = [
        {"name": (call.get("function") or {}).get("name"), "arguments": _arguments(call)}
        for call in message.get("tool_calls") or []
    ]
    usage = response.get("usage") or {}
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")

    if requested:
        summary = "Requested " + ", ".join(call["name"] or "?" for call in requested)
    elif message.get("content"):
        summary = "Replied in plain text, no tool call"
    else:
        summary = "Empty response"
    if forced:
        summary += f" (forced: {forced})"

    return TraceSpan(
        id=span_id,
        kind="llm",
        name=response.get("model") or requested_model,
        start_ms=start_ms,
        duration_ms=duration_ms,
        summary=summary,
        detail={
            "turn": turn,
            "forced_tool": forced,
            "finish_reason": choice.get("finish_reason"),
            "provider": response.get("provider"),
            "generation_id": response.get("id"),
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
                "cost": usage.get("cost"),
            },
            "content": message.get("content"),
            "tool_calls": requested,
        },
    )


def _arguments(call: dict[str, Any]) -> Any:
    raw = (call.get("function") or {}).get("arguments") or "{}"
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        # Malformed JSON from the model is exactly the thing a developer
        # needs to see verbatim, not a parse error in its place.
        return raw


def tool_span(
    span_id: str,
    name: str,
    arguments: dict[str, Any],
    start_ms: int,
    duration_ms: int,
    payload: dict[str, Any] | None = None,
    error: str | None = None,
    sent_to_model: dict[str, Any] | None = None,
) -> TraceSpan:
    """`sent_to_model` is set when the model received a trimmed copy of the
    result rather than the whole thing - the first thing to check when a
    model's answer disagrees with a payload you can see in full here."""
    if error is not None:
        return TraceSpan(
            id=span_id,
            kind="tool",
            name=name,
            start_ms=start_ms,
            duration_ms=duration_ms,
            status="error",
            summary=error,
            detail={"arguments": arguments, "error": error},
        )

    payload = payload or {}
    evidence = payload.get("evidence") or []
    count = evidence[0].get("result_count") if evidence else None
    summary = f"{count} record{'' if count == 1 else 's'}" if count is not None else "No evidence returned"
    if evidence:
        summary += f" · {evidence[0].get('source')}"
    if sent_to_model:
        summary += " · trimmed for the model"

    return TraceSpan(
        id=span_id,
        kind="tool",
        name=name,
        start_ms=start_ms,
        duration_ms=duration_ms,
        summary=summary,
        detail={
            "arguments": arguments,
            "result": _payload(payload.get("data", {})),
            "sent_to_model": sent_to_model,
            "evidence": [
                {
                    "evidence_id": item.get("evidence_id"),
                    "source": item.get("source"),
                    "criteria": item.get("criteria"),
                    "result_count": item.get("result_count"),
                    "query_hash": item.get("query_hash"),
                }
                for item in evidence
            ],
        },
    )


def submit_span(
    span_id: str,
    start_ms: int,
    arguments: dict[str, Any],
    valid_evidence_ids: list[str],
    accepted: bool,
    reason: str | None = None,
) -> TraceSpan:
    """submit_answer is not an MCP call - it is the orchestrator's own gate -
    but a rejected submission is the single most useful thing to see when an
    answer comes back uncited, so it gets a span of its own."""
    citations = arguments.get("citations") or []
    cited = [c.get("evidence_id") for c in citations if isinstance(c, dict)]
    invalid = [evidence_id for evidence_id in cited if evidence_id not in valid_evidence_ids]
    if accepted:
        summary = f"Accepted with {len(cited) - len(invalid)} valid citation{'' if len(cited) - len(invalid) == 1 else 's'}"
        if invalid:
            summary += f", {len(invalid)} invented one{'' if len(invalid) == 1 else 's'} dropped"
    else:
        summary = f"Rejected: {reason}"
    return TraceSpan(
        id=span_id,
        kind="submit",
        name="submit_answer",
        start_ms=start_ms,
        duration_ms=0,
        status="ok" if accepted else "rejected",
        summary=summary,
        detail={
            "answer": arguments.get("answer"),
            "citations": citations,
            "invalid_evidence_ids": invalid,
            "reason": reason,
        },
    )


def verifier_span(span_id: str, start_ms: int, duration_ms: int, verification: Verification) -> TraceSpan:
    readings = ", ".join(
        f"{check.key} {check.probability:.2f}" for check in verification.checks if check.probability is not None
    )
    summary = verification.headline + (f" · {readings}" if readings else "")
    return TraceSpan(
        id=span_id,
        kind="verifier",
        name=verification.model or "verifier",
        start_ms=start_ms,
        duration_ms=duration_ms,
        status="error" if verification.status == "unavailable" else "ok",
        summary=summary,
        detail={
            "status": verification.status,
            "verdict": verification.verdict,
            "verdict_confidence": verification.verdict_confidence,
            "checks": [check.model_dump() for check in verification.checks],
            # Operator telemetry - withheld from the answer badge on purpose
            # (see er.api.app), but this *is* the operator's view.
            "usage": verification.usage,
            "attempts": verification.attempts,
            "reason": verification.reason,
        },
    )
