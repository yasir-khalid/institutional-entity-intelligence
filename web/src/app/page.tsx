"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowUp, Bot, Building2, Check, ChevronRight, CircleAlert, FileText, Loader2, Search, SquareTerminal, Waypoints } from "lucide-react";
import SearchBar, { type ResearchMode } from "@/components/SearchBar";
import EvidenceList from "@/components/EvidenceLayer";
import Markdown from "@/components/Markdown";
import VerificationBadge from "@/components/VerificationBadge";
import DeveloperPanel from "@/components/DeveloperPanel";
import EntityProfile from "@/components/EntityProfile";
import {
  askQuestionStream,
  getEntityDetail,
  search,
  type AskStreamEvent,
  type Citation,
  type Derivation,
  type Evidence,
  type Fact,
  type EntityDetail,
  type SearchResult,
  type TraceSpan,
  type Verification,
} from "@/lib/api";

const DEVTOOLS_KEY = "er:developer-view";

const SUGGESTIONS = [
  { label: "Find an entity", query: "Point72", mode: "search" },
  { label: "Trace ownership", query: "Who ultimately manages Albacore Partners I Master Fund?", mode: "agent" },
  { label: "Check status", query: "What is the registration status of Fred Alger Management?", mode: "agent" },
] as const;

type AgentMessage = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  verification?: Verification | null;
};

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
  const [agentMessages, setAgentMessages] = useState<AgentMessage[]>([]);
  const [evidenceStore, setEvidenceStore] = useState<Record<string, Evidence>>({});
  const [factStore, setFactStore] = useState<Record<string, Fact>>({});
  const [derivationStore, setDerivationStore] = useState<Record<string, Derivation>>({});
  const [followup, setFollowup] = useState("");
  const [events, setEvents] = useState<AskStreamEvent[]>([]);
  const [focusedEvidenceId, setFocusedEvidenceId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const railRef = useRef<HTMLElement>(null);
  // Developer view. The trace belongs to the last *agent* run and outlives a
  // mode switch on purpose: you notice something odd, flip to Search to check
  // an entity, and the trace you were debugging is still there.
  const [devOpen, setDevOpen] = useState(false);
  const [trace, setTrace] = useState<TraceSpan[]>([]);
  const [traceQuestion, setTraceQuestion] = useState<string | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [traceRunning, setTraceRunning] = useState(false);

  // Restore the panel's open state after hydration - devtools stay open across
  // reloads, and localStorage doesn't exist during server render.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDevOpen(window.localStorage.getItem(DEVTOOLS_KEY) === "1");
  }, []);

  function setDeveloperView(next: boolean) {
    setDevOpen(next);
    window.localStorage.setItem(DEVTOOLS_KEY, next ? "1" : "0");
  }
  const hasOutput = Boolean(error) || searchResults !== null || agentMessages.length > 0;
  const agentActive = mode === "agent" && (agentMessages.length > 0 || loading || Boolean(error));

  function changeMode(nextMode: ResearchMode) {
    setMode(nextMode);
    setError(null);
    setSearchResults(null);
    setAgentMessages([]);
    setEvidenceStore({});
    setFactStore({});
    setDerivationStore({});
    setFollowup("");
    setEvents([]);
    setFocusedEvidenceId(null);
    setDetail(null);
  }

  async function runQuery(value: string, activeMode = mode) {
    setQuery(value);
    setLoading(true);
    setError(null);
    setSearchResults(null);
    setEvents([]);
    setFocusedEvidenceId(null);
    setDetail(null);
    try {
      if (activeMode === "agent") {
        const history = agentMessages.map(({ role, content }) => ({ role, content }));
        setAgentMessages((previous) => [...previous, { role: "user", content: value }]);
        setFollowup("");
        setTrace([]);
        setTraceQuestion(value);
        setTraceError(null);
        setTraceRunning(true);
        // Always traced, not only while the panel is open: the moment you
        // want a trace is usually right after an answer looked wrong, and by
        // then the run is over. Payload previews are capped server-side
        // (er.agent.trace.MAX_PAYLOAD_CHARS), so this stays bounded.
        const result = await askQuestionStream(
          value,
          null,
          (event) => {
            if (event.type === "trace" && event.span) {
              const span = event.span;
              setTrace((previous) => [...previous, span]);
            } else if (event.type === "status" || event.type === "tool_call" || event.type === "tool_result") {
              setEvents((previous) => [...previous, event]);
            }
          },
          { trace: true, history },
        );
        setEvidenceStore((previous) => ({ ...previous, ...result.evidence }));
        setFactStore((previous) => ({ ...previous, ...result.facts }));
        setDerivationStore((previous) => ({ ...previous, ...result.derivations }));
        setAgentMessages((previous) => [
          ...previous,
          { role: "assistant", content: result.answer, citations: result.citations, verification: result.verification },
        ]);
      } else {
        setAgentMessages([]);
        setEvidenceStore({});
        setFactStore({});
        setDerivationStore({});
        setSearchResults((await search(value, "name")).results);
      }
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "We couldn’t complete that request.";
      setError(message);
      if (activeMode === "agent") setTraceError(message);
    } finally {
      setLoading(false);
      setTraceRunning(false);
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

  function submitFollowup(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = followup.trim();
    if (value && !loading) void runQuery(value, "agent");
  }

  return (
    <main className={`query-app ${hasOutput || loading ? "has-output" : ""} ${agentActive ? "mode-agent" : ""} ${devOpen ? "dev-open" : ""}`}>
      <header className="query-header">
        <a href="#top" className="query-brand" aria-label="Entity Intelligence home"><Logo /><span>Entity intelligence</span></a>
        <div className="query-header-actions">
          <span className="query-header-status"><i /> Research ready</span>
          <button
            type="button"
            className="devtools-toggle"
            aria-pressed={devOpen}
            aria-controls="developer-panel"
            onClick={() => setDeveloperView(!devOpen)}
          >
            <SquareTerminal /> Developer
          </button>
        </div>
      </header>

      <section id="top" className={`query-page ${agentActive ? "has-agent" : ""}`}>
        <div className="query-intro">
          <p>Institutional entity intelligence</p>
          <h1>What do you want to know?</h1>
          <span>Resolve legal entities, inspect relationships, and trace the evidence behind the answer.</span>
        </div>

        <div className="query-column">
          {!(mode === "agent" && agentMessages.length > 0) && (
            <div className="query-composer"><SearchBar mode={mode} query={query} loading={loading} onModeChange={changeMode} onQueryChange={setQuery} onSubmit={runQuery} /></div>
          )}

          {!hasOutput && !loading && <div className="query-suggestions">
            {SUGGESTIONS.map((suggestion) => <button key={suggestion.label} type="button" onClick={() => runSuggestion(suggestion)}>
              <span>{suggestion.mode === "agent" ? <Bot /> : <Search />}</span><div><small>{suggestion.label}</small><p>{suggestion.query}</p></div>
            </button>)}
          </div>}

          {(hasOutput || loading) && <section className="query-output" aria-live="polite">
            {!loading && error && <div className="query-error"><CircleAlert /><div><strong>Request unavailable</strong><p>{error}</p></div></div>}
            {!loading && !error && mode === "search" && searchResults && <><p className="output-label">{searchResults.length} entity {searchResults.length === 1 ? "match" : "matches"}</p><SearchResults results={searchResults} onOpen={(entityId) => void openEntity(entityId)} /><EntityProfile detail={detail} loading={detailLoading} onOpenEntity={(entityId) => void openEntity(entityId)} /></>}

            {mode === "agent" && (loading || agentMessages.length > 0) && <div className="conversation">
              <div className="conversation-main">
                {agentMessages.map((message, index) => message.role === "user" ? (
                  <div key={index} className="question-turn"><span>You</span><p>{message.content}</p></div>
                ) : (
                  <div key={index} className="answer-turn">
                    <div className="answer-avatar"><Logo /></div>
                    <div className="answer-body">
                      <span className="answer-label">Entity Intelligence <i>MCP</i></span>
                      <Markdown content={message.content} citations={message.citations ?? []} evidence={evidenceStore} onCitationClick={focusEvidence} />
                      <VerificationBadge verification={message.verification} />
                    </div>
                  </div>
                ))}
                {loading && <ResearchFeed events={events} />}
                {!loading && error && <div className="query-error"><CircleAlert /><div><strong>Request unavailable</strong><p>{error}</p></div></div>}
                <form className="followup-composer" onSubmit={submitFollowup}>
                  <label className="sr-only" htmlFor="followup-question">Continue the conversation</label>
                  <input
                    id="followup-question"
                    value={followup}
                    onChange={(event) => setFollowup(event.target.value)}
                    placeholder="Ask a follow-up…"
                    autoComplete="off"
                  />
                  <button type="submit" disabled={loading || !followup.trim()} aria-label="Send follow-up">
                    {loading ? <Loader2 className="animate-spin" /> : <ArrowUp />}
                  </button>
                </form>
              </div>

              <aside className="source-rail" ref={railRef} aria-label="Sources and method">
                <div className="source-heading"><FileText /> Evidence ledger <span>{Object.keys(evidenceStore).length}</span></div>
                {Object.keys(evidenceStore).length > 0
                  ? <EvidenceList
                      evidence={evidenceStore}
                      facts={factStore}
                      derivations={derivationStore}
                      focusedEvidenceId={focusedEvidenceId}
                      compact
                      contexts={agentMessages
                        .filter((message) => message.role === "assistant")
                        .map((message) => ({ answer: message.content, citations: message.citations ?? [] }))}
                    />
                  : <SourceSkeleton />}
              </aside>
            </div>}
          </section>}
        </div>
      </section>

      <DeveloperPanel
        open={devOpen}
        onClose={() => setDeveloperView(false)}
        spans={trace}
        running={traceRunning}
        question={traceQuestion}
        activity={[...events].reverse().find((event) => event.message)?.message ?? null}
        error={traceError}
        onStartAgent={mode === "agent" ? null : () => changeMode("agent")}
      />
    </main>
  );
}
