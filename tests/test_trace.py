"""er.agent.trace - the span builders (pure), and the orchestrator's emission
of them end to end against a fake MCP client and a scripted model. No live
services: the model is a canned response sequence and the verifier is stubbed.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from er.agent import orchestrator
from er.agent.models import Verification, VerificationCheck
from er.agent.trace import MAX_PAYLOAD_CHARS, llm_span, submit_span, tool_span, verifier_span
from er.config import load_config

FORCE_SEARCH = {"type": "function", "function": {"name": "search_entity"}}

OPENROUTER_RESPONSE = {
    "id": "gen-123",
    "model": "deepseek/deepseek-v4.1-flash",
    "provider": "Relace",
    "usage": {
        "prompt_tokens": 1200,
        "completion_tokens": 40,
        "cost": 2.96e-05,
        "prompt_tokens_details": {"cached_tokens": 800},
        "completion_tokens_details": {"reasoning_tokens": 12},
    },
    "choices": [
        {
            "finish_reason": "tool_calls",
            "message": {
                "content": None,
                "tool_calls": [
                    {"id": "c1", "function": {"name": "search_entity", "arguments": '{"query": "Point72"}'}}
                ],
            },
        }
    ],
}


def _evidence(evidence_id: str = "ev_one", count: int = 3) -> dict:
    return {
        "evidence_id": evidence_id,
        "source": "GLEIF entity record (exact LEI lookup)",
        "fact_type": "lookup",
        "criteria": ["Entity ID = X"],
        "record_refs": [],
        "fields_used": [],
        "result_count": count,
        "query_hash": "abc123",
        "warnings": [],
    }


# --- builders --------------------------------------------------------------


def test_llm_span_carries_what_a_developer_needs_to_find_the_call_again():
    span = llm_span("s1", 2, "requested/model", FORCE_SEARCH, 100, 850, response=OPENROUTER_RESPONSE)
    assert span.kind == "llm"
    # The model that actually answered, not the one requested - they differ
    # under OpenRouter routing and fallbacks.
    assert span.name == "deepseek/deepseek-v4.1-flash"
    assert span.detail["provider"] == "Relace"
    assert span.detail["generation_id"] == "gen-123"
    assert span.detail["usage"] == {
        "prompt_tokens": 1200,
        "completion_tokens": 40,
        "reasoning_tokens": 12,
        "cached_tokens": 800,
        "cost": 2.96e-05,
    }
    assert span.detail["tool_calls"] == [{"name": "search_entity", "arguments": {"query": "Point72"}}]
    assert span.summary == "Requested search_entity (forced: search_entity)"


def test_a_model_that_ignores_a_forced_tool_is_visible_as_such():
    response = {"choices": [{"message": {"content": "I already know this."}}]}
    span = llm_span("s1", 1, "m", FORCE_SEARCH, 0, 10, response=response)
    assert span.summary == "Replied in plain text, no tool call (forced: search_entity)"
    assert span.detail["content"] == "I already know this."


def test_malformed_tool_arguments_are_kept_verbatim_rather_than_replaced_by_a_parse_error():
    response = {"choices": [{"message": {"tool_calls": [{"function": {"name": "search_entity", "arguments": '{"query": '}}]}}]}
    span = llm_span("s1", 1, "m", None, 0, 10, response=response)
    assert span.detail["tool_calls"][0]["arguments"] == '{"query": '


def test_a_failed_model_call_is_an_error_span():
    span = llm_span("s1", 3, "requested/model", None, 0, 30_000, error="HTTP 429 from /api/v1/chat/completions")
    assert span.status == "error"
    assert span.name == "requested/model"
    assert "HTTP 429" in span.summary


def test_a_small_tool_payload_is_carried_whole():
    payload = {"data": {"matches": [{"entity_id": "X"}]}, "evidence": [_evidence(count=1)]}
    span = tool_span("s2", "search_entity", {"query": "Point72"}, 5, 400, payload=payload)
    assert span.detail["result"]["value"] == {"matches": [{"entity_id": "X"}]}
    assert span.detail["result"]["truncated"] is False
    assert span.summary == "1 record · GLEIF entity record (exact LEI lookup)"


def test_a_huge_tool_payload_arrives_shrunk_marked_and_with_its_real_size():
    """A real depth-3 relationship tree is ~1.2M chars. Streaming that to a
    browser per call is not an option - but a preview must never pass for
    the whole result, so the true size and a truncated flag travel with it."""
    tree = {"tree": {"lei": "ROOT", "downward": [{"lei": f"C{i}", "name": "X" * 80} for i in range(20_000)]}}
    span = tool_span("s2", "get_relationship_hierarchy", {"entity_id": "ROOT"}, 0, 900, payload={"data": tree})
    result = span.detail["result"]
    assert result["truncated"] is True
    assert result["chars"] > 1_000_000
    assert len(json.dumps(result["value"])) <= MAX_PAYLOAD_CHARS
    assert result["value"]["tree"]["lei"] == "ROOT"
    assert "more items elided" in result["value"]["tree"]["downward"][-1]


def test_a_tool_error_is_an_error_span():
    span = tool_span("s2", "get_entity_profile", {"entity_id": "X"}, 0, 5, error="LEI not found")
    assert span.status == "error"
    assert span.summary == "LEI not found"


def test_a_rejected_submission_says_why():
    span = submit_span("s3", 10, {"answer": "x", "citations": []}, [], accepted=False, reason="no data tool had been called yet")
    assert span.status == "rejected"
    assert span.summary == "Rejected: no data tool had been called yet"


def test_an_accepted_submission_reports_invented_citations_it_dropped():
    args = {
        "answer": "It is ACTIVE [1] and old [2].",
        "citations": [{"marker": 1, "evidence_id": "ev_real"}, {"marker": 2, "evidence_id": "ev_made_up"}],
    }
    span = submit_span("s3", 10, args, ["ev_real"], accepted=True)
    assert span.summary == "Accepted with 1 valid citation, 1 invented one dropped"
    assert span.detail["invalid_evidence_ids"] == ["ev_made_up"]


def test_a_verifier_that_did_not_run_is_an_error_span_not_a_clean_one():
    verification = Verification(status="unavailable", headline="Not checked", detail="...", reason="HTTP 503")
    assert verifier_span("s4", 0, 20, verification).status == "error"


# --- orchestrator emission --------------------------------------------------


class _FakeClient:
    def __init__(self, fail: bool = False):
        self.fail = fail

    async def list_tools(self):
        return SimpleNamespace(
            tools=[SimpleNamespace(name="search_entity", description="search", input_schema={"type": "object"})]
        )

    async def call_tool(self, name, args):
        if self.fail:
            raise ConnectionError("MCP server went away")
        return SimpleNamespace(
            structured_content={"data": {"matches": []}, "evidence": [_evidence("ev_test", 0)]},
            is_error=False,
            content=[],
        )


def _scripted_model(monkeypatch):
    responses = iter(
        [
            {"choices": [{"message": {"content": "I know this already."}}]},
            {"choices": [{"message": {"tool_calls": [
                {"id": "c1", "function": {"name": "search_entity", "arguments": '{"query": "Point72"}'}}
            ]}}]},
            {"choices": [{"message": {"tool_calls": [
                {"id": "c2", "function": {"name": "submit_answer", "arguments": json.dumps(
                    {"answer": "No matches [1]", "citations": [{"marker": 1, "evidence_id": "ev_test"}]}
                )}}
            ]}}]},
        ]
    )

    async def fake_call(_cfg, _messages, _tools, tool_choice=None):
        return next(responses)

    async def fake_verify(_cfg, _question, _result, _transcript):
        return Verification(
            status="verified",
            headline="Verified",
            detail="...",
            model="typesafe/jev-1.13",
            checks=[VerificationCheck(key="grounded", label="g", probability=0.9, threshold=0.7, passed=True)],
            verdict="supported",
        )

    monkeypatch.setattr(orchestrator, "_call_openrouter", fake_call)
    monkeypatch.setattr(orchestrator, "verify_answer", fake_verify)


def _run(client, trace: bool):
    events: list[dict] = []

    async def collect(event):
        events.append(event)

    result = asyncio.run(orchestrator.ask(client, load_config(), "Find Point72", on_event=collect, trace=trace))
    return result, events


def test_a_traced_run_emits_one_span_per_step_in_order(monkeypatch):
    _scripted_model(monkeypatch)
    result, events = _run(_FakeClient(), trace=True)
    spans = [event["span"] for event in events if event["type"] == "trace"]

    assert [(span["kind"], span["status"]) for span in spans] == [
        ("llm", "ok"),        # ignored the forced search, answered in prose
        ("llm", "ok"),        # asked for search_entity
        ("tool", "ok"),       # search_entity ran
        ("llm", "ok"),        # asked to submit
        ("submit", "ok"),     # accepted
        ("verifier", "ok"),
    ]
    assert spans[0]["summary"] == "Replied in plain text, no tool call (forced: search_entity)"
    assert spans[2]["detail"]["arguments"] == {"query": "Point72"}
    assert len({span["id"] for span in spans}) == len(spans)
    starts = [span["start_ms"] for span in spans]
    assert starts == sorted(starts)
    assert result.citations[0].evidence_id == "ev_test"


def test_the_trace_is_a_flat_run_that_records_which_llm_call_asked_for_what(monkeypatch):
    """One question is one turn: its LLM calls, tool calls, submission and
    verification are sibling steps under the run, in order. `requested_by`
    still records which LLM call asked for each tool call and submission -
    provenance the Developer view shows, not nesting it draws."""
    _scripted_model(monkeypatch)
    _, events = _run(_FakeClient(), trace=True)
    spans = [event["span"] for event in events if event["type"] == "trace"]
    by_kind = {}
    for span in spans:
        by_kind.setdefault(span["kind"], []).append(span)

    llm_1, llm_2, llm_3 = by_kind["llm"]
    (tool,) = by_kind["tool"]
    (submit,) = by_kind["submit"]
    (verify,) = by_kind["verifier"]

    assert all("parent_id" not in span for span in spans)
    assert [span["requested_by"] for span in (llm_1, llm_2, llm_3, verify)] == [None, None, None, None]
    assert tool["requested_by"] == llm_2["id"]      # the second call asked for search_entity
    assert submit["requested_by"] == llm_3["id"]    # the third call asked to submit
    assert [span["detail"]["iteration"] for span in (llm_1, llm_2, llm_3)] == [1, 2, 3]


def test_an_untraced_run_emits_no_spans_at_all(monkeypatch):
    """Tracing is opt-in: the product's own progress feed must be unchanged,
    and no span may be built - a relationship tree's preview costs a full
    serialisation of up to ~1.2M chars."""
    _scripted_model(monkeypatch)
    built = []
    monkeypatch.setattr(orchestrator, "tool_span", lambda *a, **k: built.append(1))
    _, events = _run(_FakeClient(), trace=False)
    assert not [event for event in events if event["type"] == "trace"]
    assert built == []


def test_a_tool_that_crashes_still_leaves_its_span_behind(monkeypatch):
    """The case a trace exists for: the run dies, and the last thing on
    screen must be the call that killed it, not the one before."""
    _scripted_model(monkeypatch)
    events: list[dict] = []

    async def collect(event):
        events.append(event)

    with pytest.raises(ConnectionError):
        asyncio.run(orchestrator.ask(_FakeClient(fail=True), load_config(), "Find Point72", on_event=collect, trace=True))

    last = [event["span"] for event in events if event["type"] == "trace"][-1]
    assert (last["kind"], last["name"], last["status"]) == ("tool", "search_entity", "error")
    assert last["summary"] == "ConnectionError: MCP server went away"


# --- what the model is sent -------------------------------------------------
# Found through the developer trace itself: asked to trace Citigroup Energy
# Holdings' ownership chain, the model requested the full profile of the chain's
# top entity (82VOJDD5PTRDMVVMGV31, Citigroup Global Markets Holdings) -
# 7,591,213 chars, because a profile inlines every attached identifier and that
# entity has 30,480 of them, nearly all ISINs. The orchestrator forwarded it
# verbatim and the next turn died: "The total text input size exceeds 8 MB".
# (Re-run live after the fix, the model reported "30,480 attached identifiers",
# taken from the evidence count, and said the list it saw was trimmed.)


def test_a_normal_tool_result_reaches_the_model_untouched():
    data = {"matches": [{"entity_id": f"E{i}"} for i in range(10)]}
    view, note = orchestrator._model_view(data, 40_000)
    assert view == {"data": data}
    assert note is None


def test_an_oversized_result_is_trimmed_for_the_model_and_the_model_is_told():
    """A trimmed subsidiary list reads exactly like a short one - so the model
    is told the list was cut, and where to get the true count."""
    data = {"profile": {"lei": "ROOT", "subsidiaries": [{"lei": f"S{i}", "name": "N" * 60} for i in range(60_000)]}}
    view, note = orchestrator._model_view(data, 40_000)
    assert len(json.dumps(view["data"])) <= 40_000
    assert view["data"]["profile"]["lei"] == "ROOT"
    assert "more items elided" in view["data"]["profile"]["subsidiaries"][-1]
    assert view["data_truncated"] is note
    assert note["original_chars"] > 4_000_000
    assert "result_count" in note["note"]


def test_the_8mb_failure_does_not_recur(monkeypatch):
    """Replay of the real failure, offline: a 7.6M-char profile must reach the
    model as something that fits, with every evidence_id intact so it can still
    cite, and the trace must say the model saw a trimmed copy."""
    huge = {"profile": {"entity_id": "82VOJDD5PTRDMVVMGV31", "identifiers": [
        {"identifier_type": "ISIN", "identifier_value": f"DE000A{i:06d}", "source": "GLEIF ISIN bridge " + "X" * 60}
        for i in range(70_000)
    ]}}

    class Client(_FakeClient):
        async def call_tool(self, name, args):
            return SimpleNamespace(
                structured_content={"data": huge, "evidence": [_evidence("ev_big", 70_000)]}, is_error=False, content=[]
            )

    sent: list[list[dict]] = []
    responses = iter([
        {"choices": [{"message": {"tool_calls": [
            {"id": "c1", "function": {"name": "search_entity", "arguments": '{"query": "Citigroup"}'}}
        ]}}]},
        {"choices": [{"message": {"tool_calls": [
            {"id": "c2", "function": {"name": "submit_answer", "arguments": json.dumps(
                {"answer": "Top of chain [1]", "citations": [{"marker": 1, "evidence_id": "ev_big"}]}
            )}}
        ]}}]},
    ])

    async def fake_call(_cfg, messages, _tools, tool_choice=None):
        sent.append(list(messages))
        return next(responses)

    async def fake_verify(*_a):
        return Verification(status="verified", headline="Verified", detail="...")

    monkeypatch.setattr(orchestrator, "_call_openrouter", fake_call)
    monkeypatch.setattr(orchestrator, "verify_answer", fake_verify)

    events: list[dict] = []

    async def collect(event):
        events.append(event)

    result = asyncio.run(orchestrator.ask(Client(), load_config(), "Trace Citigroup", on_event=collect, trace=True))

    tool_message = next(m for m in sent[-1] if m.get("role") == "tool")
    body = json.loads(tool_message["content"])
    assert len(json.dumps(huge)) > 7_000_000
    assert len(tool_message["content"]) < 60_000
    assert body["evidence"][0]["evidence_id"] == "ev_big"
    assert body["data_truncated"]["original_chars"] > 7_000_000
    assert result.citations[0].evidence_id == "ev_big"

    tool = next(e["span"] for e in events if e["type"] == "trace" and e["span"]["kind"] == "tool")
    assert tool["detail"]["sent_to_model"]["original_chars"] > 7_000_000
    assert tool["summary"].endswith("trimmed for the model")


def test_an_http_error_carries_the_providers_own_explanation():
    """"HTTP 400" alone sent the first diagnosis of the 8 MB failure down the
    wrong path. The body said exactly what was wrong."""
    import httpx

    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(
        400, request=request, json={"error": {"message": "The total text input size exceeds 8 MB", "code": 400}}
    )
    exc = httpx.HTTPStatusError("400", request=request, response=response)
    assert orchestrator._describe(exc) == "HTTP 400 from /api/v1/chat/completions: The total text input size exceeds 8 MB"


def test_an_http_error_without_a_json_body_still_says_something_useful():
    import httpx

    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(502, request=request, text="upstream connect error")
    exc = httpx.HTTPStatusError("502", request=request, response=response)
    assert orchestrator._describe(exc) == "HTTP 502 from /api/v1/chat/completions: upstream connect error"


# --- transient model failures ------------------------------------------------
# Seen in the web UI as "Request unavailable - Server disconnected without
# sending a response.": OpenRouter dropped one connection before replying
# (httpx.RemoteProtocolError). Eight calls made straight afterwards all
# succeeded - it was transient, but with no retry it killed the whole run, and
# the raw httpx message didn't even say which server had disconnected.

import httpx


def _dropped() -> httpx.RemoteProtocolError:
    return httpx.RemoteProtocolError("Server disconnected without sending a response.")


def _status(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
    response = httpx.Response(code, request=request, json={"error": {"message": f"status {code}"}})
    return httpx.HTTPStatusError(str(code), request=request, response=response)


def _flaky_model(monkeypatch, failures: list[BaseException]):
    """The first calls raise `failures` in order; after that the scripted
    happy path from _scripted_model() runs. Returns the list of attempts."""
    _scripted_model(monkeypatch)
    succeed = orchestrator._call_openrouter
    attempts: list[int] = []
    queue = list(failures)

    async def flaky(cfg, messages, tools, tool_choice=None):
        attempts.append(1)
        if queue:
            raise queue.pop(0)
        return await succeed(cfg, messages, tools, tool_choice=tool_choice)

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(orchestrator, "_call_openrouter", flaky)
    monkeypatch.setattr(orchestrator, "_backoff", no_wait)
    return attempts


def test_a_dropped_connection_is_retried_and_the_run_completes(monkeypatch):
    attempts = _flaky_model(monkeypatch, [_dropped()])
    result, events = _run(_FakeClient(), trace=True)

    assert result.citations[0].evidence_id == "ev_test"
    assert len(attempts) == 4  # 1 dropped + the 3 turns of the happy path
    spans = [event["span"] for event in events if event["type"] == "trace"]
    # The failed attempt is in the trace, not hidden behind the retry.
    assert (spans[0]["kind"], spans[0]["status"]) == ("llm", "error")
    assert "Server disconnected without sending a response" in spans[0]["summary"]
    assert "retrying (attempt 1 of 3)" in spans[0]["summary"]
    assert (spans[1]["kind"], spans[1]["status"]) == ("llm", "ok")
    # ...and the reader of the progress feed is told, not left on a spinner.
    assert any("retrying" in (event.get("message") or "") for event in events if event["type"] == "status")


def test_gateway_and_rate_limit_statuses_are_retried(monkeypatch):
    attempts = _flaky_model(monkeypatch, [_status(503), _status(429)])
    result, _ = _run(_FakeClient(), trace=False)
    assert result.citations[0].evidence_id == "ev_test"
    assert len(attempts) == 5


def test_a_bad_request_is_never_retried(monkeypatch):
    """A 400 - like the "input exceeds 8 MB" failure - fails identically
    however many times it is sent. Retrying it only delays the error."""
    attempts = _flaky_model(monkeypatch, [_status(400)])
    with pytest.raises(httpx.HTTPStatusError):
        _run(_FakeClient(), trace=False)
    assert len(attempts) == 1


def test_when_retries_run_out_the_error_says_who_failed_in_plain_words(monkeypatch):
    attempts = _flaky_model(monkeypatch, [_dropped(), _dropped(), _dropped()])
    with pytest.raises(orchestrator.ModelUnavailableError) as raised:
        _run(_FakeClient(), trace=False)

    assert len(attempts) == 3
    message = str(raised.value)
    assert message.startswith("The model provider (OpenRouter) failed 3 times in a row")
    assert "usually temporary" in message
    # The raw transport error is kept for whoever debugs it.
    assert isinstance(raised.value.__cause__, httpx.RemoteProtocolError)
