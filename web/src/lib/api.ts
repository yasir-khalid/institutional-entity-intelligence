// Thin client for the FastAPI backend (src/er/api/app.py) - all shapes mirror
// er.api.schemas exactly. This file owns no business logic itself, same
// principle as the Python side: it only fetches and types the response.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function apiUrl(path: string): string {
  return path.startsWith("/") ? `${API_URL}${path}` : path;
}

export type SearchType = "name" | "lei" | "cusip";

export interface SearchResult {
  entity_id: string;
  canonical_name: string;
  jurisdiction: string | null;
  legal_country: string | null;
  decision: string | null;
  score: number | null;
  matched_via: SearchType;
  cik: string | null;
}

export interface SearchResponse {
  query: string;
  search_type: SearchType;
  results: SearchResult[];
}

export interface TreeNode {
  entity_id: string;
  name: string | null;
  direction: "upward" | "downward" | null;
  relationship_type: string | null;
  label: string | null;
  expanded: boolean;
  children: TreeNode[];
}

export interface EntityIdentifier {
  identifier_type: string;
  identifier_value: string;
  confidence: string;
  source: string;
  source_file: string | null;
  snapshot_date: string | null;
  ingested_at: string | null;
}

export interface EntityLineage {
  entity_creation_date: string | null;
  initial_registration_date: string | null;
  last_update_date: string | null;
  next_renewal_date: string | null;
  registration_status: string | null;
  gleif_snapshot_date: string | null;
}

export interface Sec13FHolding {
  name_of_issuer: string;
  value: number | null;
  cusip: string | null;
}

export interface Sec13FActivity {
  cik: string;
  latest_period_of_report: string | null;
  latest_filing_date: string | null;
  reported_security_count: number;
  value_unit: string;
  top_reported_holdings: Sec13FHolding[];
  /** "accession: ERROR, ..." for filings kept out of the holdings because
   * they did not reconcile with their own summary page. */
  quarantined_filings: string[];
  /** Latest-period filings whose values look like thousands despite the
   * whole-dollar rule. Shown as filed, flagged rather than rescaled. */
  scale_suspect_filings: string[];
}

/* Relationships from sources other than GLEIF's hierarchy, from the knowledge
   graph (er.entity.connections). Each edge_type is a different claim - bank
   control, >5% beneficial ownership, significant control, insider, succession -
   and the UI keeps them apart. `direction` is from this entity's side. */
export interface Connection {
  edge_type: string;
  direction: "outgoing" | "incoming";
  other_node_id: string;
  other_name: string | null;
  other_type: string | null;
  source: string;
  valid_from: string | null;
  valid_to: string | null;
  percent: number | null;
  source_url: string | null;
}

export interface ConnectionGroup {
  edge_type: string;
  direction: "outgoing" | "incoming";
  total: number;
  connections: Connection[];
}

export interface LinkedRecord {
  node_id: string;
  display_name: string | null;
  source: string;
}

export interface MatchReview {
  node_id: string;
  lei: string;
  outcome: "CONFIRMED" | "REJECTED";
  reviewer: string;
  reviewed_at: string;
  rationale: string | null;
}

/** The stored crosswalk decision linking a source record to this LEI
 * (er.entity.resolution) - the evidence for "this CIK is this entity". */
export interface MatchDecision {
  node_id: string;
  source_name: string | null;
  lei: string | null;
  decision: string;
  score: number | null;
  gap: number | null;
  reason: string | null;
  runner_up_lei: string | null;
  runner_up_name: string | null;
  runner_up_score: number | null;
  feature_contributions: Record<string, number>;
  config_hash: string | null;
  decided_on: string | null;
  reviews: MatchReview[];
}

export interface EntityDetail {
  entity_id: string;
  canonical_name: string;
  entity_type: string | null;
  jurisdiction: string | null;
  legal_country: string | null;
  entity_status: string | null;
  lineage: EntityLineage | null;
  identifiers: EntityIdentifier[];
  /** Every identifier attached; `identifiers` holds up to 200 per type. */
  identifier_total: number;
  sec_13f: Sec13FActivity | null;
  parent_count: number;
  subsidiary_count: number;
  connections: { linked_records: LinkedRecord[]; groups: ConnectionGroup[] };
  match_decisions: MatchDecision[];
}

/* ---------------------------------------------------------------------------
   The entity Q&A agent (er.agent) - not RAG-style text chunks, since there is
   no document corpus here: each Evidence entry is a deterministic provenance
   record a tool call constructed from the exact lookup it just ran (source,
   criteria, record count, timestamp, reproducible query hash), never an
   LLM-invented confidence score. See er.agent.models.Evidence.
--------------------------------------------------------------------------- */

export interface Evidence {
  evidence_id: string;
  source: string;
  source_timestamp: string | null;
  fact_type: string;
  criteria: string[];
  record_refs: string[];
  fields_used: string[];
  result_count: number | null;
  query_hash: string;
  warnings: string[];
  source_uri: string | null;
  page: number | null;
}

/* An addressed value (er.agent.models.Fact): the answer states it through a
   placeholder the server fills in, so every number in an answer has one of
   these behind it - source, document, and the exact place in it. */
export interface FactAddress {
  source: string;
  document_id: string;
  snapshot_id: string | null;
  locator: string;
  field: string;
  uri: string | null;
  page: number | null;
  char_start: number | null;
  char_end: number | null;
}

export interface Fact {
  fact_id: string;
  evidence_id: string;
  subject: string;
  predicate: string;
  value: string | number | boolean | null;
  unit: string | null;
  as_of: string | null;
  address: FactAddress;
}

/** A computed fact: a registered formula (er.knowledge.formulas) applied to
 * input facts, each of which is in the same facts map. */
export interface Derivation {
  fact_id: string;
  formula_id: string;
  expression: string;
  inputs: string[];
}

export interface ToolResult {
  data: Record<string, unknown>;
  evidence: Evidence[];
  facts: Fact[];
  derivations: Derivation[];
}

export interface Citation {
  marker: number;
  evidence_id: string;
}

/* The answer's verification badge, mirrored from er.api.schemas.VerificationOut
   (produced by er.agent.verifier). `status` "unavailable" means the check did
   not run - a different state from "unverified", which means it ran and the
   answer did not hold up. `probability` is null when the verifier returned no
   reading for that check: no signal, never a failure. */
export interface VerificationCheck {
  key: string;
  label: string;
  probability: number | null;
  threshold: number;
  passed: boolean | null;
}

export interface Verification {
  status: "verified" | "partial" | "unverified" | "unavailable";
  headline: string;
  detail: string;
  model: string | null;
  checks: VerificationCheck[];
  verdict: string | null;
  verdict_confidence: number | null;
  latency_ms: number | null;
  reason: string | null;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  evidence: Record<string, Evidence>;
  facts: Record<string, Fact>;
  derivations: Record<string, Derivation>;
  verification: Verification | null;
}

export interface ConversationTurn {
  role: "user" | "assistant";
  content: string;
}

/* One step of an agent run, mirrored from er.agent.trace.TraceSpan - an LLM
   call, an MCP tool call, the submit_answer gate, or the verifier. Only
   streamed when the request asks for `trace`. `start_ms` is relative to the
   start of the run so spans lay out as a waterfall directly. `detail` differs
   by kind; DeveloperPanel reads it field by field. */
export interface TraceSpan {
  id: string;
  /** The LLM call that requested this tool call or submission; null for LLM
   * calls and the verifier. Provenance only - every span is a step directly
   * under the run. */
  requested_by: string | null;
  kind: "llm" | "tool" | "submit" | "verifier";
  name: string;
  start_ms: number;
  duration_ms: number;
  status: "ok" | "error" | "rejected";
  summary: string;
  detail: Record<string, unknown>;
}

/** One progress event emitted while the agent researches, mirrored from
 * er.agent.orchestrator.ProgressEvent (see er/api/app.py's /api/ask/stream). */
export interface AskStreamEvent {
  type: "status" | "tool_call" | "tool_result" | "verification" | "trace" | "answer" | "error";
  message?: string;
  tool?: string;
  source?: string | null;
  count?: number | null;
  evidence_ids?: string[];
  answer?: string;
  citations?: Citation[];
  evidence?: Record<string, Evidence>;
  facts?: Record<string, Fact>;
  derivations?: Record<string, Derivation>;
  status?: string;
  detail?: string;
  verification?: Verification | null;
  span?: TraceSpan;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export function search(query: string, searchType: SearchType, country?: string): Promise<SearchResponse> {
  const params = new URLSearchParams({ query, search_type: searchType });
  if (country) params.set("country", country);
  return getJson(`/api/search?${params.toString()}`);
}

export function getEntityTree(entityId: string, depth = 2): Promise<TreeNode> {
  return getJson(`/api/entity/${encodeURIComponent(entityId)}/tree?depth=${depth}`);
}

export function getEntityDetail(entityId: string): Promise<EntityDetail> {
  return getJson(`/api/entity/${encodeURIComponent(entityId)}`);
}

export function getPositionHistory(cik: string, cusip: string): Promise<ToolResult> {
  return getJson(`/api/positions/${encodeURIComponent(cik)}/${encodeURIComponent(cusip)}`);
}

export async function submitReview(review: {
  node_id: string;
  lei: string;
  outcome: "CONFIRMED" | "REJECTED";
  reviewer: string;
  rationale: string;
}): Promise<MatchReview> {
  const res = await fetch(`${API_URL}/api/reviews`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(review),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<MatchReview>;
}

/** Asks the agent through /api/ask/stream's Server-Sent Events, so the caller
 * can render progress (`onEvent`) instead of waiting on a blank spinner.
 * Resolves with the final answer, or throws on an error event. */
export async function askQuestionStream(
  question: string,
  entityId: string | null,
  onEvent: (event: AskStreamEvent) => void,
  options: { trace?: boolean; history?: ConversationTurn[] } = {},
): Promise<AskResponse> {
  const res = await fetch(`${API_URL}/api/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      entity_id: entityId,
      trace: options.trace ?? false,
      history: options.history ?? [],
    }),
  });
  if (!res.ok || !res.body) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let final: AskResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      const line = frame.split("\n").find((entry) => entry.startsWith("data: "));
      if (!line) continue;
      const event = JSON.parse(line.slice(6)) as AskStreamEvent;
      onEvent(event);
      if (event.type === "answer") {
        final = {
          answer: event.answer ?? "",
          citations: event.citations ?? [],
          evidence: event.evidence ?? {},
          facts: event.facts ?? {},
          derivations: event.derivations ?? {},
          verification: event.verification ?? null,
        };
      } else if (event.type === "error") {
        throw new Error(event.message ?? "The agent could not produce an answer.");
      }
    }
  }

  if (!final) throw new Error("The agent stream ended without an answer.");
  return final;
}
