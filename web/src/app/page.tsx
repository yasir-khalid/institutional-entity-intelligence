"use client";

import { useRef, useState, type ReactNode } from "react";
import { Bot, Building2, Check, ChevronRight, CircleAlert, FileText, Loader2, Search, Waypoints } from "lucide-react";
import SearchBar, { type ResearchMode } from "@/components/SearchBar";
import EvidenceList from "@/components/EvidenceLayer";
import Markdown from "@/components/Markdown";
import {
  askQuestionStream,
  getEntityDetail,
  search,
  type AskResponse,
  type AskStreamEvent,
  type EntityDetail,
  type SearchResult,
} from "@/lib/api";

const SUGGESTIONS = [
  { label: "Find an entity", query: "Point72", mode: "search" },
  { label: "Trace ownership", query: "Who ultimately manages Albacore Partners I Master Fund?", mode: "agent" },
  { label: "Check status", query: "What is the registration status of Fred Alger Management?", mode: "agent" },
] as const;

function Logo() {
  return <span className="query-logo"><Waypoints /></span>;
}

function SearchResults({ results, onOpen }: { results: SearchResult[]; onOpen: (entityId: string) => void }) {
  if (!results.length) return <EmptyState icon={<Search />} title="No matching entities" text="Try a legal name, jurisdiction, LEI, or CUSIP." />;
  return (
    <div className="candidate-list">
      {results.map((result) => {
        const status = result.decision === "AUTO_MATCH" ? "Resolved" : result.decision === "REVIEW" ? "Review" : "Candidate";
        return (
          <a key={result.entity_id} href="#entity-profile" onClick={() => onOpen(result.entity_id)} className="candidate-row">
            <span className="candidate-icon"><Building2 /></span>
            <div className="candidate-main">
              <h3>{result.canonical_name}</h3>
              <p>{result.jurisdiction ?? result.legal_country ?? "Jurisdiction unavailable"}</p>
              <span className="candidate-id">{result.entity_id}</span>
            </div>
            <span className={`candidate-status ${status.toLowerCase()}`}>{status}</span>
            <ChevronRight className="candidate-arrow" />
          </a>
        );
      })}
    </div>
  );
}

function EntityProfile({ detail, loading }: { detail: EntityDetail | null; loading: boolean }) {
  if (!detail && !loading) return null;
  if (loading) return <div id="entity-profile" className="entity-profile-loading"><Loader2 className="animate-spin" /> Opening entity profile…</div>;
  if (!detail) return null;
  return (
    <section id="entity-profile" className="entity-profile">
      <div className="entity-profile-heading"><span>Entity profile</span><a href={`https://search.gleif.org/#/search/lei/${detail.entity_id}`} target="_blank" rel="noreferrer">View in GLEIF ↗</a></div>
      <h2>{detail.canonical_name}</h2>
      <div className="entity-profile-grid">
        <div><small>LEI</small><code>{detail.entity_id}</code></div>
        <div><small>Status</small><p>{detail.entity_status ?? "—"}</p></div>
        <div><small>Jurisdiction</small><p>{detail.jurisdiction ?? detail.legal_country ?? "—"}</p></div>
        <div><small>Registration</small><p>{detail.lineage?.registration_status ?? "—"}</p></div>
      </div>
    </section>
  );
}

function EmptyState({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return <div className="empty-state"><span>{icon}</span><div><strong>{title}</strong><p>{text}</p></div></div>;
}

/* The live research feed: a running list of what the agent is doing, streamed
   from /api/ask/stream. Shown only while the answer is in flight and dropped
   the moment the answer arrives, per the "hide them once finished" request. */
function ResearchFeed({ events }: { events: AskStreamEvent[] }) {
  const last = events[events.length - 1];
  const inFlight = last && (last.type === "status" || last.type === "tool_call");
  return (
    <div className="research-feed" aria-live="polite" aria-busy="true">
      {events.map((event, index) => {
        const running = index === events.length - 1 && inFlight;
        return (
          <div key={index} className={`research-event ${event.type}`}>
            <span className="research-event-icon">
              {running ? <Loader2 className="animate-spin" /> : event.type === "tool_result" ? <Check /> : <span className="research-dot" />}
            </span>
            <div className="research-event-main">
              <p>{event.message ?? event.type}</p>
              {event.type === "tool_result" && (
                <small>
                  {event.count ?? 0} record{(event.count ?? 0) === 1 ? "" : "s"}
                  {event.source ? ` · ${event.source}` : ""}
                </small>
              )}
              {event.type === "tool_call" && event.tool && <small>via {event.tool}</small>}
            </div>
          </div>
        );
      })}
      {!inFlight && (
        <div className="research-event status">
          <span className="research-event-icon"><Loader2 className="animate-spin" /></span>
          <div className="research-event-main"><p>Researching…</p></div>
        </div>
      )}
    </div>
  );
}

function SourceSkeleton() {
  return (
    <div className="source-skeleton" aria-hidden>
      {[0, 1, 2].map((i) => (
        <div key={i} className="source-skeleton-card">
          <span /><span /><span />
        </div>
      ))}
    </div>
  );
}

export default function Home() {
  const [mode, setMode] = useState<ResearchMode>("search");
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchResults, setSearchResults] = useState<SearchResult[] | null>(null);
  const [agentResult, setAgentResult] = useState<AskResponse | null>(null);
  const [events, setEvents] = useState<AskStreamEvent[]>([]);
  const [focusedEvidenceId, setFocusedEvidenceId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const railRef = useRef<HTMLElement>(null);
  const hasOutput = Boolean(error) || searchResults !== null || agentResult !== null;
  const agentActive = mode === "agent" && (hasOutput || loading);

  function changeMode(nextMode: ResearchMode) {
    setMode(nextMode);
    setError(null);
    setSearchResults(null);
    setAgentResult(null);
    setEvents([]);
    setFocusedEvidenceId(null);
    setDetail(null);
  }

  async function runQuery(value: string, activeMode = mode) {
    setQuery(value);
    setLoading(true);
    setError(null);
    setSearchResults(null);
    setAgentResult(null);
    setEvents([]);
    setFocusedEvidenceId(null);
    setDetail(null);
    try {
      if (activeMode === "agent") {
        const result = await askQuestionStream(value, null, (event) => {
          if (event.type === "status" || event.type === "tool_call" || event.type === "tool_result") {
            setEvents((previous) => [...previous, event]);
          }
        });
        setAgentResult(result);
      } else {
        setSearchResults((await search(value, "name")).results);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "We couldn’t complete that request.");
    } finally {
      setLoading(false);
    }
  }

  function runSuggestion(suggestion: (typeof SUGGESTIONS)[number]) {
    changeMode(suggestion.mode);
    void runQuery(suggestion.query, suggestion.mode);
  }

  async function openEntity(entityId: string) {
    setDetailLoading(true);
    try {
      setDetail(await getEntityDetail(entityId));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "We couldn’t open that entity profile.");
    } finally {
      setDetailLoading(false);
    }
  }

  function focusEvidence(evidenceId: string) {
    setFocusedEvidenceId(evidenceId);
    const target = railRef.current?.querySelector<HTMLElement>(`#evidence-${CSS.escape(evidenceId)}`);
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  return (
    <main className={`query-app ${hasOutput || loading ? "has-output" : ""} ${agentActive ? "mode-agent" : ""}`}>
      <header className="query-header">
        <a href="#top" className="query-brand" aria-label="Entity Intelligence home"><Logo /><span>Entity intelligence</span></a>
        <span className="query-header-status"><i /> Research ready</span>
      </header>

      <section id="top" className={`query-page ${agentActive ? "has-agent" : ""}`}>
        <div className="query-intro">
          <p>Institutional entity intelligence</p>
          <h1>What do you want to know?</h1>
          <span>Resolve legal entities, inspect relationships, and trace the evidence behind the answer.</span>
        </div>

        <div className="query-column">
          <div className="query-composer"><SearchBar mode={mode} query={query} loading={loading} onModeChange={changeMode} onQueryChange={setQuery} onSubmit={runQuery} /></div>

          {!hasOutput && !loading && <div className="query-suggestions">
            {SUGGESTIONS.map((suggestion) => <button key={suggestion.label} type="button" onClick={() => runSuggestion(suggestion)}>
              <span>{suggestion.mode === "agent" ? <Bot /> : <Search />}</span><div><small>{suggestion.label}</small><p>{suggestion.query}</p></div>
            </button>)}
          </div>}

          {(hasOutput || loading) && <section className="query-output" aria-live="polite">
            {!loading && error && <div className="query-error"><CircleAlert /><div><strong>Request unavailable</strong><p>{error}</p></div></div>}
            {!loading && !error && mode === "search" && searchResults && <><p className="output-label">{searchResults.length} entity {searchResults.length === 1 ? "match" : "matches"}</p><SearchResults results={searchResults} onOpen={(entityId) => void openEntity(entityId)} /><EntityProfile detail={detail} loading={detailLoading} /></>}

            {mode === "agent" && !error && (loading || agentResult) && <div className="conversation">
              <div className="conversation-main">
                <div className="question-turn"><span>You</span><p>{query}</p></div>
                {loading && <ResearchFeed events={events} />}
                {!loading && agentResult && <div className="answer-turn">
                  <div className="answer-avatar"><Logo /></div>
                  <div className="answer-body">
                    <span className="answer-label">Entity Intelligence <i>MCP</i></span>
                    <Markdown content={agentResult.answer} citations={agentResult.citations} evidence={agentResult.evidence} onCitationClick={focusEvidence} />
                  </div>
                </div>}
              </div>

              <aside className="source-rail" ref={railRef} aria-label="Sources and method">
                <div className="source-heading"><FileText /> Sources &amp; method {agentResult && <span>{Object.keys(agentResult.evidence).length}</span>}</div>
                {agentResult
                  ? <EvidenceList
                      evidence={agentResult.evidence}
                      focusedEvidenceId={focusedEvidenceId}
                      compact
                      contexts={[{ answer: agentResult.answer, citations: agentResult.citations }]}
                    />
                  : <SourceSkeleton />}
              </aside>
            </div>}
          </section>}
        </div>
      </section>
    </main>
  );
}
