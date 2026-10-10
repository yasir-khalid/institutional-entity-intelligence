# The agent

`er.agent.mcp_server` is a standalone MCP server (`search_entity`,
`get_entity_profile`, `get_relationship_hierarchy`, `search_adv_documents`,
`get_position_history`, `get_beneficial_owners`, `get_entity_connections`,
`get_fund_structure`, `get_security`).
`er.agent.orchestrator` drives an OpenRouter model through it over stdio, the
same way any other MCP client would, until the model calls `submit_answer`.

```bash
uv run python -m er.cli.mcp_server      # just the server, for any MCP client
uv run python -m er.cli.ask --entity-id 254900ESP1ZKG7UNS007 --question "What is its registration status?"
```

## Talking to it from another agent (A2A)

The API also serves the agent over the [A2A protocol](https://a2a-protocol.org)
(v1.0, JSON-RPC binding), from `er.api.a2a`. Any A2A client - another agent,
an agent workspace - discovers it from the card and sends it messages:

- `GET /.well-known/agent-card.json` - the agent card (one `entity_research` skill)
- `POST /a2a` - JSON-RPC: `SendMessage`, `SendStreamingMessage`, `GetTask`, `CancelTask`

One message is one `orchestrator.ask()` run, the same path as `/api/ask`.
Progress streams as `working` status updates. The task completes with one
`answer` artifact: a `text/markdown` part (the rendered answer) and a data part
with `citations`, `evidence`, `facts`, `derivations` and the Jev
`verification`, so the calling agent keeps the provenance. Set `entity_id` (an
LEI) in the message metadata to scope a question; send follow-ups with the
same `contextId` and the last four answered turns go along as history.

`A2A_PUBLIC_URL` is the address advertised in the card (default
`http://localhost:8000`) - set it to the deployed URL. With `A2A_API_KEY` set,
`/a2a` requires `Authorization: Bearer <key>` and the card says so; without it
`/a2a` is open, which is only fine on localhost since every call spends
OpenRouter credit. Tasks live in memory: a restart forgets conversations, and
running more than one API replica needs a shared task store first.

```bash
make api
curl -s localhost:8000/.well-known/agent-card.json
curl -s localhost:8000/a2a -H 'Content-Type: application/json' -H 'A2A-Version: 1.0' -d '{
  "jsonrpc": "2.0", "id": 1, "method": "SendMessage",
  "params": {"message": {"messageId": "m1", "role": "ROLE_USER",
    "parts": [{"text": "Who is the direct parent of BlackRock Fund Advisors?"}]}}}'
```

## The submission gate

Tools return facts with an address (source, document, locator, field). The
model writes `{{f:fact_id}}` instead of a value, and a numeric literal in its
text is rejected. Before rendering, the orchestrator re-runs the tool behind
every cited fact and checks the same fact comes back; if it doesn't, the
submission goes back to the model with the reason. Computed values (a
position's change between 13F reports) come from registered formulas in
`er.knowledge.formulas` and carry their input facts, so the evidence card can
show the formula. Form ADV citations open the original PDF page.

## Answer verification

After the agent finishes, the answer and every tool
result behind it go to [TypeSafe's Jev](https://openrouter.ai/typesafe)
(`typesafe/jev-1.13`, OpenRouter's Decisions API) - a *decision* model rather
than a chat model: it answers a fixed set of typed questions in one forward
pass and returns a calibrated probability for each, so it cannot invent an
option or a confidence score the way a chat model asked to "rate this answer"
can. Four checks (claims match the records / no conflict with the records /
citations point at the right evidence / stays inside the retrieved data) plus an
overall verdict become one badge, via thresholds that live in
`config/dev.yaml`, not in code. It adds ~0.4-0.6s and ~$0.00002 per answer.

The badge says the answer matches what was retrieved - never that the records
are complete or correct. "Not checked" (the verifier was unreachable) is a
distinct state from "not verified" (it ran and the answer didn't hold up), and
renders grey rather than red. The thresholds were calibrated against a labelled
answer set rather than picked by feel; the readings, and a real bug the
measurement caught, are in
[`experiments/006-jev-answer-verification.md`](../experiments/006-jev-answer-verification.md).

## Developer view

The **Developer** button in the header docks a trace of
the last agent run on the right, laid out like Arize Phoenix / Langfuse: one
agent span at the root and, under it, every step in the order it happened -
LLM calls, MCP tool calls, the `submit_answer` guardrail and the Jev
evaluator. They are sibling steps, not turns: one question is one turn. Each
span kind has its own icon and tint. Select a span and its latency, tokens,
cost and input/output open beside the tree, payloads as a collapsible
key/value tree: for an LLM call, the tool calls it requested, forced tool
choice, finish reason, provider and OpenRouter generation id; for a tool
call, its arguments, result and evidence, plus which LLM call requested it;
for the guardrail, a rejection and why; for the evaluator, each check's
reading against its threshold. The root shows the whole run as a timeline.
Spans stream in live as the run happens, and a failed run opens on the span
that failed. A run that crashes still leaves every step up to the one that
killed it. Payload previews are capped at 20k chars; a larger result (a deep
relationship tree is ~1.2M) arrives shape-preserved with long lists trimmed
and each elision marked, and the panel shows its true size. Traces come from `er.agent.trace` and are
opt-in on the API (`"trace": true` on `/api/ask/stream`); the web client
always asks for one so the panel can be opened *after* an answer looks wrong.

Separately, each tool result is capped at `agent.max_tool_result_chars`
(40k) *as sent to the model* - the full profile of a large issuer inlines
tens of thousands of ISINs (~7.6M chars), which OpenRouter rejects outright.
Over the cap, lists are trimmed with each elision marked and the model is told
to take counts from the evidence records; the trace shows when this happened.
