"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { ArrowRight, ArrowUp, Bot, Building2, Check, CircleAlert, FileText, Loader2, Search, SquareTerminal, Waypoints } from "lucide-react";
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

type Suggestion = { label: string; query: string; mode: ResearchMode };

const SEARCH_SUGGESTIONS: Suggestion[] = [
  { label: "Find a manager", query: "Point72", mode: "search" },
  { label: "Find a fund", query: "BlackRock", mode: "search" },
  { label: "Find an issuer", query: "Apple Inc.", mode: "search" },
];

const AGENT_SUGGESTIONS: Suggestion[] = [
  { label: "Trace ownership", query: "Who ultimately manages Albacore Partners I Master Fund?", mode: "agent" },
  { label: "Check status", query: "What is the registration status of Fred Alger Management?", mode: "agent" },
  { label: "Compare holdings", query: "What was Point72's latest reported holding in Apple?", mode: "agent" },
];

// The landing page names the primary registers and disclosures that the
// platform joins. They are deliberately text rather than third-party logos:
// the treatment reads as research coverage, not as an endorsement by any of
// the source organisations.
const RESEARCH_SOURCES = [
  "GLEIF LEI",
  "SEC 13F",
  "SEC 13D/G",
  "SEC Forms 3/4/5",
  "SEC series & class",
  "EDGAR submissions",
  "SEC N-PORT",
  "OpenFIGI",
  "SEC Form ADV",
  "Companies House",
  "FFIEC NIC",
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

function SearchResults({
  results,
  selectedEntityId,
  onSelect,
}: {
  results: SearchResult[];
  selectedEntityId: string | null;
  onSelect: (entityId: string) => void;
}) {
  if (!results.length) return <EmptyState icon={<Search />} title="No matching entities" text="Try a legal name, jurisdiction, LEI, or CUSIP." />;
  return (
    <div className="candidate-list">
      <table>
        <caption className="sr-only">Entity matches. Select a row to inspect its profile.</caption>
        <thead>
          <tr>
            <th scope="col">Entity</th>
            <th scope="col">Jurisdiction</th>
            <th scope="col">LEI</th>
            <th scope="col">Match</th>
          </tr>
        </thead>
        <tbody>
          {results.map((result) => {
            const status = result.decision === "AUTO_MATCH" ? "Resolved" : result.decision === "REVIEW" ? "Review" : "Candidate";
            const selected = result.entity_id === selectedEntityId;
            return (
              <tr key={result.entity_id} className={selected ? "is-selected" : ""}>
                <td>
                  <button
                    type="button"
                    aria-pressed={selected}
                    onClick={() => onSelect(result.entity_id)}
                    className="candidate-row-select"
                  >
                    <span className="candidate-icon"><Building2 /></span>
                    <span className="candidate-main">
                      <strong>{result.canonical_name}</strong>
                      <small>{selected ? "Viewing profile" : "View profile"}</small>
                    </span>
                  </button>
                </td>
                <td className="candidate-jurisdiction">{result.jurisdiction ?? result.legal_country ?? "Unavailable"}</td>
                <td><code className="candidate-id">{result.entity_id}</code></td>
                <td><span className={`candidate-status ${status.toLowerCase()}`}>{status}</span></td>
              </tr>
            );
          })}
        </tbody>
      </table>
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
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
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
  const threadRef = useRef<HTMLDivElement>(null);
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
  const searchActive = mode === "search" && (loading || searchResults !== null || Boolean(error));
  const canFollowUp = agentMessages.some((message) => message.role === "assistant") && !loading;
  const suggestions = mode === "agent" ? AGENT_SUGGESTIONS : SEARCH_SUGGESTIONS;

  // The thread is its own scrolling region, like a chat application. New
  // status updates and the completed answer stay in view above the composer
  // instead of pushing the input below the browser fold.
  useEffect(() => {
    if (!agentActive) return;
    const frame = window.requestAnimationFrame(() => {
      threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight, behavior: "smooth" });
    });
    return () => window.cancelAnimationFrame(frame);
  }, [agentActive, agentMessages, error, events, loading]);

  function changeMode(nextMode: ResearchMode) {
    setMode(nextMode);
    setError(null);
    setSearchResults(null);
    setSelectedEntityId(null);
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
    if (loading) return;
    setQuery(value);
    setLoading(true);
    setError(null);
    setSearchResults(null);
    setSelectedEntityId(null);
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
        const results = (await search(value, "name")).results;
        setSearchResults(results);
        if (results[0]) void openEntity(results[0].entity_id);
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

  function runSuggestion(suggestion: Suggestion) {
    changeMode(suggestion.mode);
    void runQuery(suggestion.query, suggestion.mode);
  }

  async function openEntity(entityId: string) {
    setSelectedEntityId(entityId);
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
    <main className={`query-app ${hasOutput || loading ? "has-output" : ""} ${searchResults ? "has-search-results" : ""} ${searchActive ? "search-active" : ""} ${agentActive ? "mode-agent" : ""} ${devOpen ? "dev-open" : ""}`}>
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
          <Link href="/how-it-works" className="how-it-works-link">How it works <ArrowRight aria-hidden="true" /></Link>
        </div>

        <div className="query-column">
          {!searchActive && !(mode === "agent" && agentMessages.length > 0) && (
            <div className="query-composer"><SearchBar mode={mode} query={query} loading={loading} onModeChange={changeMode} onQueryChange={setQuery} onSubmit={runQuery} variant={mode === "search" && (searchResults !== null || loading || Boolean(error)) ? "inline" : "landing"} /></div>
          )}

          {!hasOutput && !loading && (
            <section className="source-marquee" aria-label="Research sources">
              <span className="source-marquee-label">Research spans</span>
              <div className="source-marquee-window">
                <div className="source-marquee-track">
                  <div className="source-marquee-list" role="list">
                    {RESEARCH_SOURCES.map((source) => <span key={source} role="listitem">{source}</span>)}
                  </div>
                  <div className="source-marquee-list" aria-hidden="true">
                    {RESEARCH_SOURCES.map((source) => <span key={source}>{source}</span>)}
                  </div>
                </div>
              </div>
            </section>
          )}

          {!hasOutput && !loading && <section className="query-suggestion-block" aria-label={mode === "agent" ? "Suggested research questions" : "Suggested searches"}>
            <p>{mode === "agent" ? "Suggested research questions" : "Suggested searches"}</p>
            <div className={`query-suggestions ${mode === "agent" ? "is-agent" : ""}`}>
              {suggestions.map((suggestion) => <button key={suggestion.label} type="button" onClick={() => runSuggestion(suggestion)}>
                <span>{suggestion.mode === "agent" ? <Bot /> : <Search />}</span><div><small>{suggestion.label}</small><p>{suggestion.query}</p></div>
              </button>)}
            </div>
          </section>}

          {searchActive && <section className="search-shell" aria-label="Entity search workspace">
            <header className="search-command-pane">
              <div className="search-command-copy">
                <span>Entity search</span>
                <p>Resolve a name or identifier, then inspect the selected record.</p>
              </div>
              <div className="query-composer">
                <SearchBar mode="search" query={query} loading={loading} onModeChange={changeMode} onQueryChange={setQuery} onSubmit={runQuery} variant="inline" />
              </div>
            </header>

            <div className="search-workspace">
              <section className="search-list-pane" aria-label="Entity matches" aria-live="polite">
                <div className="search-results-heading">
                  <div>
                    <p className="output-label">Entity matches</p>
                    <h2>{loading ? "Searching…" : `${searchResults?.length ?? 0} result${searchResults?.length === 1 ? "" : "s"}`}</h2>
                  </div>
                  <p>{loading ? "Resolving candidates" : "Select a row to inspect its profile."}</p>
                </div>
                <div className="search-list-scroll">
                  {loading && <div className="query-loading"><Loader2 className="animate-spin" /> Searching entity records…</div>}
                  {!loading && error && <div className="query-error"><CircleAlert /><div><strong>Request unavailable</strong><p>{error}</p></div></div>}
                  {!loading && !error && searchResults && <SearchResults results={searchResults} selectedEntityId={selectedEntityId} onSelect={(entityId) => void openEntity(entityId)} />}
                </div>
              </section>

              <aside className="search-detail-pane" aria-label="Selected entity profile" aria-live="polite">
                <div className="search-selection-heading">
                  <span>Selected record</span>
                  <small>{detail?.canonical_name ?? (detailLoading ? "Opening profile…" : "No entity selected")}</small>
                </div>
                <div className="search-detail-scroll">
                  <EntityProfile detail={detail} loading={detailLoading} onOpenEntity={(entityId) => void openEntity(entityId)} />
                  {!detailLoading && !detail && <EmptyState icon={<Building2 />} title="Select an entity" text="Choose a result to inspect its identifiers, relationships, and filings." />}
                </div>
              </aside>
            </div>
          </section>}

          {(hasOutput || loading) && !searchActive && <section className="query-output" aria-live="polite">

            {mode === "agent" && (loading || agentMessages.length > 0) && <div className="conversation">
              <div className="conversation-main">
                <div className="conversation-thread" ref={threadRef} aria-live="polite">
                {agentMessages.map((message, index) => message.role === "user" ? (
                  <div key={index} className="question-turn"><span>You</span><p>{message.content}</p></div>
                ) : (
                  <div key={index} className="answer-turn">
                    <div className="answer-avatar"><Logo /></div>
                    <div className="answer-body">
                      <span className="answer-label">Researched answer <i>Source-backed</i></span>
                      <Markdown content={message.content} citations={message.citations ?? []} evidence={evidenceStore} onCitationClick={focusEvidence} />
                      <VerificationBadge verification={message.verification} />
                    </div>
                  </div>
                ))}
                {loading && <ResearchFeed events={events} />}
                {!loading && error && <div className="query-error"><CircleAlert /><div><strong>Request unavailable</strong><p>{error}</p><button type="button" onClick={() => void runQuery(query, "agent")}>Try again</button></div></div>}
                </div>
                <form className="followup-composer" onSubmit={submitFollowup}>
                  <label className="sr-only" htmlFor="followup-question">Continue the conversation</label>
                  <input
                    id="followup-question"
                    value={followup}
                    onChange={(event) => setFollowup(event.target.value)}
                    disabled={!canFollowUp}
                    placeholder={loading ? "Researching the response…" : canFollowUp ? "Ask a follow-up…" : "Wait for the response before continuing…"}
                    autoComplete="off"
                  />
                  <div className="followup-toolbar" aria-hidden="true">
                    <span className="followup-tool"><Search /> Research</span>
                    <span className="followup-note">Answers cite source records</span>
                  </div>
                  <button type="submit" disabled={!canFollowUp || !followup.trim()} aria-label={loading ? "Research in progress" : "Send follow-up"}>
                    {loading ? <Loader2 className="animate-spin" /> : <ArrowUp />}
                  </button>
                </form>
              </div>

              <aside className="source-rail" ref={railRef} aria-label="Sources and method">
                <div className="source-heading"><FileText /><strong>Sources</strong><span>{Object.keys(evidenceStore).length}</span></div>
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
