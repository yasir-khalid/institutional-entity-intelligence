"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  BadgeCheck,
  Bot,
  Check,
  ChevronRight,
  Copy,
  Loader2,
  ShieldCheck,
  Sparkles,
  SquareTerminal,
  Wrench,
  X,
  type LucideIcon,
} from "lucide-react";
import type { TraceSpan } from "@/lib/api";

/* ---------------------------------------------------------------------------
   Developer view: the trace of the last agent run, laid out the way Arize
   Phoenix and Langfuse lay out theirs - one agent span at the root, and under
   it every step in the order it happened: LLM calls, tool calls, the
   submit_answer guardrail and the evaluator. They are siblings, not turns: one
   question is one turn, and everything the agent did to answer it is a step
   inside that turn. (Which LLM call asked for a tool is still recorded - see
   `requested_by` - and shown on the tool's span, not drawn as nesting.)

   Each span kind has one icon and one tint, used in the tree and the pane
   alike, so the eye can find "the tool calls" without reading. Select a span
   and its input, output and metadata open beside the tree; payloads render as
   a collapsible key/value tree rather than a wall of JSON. Spans stream in as
   each step completes, so a run that dies still leaves everything up to the
   step that killed it, and a failed run opens on the span that failed.
--------------------------------------------------------------------------- */

type Kind = TraceSpan["kind"] | "agent";

const KINDS: Record<Kind, { label: string; icon: LucideIcon }> = {
  agent: { label: "Agent", icon: Bot },
  llm: { label: "LLM", icon: Sparkles },
  tool: { label: "Tool", icon: Wrench },
  submit: { label: "Guardrail", icon: ShieldCheck },
  verifier: { label: "Evaluator", icon: BadgeCheck },
};

const RUN_ID = "run";

// --- formatting -----------------------------------------------------------

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} s`;
}

function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

function formatCost(value: number): string {
  return `$${value >= 0.01 ? value.toFixed(3) : value.toFixed(5)}`;
}

function formatChars(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M chars`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}k chars`;
  return `${value} chars`;
}

/** "deepseek/deepseek-v4.1-flash" -> "deepseek-v4.1-flash": the vendor prefix
 * is noise once every row already says which kind of span it is. */
function shortModel(name: string): string {
  return name.includes("/") ? name.slice(name.lastIndexOf("/") + 1) : name;
}

// `detail` is kind-specific and arrives untyped over the wire; these read one
// field at a time rather than casting the whole object to a shape it may not
// have.
function field<T>(detail: Record<string, unknown>, key: string): T | undefined {
  const value = detail[key];
  return value === null || value === undefined ? undefined : (value as T);
}

function num(value: unknown): number | undefined {
  return typeof value === "number" ? value : undefined;
}

interface Usage {
  prompt_tokens?: number | null;
  completion_tokens?: number | null;
  reasoning_tokens?: number | null;
  cached_tokens?: number | null;
  cost?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
}

function usageOf(span: TraceSpan): Usage | undefined {
  return field<Usage>(span.detail, "usage");
}

function tokensOf(usage: Usage | undefined): { input: number; output: number } | undefined {
  if (!usage) return undefined;
  const input = num(usage.prompt_tokens) ?? num(usage.input_tokens);
  const output = num(usage.completion_tokens) ?? num(usage.output_tokens);
  if (input === undefined && output === undefined) return undefined;
  return { input: input ?? 0, output: output ?? 0 };
}

function totals(spans: TraceSpan[]) {
  let tokens = 0;
  let cost = 0;
  let sawCost = false;
  for (const span of spans) {
    const usage = usageOf(span);
    const counted = tokensOf(usage);
    if (counted) tokens += counted.input + counted.output;
    const spanCost = num(usage?.cost);
    if (spanCost !== undefined) {
      cost += spanCost;
      sawCost = true;
    }
  }
  return {
    elapsed: spans.reduce((max, span) => Math.max(max, span.start_ms + span.duration_ms), 0),
    llmCalls: spans.filter((span) => span.kind === "llm").length,
    tools: spans.filter((span) => span.kind === "tool").length,
    tokens,
    cost: sawCost ? cost : null,
  };
}

interface RequestedCall {
  name?: string | null;
}

/** The name a span goes by in the tree and the pane header. */
function spanTitle(span: TraceSpan): string {
  if (span.kind === "llm") return shortModel(span.name);
  if (span.kind === "verifier") return "Answer verification";
  return span.name;
}

/** The one-line outcome under a span's name - what it did, not what it was. */
function spanOutcome(span: TraceSpan): string {
  if (span.status === "error") return field<string>(span.detail, "error") ?? span.summary;
  if (span.kind === "llm") {
    const calls = field<RequestedCall[]>(span.detail, "tool_calls") ?? [];
    if (calls.length === 0) return field<string>(span.detail, "content") ? "Replied in text" : "Empty response";
    const counts = new Map<string, number>();
    for (const call of calls) counts.set(call.name ?? "?", (counts.get(call.name ?? "?") ?? 0) + 1);
    return "Called " + [...counts].map(([name, n]) => (n > 1 ? `${name} ×${n}` : name)).join(", ");
  }
  if (span.kind === "submit") return span.status === "rejected" ? `Rejected: ${field<string>(span.detail, "reason") ?? ""}` : span.summary;
  // The verifier's summary is "<headline> \u00b7 <readings>"; the readings are in the pane.
  if (span.kind === "verifier") return span.summary.split(" \u00b7 ")[0];
  return span.summary;
}

// --- shared building blocks ---------------------------------------------------

function KindIcon({ kind, status = "ok" }: { kind: Kind; status?: TraceSpan["status"] }) {
  const { icon: Icon } = KINDS[kind];
  return (
    <span className={`trace-icon is-${kind} is-${status}`} aria-hidden>
      <Icon />
    </span>
  );
}

/** A small label/value pair in a span's header row - latency, tokens, cost,
 * model. `onClick` turns it into a link to another span. */
function Chip({ label, children, tone, onClick }: { label?: string; children: ReactNode; tone?: "danger" | "caution"; onClick?: () => void }) {
  const body = (
    <>
      {label && <span>{label}</span>}
      {children}
    </>
  );
  const className = `trace-chip ${tone ? `is-${tone}` : ""}`;
  return onClick ? (
    <button type="button" className={`${className} is-link`} onClick={onClick}>{body}</button>
  ) : (
    <span className={className}>{body}</span>
  );
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }
  return (
    <button type="button" className="trace-copy" onClick={() => void copy()} aria-label={`Copy ${label.toLowerCase()}`}>
      {copied ? <Check /> : <Copy />}
    </button>
  );
}

/** One titled section of the span pane: Input, Output, Metadata... */
function Section({ title, note, copy, children }: { title: string; note?: ReactNode; copy?: unknown; children: ReactNode }) {
  return (
    <section className="trace-section">
      <header>
        <h4>{title}</h4>
        {note && <small>{note}</small>}
        {copy !== undefined && <CopyButton text={typeof copy === "string" ? copy : JSON.stringify(copy, null, 2)} label={title} />}
      </header>
      {children}
    </section>
  );
}

// --- payloads as a key/value tree -----------------------------------------------

function JsonLeaf({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="json-null">null</span>;
  if (typeof value === "string") return <span className="json-string">{value}</span>;
  if (typeof value === "number") return <span className="json-number">{formatCount(value)}</span>;
  if (typeof value === "boolean") return <span className="json-bool">{String(value)}</span>;
  return <span>{String(value)}</span>;
}

function isBranch(value: unknown): value is Record<string, unknown> | unknown[] {
  return value !== null && typeof value === "object";
}

function entriesOf(value: Record<string, unknown> | unknown[]): [string, unknown][] {
  return Array.isArray(value) ? value.map((item, index) => [String(index), item]) : Object.entries(value);
}

function JsonNode({ name, value, depth, index }: { name: string; value: unknown; depth: number; index: boolean }) {
  // Open the top level, and anything small enough to read at a glance (a
  // tool call's arguments); leave big nested lists folded.
  const size = isBranch(value) ? entriesOf(value).length : 0;
  const [open, setOpen] = useState(depth < 2 || (depth < 4 && size <= 6));
  if (!isBranch(value)) {
    return (
      <li className="json-row">
        <span className={index ? "json-key is-index" : "json-key"}>{name}</span>
        <JsonLeaf value={value} />
      </li>
    );
  }
  const entries = entriesOf(value);
  const count = Array.isArray(value)
    ? `${entries.length} item${entries.length === 1 ? "" : "s"}`
    : `${entries.length} field${entries.length === 1 ? "" : "s"}`;
  return (
    <li className="json-row is-branch">
      <button type="button" className="json-toggle" aria-expanded={open} onClick={() => setOpen(!open)} disabled={entries.length === 0}>
        <ChevronRight />
        <span className={index ? "json-key is-index" : "json-key"}>{name}</span>
        <span className="json-count">{count}</span>
      </button>
      {open && entries.length > 0 && (
        <ul className="json-children">
          {entries.map(([key, item]) => (
            <JsonNode key={key} name={key} value={item} depth={depth + 1} index={Array.isArray(value)} />
          ))}
        </ul>
      )}
    </li>
  );
}

function JsonTree({ value }: { value: unknown }) {
  if (!isBranch(value)) {
    return (
      <div className="json-tree is-leaf">
        <JsonLeaf value={value} />
      </div>
    );
  }
  const entries = entriesOf(value);
  if (entries.length === 0) return <div className="json-tree is-leaf"><span className="json-null">{Array.isArray(value) ? "No items" : "No fields"}</span></div>;
  return (
    <ul className="json-tree">
      {entries.map(([key, item]) => (
        <JsonNode key={key} name={key} value={item} depth={1} index={Array.isArray(value)} />
      ))}
    </ul>
  );
}

function Metadata({ rows }: { rows: [string, ReactNode | undefined][] }) {
  const present = rows.filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (present.length === 0) return null;
  return (
    <Section title="Metadata">
      <dl className="trace-meta">
        {present.map(([label, value]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>{value}</dd>
          </div>
        ))}
      </dl>
    </Section>
  );
}

function ErrorSection({ message }: { message: string }) {
  return (
    <Section title="Error" copy={message}>
      <p className="trace-error-text">{message}</p>
    </Section>
  );
}

// --- per-kind span detail ---------------------------------------------------------

function LlmDetail({ span }: { span: TraceSpan }) {
  const toolCalls = field<unknown[]>(span.detail, "tool_calls") ?? [];
  const content = field<string>(span.detail, "content");
  const error = field<string>(span.detail, "error");
  const forced = field<string>(span.detail, "forced_tool");
  return (
    <>
      {error && <ErrorSection message={error} />}
      {toolCalls.length > 0 && (
        <Section title="Output" note="tool calls requested" copy={toolCalls}>
          <JsonTree value={toolCalls} />
        </Section>
      )}
      {content && (
        <Section title={toolCalls.length > 0 ? "Message" : "Output"} copy={content}>
          <p className="trace-text">{content}</p>
        </Section>
      )}
      <Metadata
        rows={[
          ["Model", span.name],
          ["Tool choice", forced ? `Forced to ${forced}` : "Model's choice"],
          ["Finish reason", field<string>(span.detail, "finish_reason")],
          ["Provider", field<string>(span.detail, "provider")],
          ["Generation", field<string>(span.detail, "generation_id")],
        ]}
      />
    </>
  );
}

interface ResultPreview {
  value: unknown;
  chars: number;
  truncated: boolean;
}

function ToolDetail({ span }: { span: TraceSpan }) {
  const result = field<ResultPreview>(span.detail, "result");
  const evidence = field<Record<string, unknown>[]>(span.detail, "evidence") ?? [];
  const error = field<string>(span.detail, "error");
  const argumentsValue = field(span.detail, "arguments") ?? {};

  return (
    <>
      {error && <ErrorSection message={error} />}
      <Section title="Input" copy={argumentsValue}>
        <JsonTree value={argumentsValue} />
      </Section>
      {result && (
        <Section
          title="Output"
          note={result.truncated ? `preview of ${formatChars(result.chars)}, long lists trimmed` : formatChars(result.chars)}
          copy={result.value ?? undefined}
        >
          {result.value === null ? (
            <p className="trace-empty">Too large to preview ({formatChars(result.chars)}).</p>
          ) : (
            <JsonTree value={result.value} />
          )}
        </Section>
      )}
      {evidence.length > 0 && (
        <Section title="Evidence" note={`${evidence.length} record${evidence.length === 1 ? "" : "s"} the answer may cite`} copy={evidence}>
          <JsonTree value={evidence} />
        </Section>
      )}
    </>
  );
}

function SubmitDetail({ span }: { span: TraceSpan }) {
  const invalid = field<string[]>(span.detail, "invalid_evidence_ids") ?? [];
  const reason = field<string>(span.detail, "reason");
  const answer = field<string>(span.detail, "answer") ?? "";
  const citations = field<unknown[]>(span.detail, "citations") ?? [];
  return (
    <>
      {reason && <ErrorSection message={`Rejected: ${reason}`} />}
      <Section title="Answer" copy={answer}>
        {answer ? <p className="trace-text">{answer}</p> : <p className="trace-empty">No answer text.</p>}
      </Section>
      <Section title="Citations" copy={citations}>
        <JsonTree value={citations} />
      </Section>
      {invalid.length > 0 && (
        <Section title="Dropped as invented" note="cited, but no tool returned them" copy={invalid}>
          <JsonTree value={invalid} />
        </Section>
      )}
    </>
  );
}

interface CheckRow {
  key: string;
  probability: number | null;
  threshold: number;
  passed: boolean | null;
}

function VerifierDetail({ span }: { span: TraceSpan }) {
  const checks = field<CheckRow[]>(span.detail, "checks") ?? [];
  const confidence = num(field(span.detail, "verdict_confidence"));
  const verdict = field<string>(span.detail, "verdict");
  const attempts = num(field(span.detail, "attempts")) ?? 1;
  return (
    <>
      {span.status === "error" && <ErrorSection message={field<string>(span.detail, "reason") ?? span.summary} />}
      {checks.length > 0 && (
        <Section title="Checks" note="reading against the threshold it had to clear">
          <ul className="trace-checks">
            {checks.map((check) => {
              const state = check.passed === null ? "is-unknown" : check.passed ? "is-pass" : "is-fail";
              return (
                <li key={check.key} className={state}>
                  <span>{check.key.replace(/_/g, " ")}</span>
                  <span className="verify-meter" aria-hidden>
                    {check.probability !== null && (
                      <span className="verify-meter-fill" style={{ width: `${check.probability * 100}%` }} />
                    )}
                    <span className="verify-meter-threshold" style={{ left: `${check.threshold * 100}%` }} />
                  </span>
                  <span className="tabular">
                    {check.probability === null ? "no reading" : check.probability.toFixed(2)}
                    <small> / {check.threshold.toFixed(2)}</small>
                  </span>
                </li>
              );
            })}
          </ul>
        </Section>
      )}
      <Metadata
        rows={[
          ["Status", field<string>(span.detail, "status")],
          ["Verdict", verdict && `${verdict}${confidence !== undefined ? ` (${confidence.toFixed(2)})` : ""}`],
          ["Model", span.name],
          // Only worth a row when a transient failure was retried.
          ["Attempts", attempts > 1 ? attempts : undefined],
          ["Reason", span.status === "error" ? undefined : field<string>(span.detail, "reason")],
        ]}
      />
    </>
  );
}

function SpanDetail({ span }: { span: TraceSpan }) {
  if (span.kind === "llm") return <LlmDetail span={span} />;
  if (span.kind === "tool") return <ToolDetail span={span} />;
  if (span.kind === "submit") return <SubmitDetail span={span} />;
  return <VerifierDetail span={span} />;
}

// --- the tree ------------------------------------------------------------------

function TreeRow({
  kind,
  status = "ok",
  title,
  outcome,
  duration,
  selected,
  onSelect,
}: {
  kind: Kind;
  status?: TraceSpan["status"];
  title: string;
  outcome: string | null;
  duration: string | null;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      className={`trace-row is-${status} ${selected ? "is-selected" : ""}`}
      aria-current={selected ? "true" : undefined}
      onClick={onSelect}
    >
      <KindIcon kind={kind} status={status} />
      <span className="trace-row-text">
        <span className="trace-row-line">
          <strong>{title}</strong>
          {duration && <span className="trace-row-duration tabular">{duration}</span>}
        </span>
        {outcome && <small>{outcome}</small>}
      </span>
    </button>
  );
}

// --- the selected span --------------------------------------------------------

function PaneHead({ kind, status = "ok", title, children }: { kind: Kind; status?: TraceSpan["status"]; title: string; children: ReactNode }) {
  return (
    <header className="trace-pane-head">
      <div className="trace-pane-title">
        <KindIcon kind={kind} status={status} />
        <span>{KINDS[kind].label}</span>
        <h3>{title}</h3>
      </div>
      <div className="trace-chips">{children}</div>
    </header>
  );
}

interface ModelView {
  original_chars: number;
  sent_chars: number;
}

function SpanPane({ span, spans, onSelect }: { span: TraceSpan; spans: TraceSpan[]; onSelect: (id: string) => void }) {
  const usage = usageOf(span);
  const tokens = tokensOf(usage);
  const cost = num(usage?.cost);
  const requester = span.requested_by ? spans.find((candidate) => candidate.id === span.requested_by) : undefined;
  const requesterIndex = requester ? spans.filter((candidate) => candidate.kind === "llm").indexOf(requester) + 1 : 0;
  // Set when the model got a trimmed copy - the first thing to check when an
  // answer disagrees with a payload that is visible here in full.
  const sent = field<ModelView>(span.detail, "sent_to_model");
  const records = span.kind === "tool" ? (field<Record<string, unknown>[]>(span.detail, "evidence") ?? [])[0] : undefined;

  return (
    <div className="trace-pane-inner">
      <PaneHead kind={span.kind} status={span.status} title={spanTitle(span)}>
        {span.status !== "ok" && <Chip tone={span.status === "error" ? "danger" : "caution"}>{span.status}</Chip>}
        {span.kind !== "submit" && <Chip label="Latency">{formatDuration(span.duration_ms)}</Chip>}
        <Chip label="At">{formatDuration(span.start_ms)}</Chip>
        {tokens && (
          <Chip label="Tokens">
            {formatCount(tokens.input)} &rarr; {formatCount(tokens.output)}
          </Chip>
        )}
        {cost !== undefined && <Chip label="Cost">{formatCost(cost)}</Chip>}
        {records && num(records.result_count) !== undefined && (
          <Chip label="Records">{formatCount(num(records.result_count) ?? 0)}</Chip>
        )}
        {requester && (
          <Chip label="Requested by" onClick={() => onSelect(requester.id)}>
            LLM call {requesterIndex}
          </Chip>
        )}
        {sent && (
          <Chip label="Model saw" tone="caution">
            {formatChars(sent.sent_chars)} of {formatChars(sent.original_chars)}
          </Chip>
        )}
      </PaneHead>
      <div className="trace-sections">
        <SpanDetail span={span} />
      </div>
    </div>
  );
}

function RunPane({
  spans,
  question,
  running,
  error,
  onSelect,
}: {
  spans: TraceSpan[];
  question: string | null;
  running: boolean;
  error: string | null;
  onSelect: (id: string) => void;
}) {
  const summary = totals(spans);
  const outcome = running
    ? "Running"
    : error
      ? "Failed"
      : spans.some((span) => span.kind === "submit" && span.status === "ok")
        ? "Answered"
        : "Ended without an answer";
  const scale = summary.elapsed;
  return (
    <div className="trace-pane-inner">
      <PaneHead kind="agent" status={error && !running ? "error" : "ok"} title="Agent run">
        <Chip tone={outcome === "Failed" ? "danger" : outcome === "Ended without an answer" ? "caution" : undefined}>{outcome}</Chip>
        <Chip label="Latency">{formatDuration(summary.elapsed)}</Chip>
        <Chip label="Tokens">{formatCount(summary.tokens)}</Chip>
        {summary.cost !== null && <Chip label="Cost">{formatCost(summary.cost)}</Chip>}
      </PaneHead>
      <div className="trace-sections">
        {error && <ErrorSection message={error} />}
        {question && (
          <Section title="Input" copy={question}>
            <p className="trace-text">{question}</p>
          </Section>
        )}
        {spans.length > 0 && (
          <Section title="Timeline" note={`${spans.length} step${spans.length === 1 ? "" : "s"} on one time scale`}>
            <ol className="trace-timeline">
              {spans.map((span) => {
                const left = scale > 0 ? (span.start_ms / scale) * 100 : 0;
                const width = scale > 0 ? (span.duration_ms / scale) * 100 : 0;
                return (
                  <li key={span.id}>
                    <button type="button" className={`is-${span.kind} is-${span.status}`} onClick={() => onSelect(span.id)}>
                      <KindIcon kind={span.kind} status={span.status} />
                      <span className="trace-timeline-name">{spanTitle(span)}</span>
                      <span className="trace-timeline-track" title={`at ${formatDuration(span.start_ms)}, took ${formatDuration(span.duration_ms)}`}>
                        <i style={{ left: `${left}%`, width: `max(2px, ${width}%)` }} />
                      </span>
                      <span className="trace-timeline-duration tabular">{span.kind === "submit" ? "" : formatDuration(span.duration_ms)}</span>
                    </button>
                  </li>
                );
              })}
            </ol>
          </Section>
        )}
      </div>
    </div>
  );
}

export default function DeveloperPanel({
  open,
  onClose,
  spans,
  running,
  question,
  activity,
  error,
  onStartAgent,
}: {
  open: boolean;
  onClose: () => void;
  spans: TraceSpan[];
  running: boolean;
  question: string | null;
  /** The latest progress message, shown while a run is in flight. */
  activity: string | null;
  error: string | null;
  /** Offered from the empty state when nothing has been traced yet. */
  onStartAgent: (() => void) | null;
}) {
  const [selectedId, setSelectedId] = useState<string>(RUN_ID);
  const [seen, setSeen] = useState({ question, error });
  const treeRef = useRef<HTMLDivElement>(null);

  // Adjusted during render rather than in an effect: a new run opens on its
  // root, and a run that fails opens on the span that failed - that is the one
  // you came for. Only when the run fails, not on every span after it.
  if (seen.question !== question || seen.error !== error) {
    setSeen({ question, error });
    if (seen.question !== question) setSelectedId(RUN_ID);
    if (error && seen.error !== error) {
      const failed = [...spans].reverse().find((span) => span.status === "error");
      if (failed) setSelectedId(failed.id);
    }
  }

  // Follow the run as it streams, unless the reader has scrolled up.
  useEffect(() => {
    const tree = treeRef.current;
    if (!tree || !running) return;
    if (tree.scrollHeight - tree.scrollTop - tree.clientHeight < 80) tree.scrollTop = tree.scrollHeight;
  }, [spans.length, running]);

  if (!open) return null;

  const summary = totals(spans);
  const selected = spans.find((span) => span.id === selectedId) ?? null;

  return (
    <aside
      id="developer-panel"
      className="devtools"
      aria-label="Developer view"
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
      }}
    >
      <header className="devtools-head">
        <span className="devtools-head-icon"><SquareTerminal /></span>
        <div>
          <h2>Trace</h2>
          <p>{question ?? "Last agent run"}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="Close developer view"><X /></button>
      </header>

      {spans.length === 0 && !running ? (
        <div className="devtools-empty">
          <p>No agent run traced yet. Every LLM call, tool call and payload for the next run will appear here as it happens.</p>
          {onStartAgent && <button type="button" onClick={onStartAgent}>Switch to Agent mode</button>}
        </div>
      ) : (
        <>
          <dl className="devtools-stats">
            <div><dt>Latency</dt><dd className="tabular">{formatDuration(summary.elapsed)}</dd></div>
            <div><dt>LLM calls</dt><dd className="tabular">{summary.llmCalls}</dd></div>
            <div><dt>Tool calls</dt><dd className="tabular">{summary.tools}</dd></div>
            <div><dt>Tokens</dt><dd className="tabular">{formatCount(summary.tokens)}</dd></div>
            {summary.cost !== null && <div><dt>Cost</dt><dd className="tabular">{formatCost(summary.cost)}</dd></div>}
          </dl>

          <div className="devtools-body">
            <nav className="devtools-tree" aria-label="Trace tree">
              <div className="trace-tree" ref={treeRef}>
                <TreeRow
                  kind="agent"
                  status={error && !running ? "error" : "ok"}
                  title="Agent run"
                  outcome={`${summary.llmCalls} LLM call${summary.llmCalls === 1 ? "" : "s"} · ${summary.tools} tool call${summary.tools === 1 ? "" : "s"}`}
                  duration={formatDuration(summary.elapsed)}
                  selected={selectedId === RUN_ID}
                  onSelect={() => setSelectedId(RUN_ID)}
                />
                <ol className="trace-children">
                  {spans.map((span) => (
                    <li key={span.id}>
                      <TreeRow
                        kind={span.kind}
                        status={span.status}
                        title={spanTitle(span)}
                        outcome={spanOutcome(span)}
                        duration={span.kind === "submit" ? null : formatDuration(span.duration_ms)}
                        selected={span.id === selectedId}
                        onSelect={() => setSelectedId(span.id)}
                      />
                    </li>
                  ))}
                  {running && (
                    <li className="is-pending" aria-live="polite">
                      <span className="trace-row is-pending">
                        <span className="trace-icon is-pending" aria-hidden><Loader2 className="animate-spin" /></span>
                        <span className="trace-row-text"><small>{activity ?? "Running…"}</small></span>
                      </span>
                    </li>
                  )}
                </ol>
              </div>
            </nav>

            <section className="devtools-pane" aria-label="Selected span" key={selectedId}>
              {selected ? (
                <SpanPane span={selected} spans={spans} onSelect={setSelectedId} />
              ) : (
                <RunPane spans={spans} question={question} running={running} error={error} onSelect={setSelectedId} />
              )}
            </section>
          </div>
        </>
      )}
    </aside>
  );
}
