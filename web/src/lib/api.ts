// Thin client for the FastAPI backend (src/er/api/app.py) - all shapes mirror
// er.api.schemas exactly. This file owns no business logic itself, same
// principle as the Python side: it only fetches and types the response.

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
}

export interface Sec13FActivity {
  cik: string;
  latest_period_of_report: string | null;
  latest_filing_date: string | null;
  reported_security_count: number;
  top_reported_holdings: Sec13FHolding[];
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
  sec_13f: Sec13FActivity | null;
  parent_count: number;
  subsidiary_count: number;
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
  verification: Verification | null;
}

/* One step of an agent run, mirrored from er.agent.trace.TraceSpan - a model
   turn, an MCP tool call, the submit_answer gate, or the verifier. Only
   streamed when the request asks for `trace`. `start_ms` is relative to the
   start of the run so spans lay out as a waterfall directly. `detail` differs
   by kind; DeveloperPanel reads it field by field. */
export interface TraceSpan {
  id: string;
  /** The model turn that requested this call; null for turns and the verifier,
   * which sit directly under the run. Makes the trace a tree. */
  parent_id: string | null;
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

export async function askQuestion(question: string, entityId: string | null): Promise<AskResponse> {
  const res = await fetch(`${API_URL}/api/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, entity_id: entityId }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<AskResponse>;
}

/** Same answer as askQuestion, but consumes /api/ask/stream's Server-Sent
 * Events so the caller can render progress (`onEvent`) instead of waiting on a
 * blank spinner. Resolves with the final answer, or throws on an error event. */
export async function askQuestionStream(
  question: string,
  entityId: string | null,
  onEvent: (event: AskStreamEvent) => void,
  options: { trace?: boolean } = {},
): Promise<AskResponse> {
  const res = await fetch(`${API_URL}/api/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, entity_id: entityId, trace: options.trace ?? false }),
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
