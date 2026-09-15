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
