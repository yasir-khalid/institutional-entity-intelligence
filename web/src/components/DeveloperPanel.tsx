"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Check, ChevronRight, Copy, Loader2, SquareTerminal, X } from "lucide-react";
import type { TraceSpan } from "@/lib/api";

/* ---------------------------------------------------------------------------
   Developer view: the trace of the last agent run, as a tree.

   The shape is the usual one for agent traces: the run at the root, each model
   turn under it, and under each turn the tool calls (and the submit_answer
   gate) that turn asked for - `parent_id` from er.agent.trace. Select a node
   and its span opens in the pane beside the tree. Spans stream in as each step
   completes, so a run that dies still leaves everything up to the step that
   killed it, and a failed run opens on the span that failed.

   Every row is a plain button and every collapse toggle a separate button with
   aria-expanded, so keyboard and screen-reader behaviour is the browser's own
   rather than a hand-rolled tree widget.
--------------------------------------------------------------------------- */

const KIND_TAG: Record<TraceSpan["kind"], string> = {
  llm: "llm",
  tool: "tool",
  submit: "gate",
  verifier: "verify",
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

function totals(spans: TraceSpan[]) {
  let tokens = 0;
  let cost = 0;
  let sawCost = false;
  for (const span of spans) {
    const usage = usageOf(span);
    if (!usage) continue;
    tokens +=
      (num(usage.prompt_tokens) ?? num(usage.input_tokens) ?? 0) +
      (num(usage.completion_tokens) ?? num(usage.output_tokens) ?? 0);
    const spanCost = num(usage.cost);
    if (spanCost !== undefined) {
      cost += spanCost;
      sawCost = true;
    }
  }
  return {
    elapsed: spans.reduce((max, span) => Math.max(max, span.start_ms + span.duration_ms), 0),
    turns: spans.filter((span) => span.kind === "llm").length,
    tools: spans.filter((span) => span.kind === "tool").length,
    tokens,
    cost: sawCost ? cost : null,
  };
}

// --- detail building blocks ------------------------------------------------

function JsonBlock({ label, value, note }: { label: string; value: unknown; note?: ReactNode }) {
  const [copied, setCopied] = useState(false);
  const text = typeof value === "string" ? value : JSON.stringify(value, null, 2);

  async function copy() {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="devtools-block">
      <div className="devtools-block-head">
        <span>{label}</span>
        {note && <small>{note}</small>}
        <button type="button" onClick={() => void copy()} aria-label={`Copy ${label.toLowerCase()}`}>
          {copied ? <Check /> : <Copy />}
        </button>
      </div>
      <pre>{text}</pre>
    </div>
  );
}

function Facts({ rows }: { rows: [string, ReactNode | undefined][] }) {
  const present = rows.filter(([, value]) => value !== undefined && value !== null && value !== "");
  if (present.length === 0) return null;
  return (
    <dl className="devtools-facts">
      {present.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function LlmDetail({ span }: { span: TraceSpan }) {
  const usage = usageOf(span);
  const toolCalls = field<unknown[]>(span.detail, "tool_calls") ?? [];
  const content = field<string>(span.detail, "content");
  const tokens =
    usage && num(usage.prompt_tokens) !== undefined
      ? `${formatCount(usage.prompt_tokens ?? 0)} in · ${formatCount(usage.completion_tokens ?? 0)} out` +
        (num(usage.reasoning_tokens) ? ` · ${formatCount(usage.reasoning_tokens ?? 0)} reasoning` : "") +
        (num(usage.cached_tokens) ? ` · ${formatCount(usage.cached_tokens ?? 0)} cached` : "")
      : undefined;

  return (
    <>
      <Facts
        rows={[
          ["Turn", field<number>(span.detail, "turn")],
          ["Tool choice", field<string>(span.detail, "forced_tool") ? `forced: ${field<string>(span.detail, "forced_tool")}` : "auto"],
          ["Finish", field<string>(span.detail, "finish_reason")],
          ["Provider", field<string>(span.detail, "provider")],
          ["Tokens", tokens],
          ["Cost", num(usage?.cost) !== undefined ? formatCost(usage?.cost ?? 0) : undefined],
          ["Generation", field<string>(span.detail, "generation_id") && <code>{field<string>(span.detail, "generation_id")}</code>],
          ["Error", field<string>(span.detail, "error")],
        ]}
      />
      {toolCalls.length > 0 && <JsonBlock label="Requested tool calls" value={toolCalls} />}
      {content && <JsonBlock label="Message content" value={content} />}
    </>
  );
}

interface ResultPreview {
  value: unknown;
  chars: number;
  truncated: boolean;
}

interface ModelView {
  original_chars: number;
  sent_chars: number;
}

function ToolDetail({ span }: { span: TraceSpan }) {
  const result = field<ResultPreview>(span.detail, "result");
  const evidence = field<Record<string, unknown>[]>(span.detail, "evidence") ?? [];
  const error = field<string>(span.detail, "error");
  // Set when the model got a trimmed copy - the first thing to check when an
  // answer disagrees with a payload that is visible here in full.
  const sent = field<ModelView>(span.detail, "sent_to_model");

  return (
    <>
      <JsonBlock label="Arguments" value={field(span.detail, "arguments") ?? {}} />
      {error && <Facts rows={[["Error", error]]} />}
      {sent && (
        <p className="devtools-note">
          The model received a trimmed copy: {formatChars(sent.sent_chars)} of {formatChars(sent.original_chars)}, long
          lists cut with each elision marked. It was told to take counts from the evidence, not the list.
        </p>
      )}
      {evidence.length > 0 && <JsonBlock label="Evidence returned" value={evidence} />}
      {result &&
        (result.value === null ? (
          <p className="devtools-note">Result too large to preview ({formatChars(result.chars)}).</p>
        ) : (
          <JsonBlock
            label="Result"
            value={result.value}
            note={
              result.truncated
                ? `preview of ${formatChars(result.chars)} · long lists trimmed, elisions marked`
                : formatChars(result.chars)
            }
          />
        ))}
    </>
  );
}

function SubmitDetail({ span }: { span: TraceSpan }) {
  const invalid = field<string[]>(span.detail, "invalid_evidence_ids") ?? [];
  return (
    <>
      <Facts rows={[["Reason", field<string>(span.detail, "reason")]]} />
      <JsonBlock label="Answer" value={field<string>(span.detail, "answer") ?? ""} />
      <JsonBlock label="Citations" value={field(span.detail, "citations") ?? []} />
      {invalid.length > 0 && <JsonBlock label="Dropped as invented" value={invalid} />}
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
  const usage = usageOf(span);
  const confidence = num(field(span.detail, "verdict_confidence"));
  return (
    <>
      <Facts
        rows={[
          ["Status", field<string>(span.detail, "status")],
          ["Verdict", field<string>(span.detail, "verdict") && `${field<string>(span.detail, "verdict")}${confidence !== undefined ? ` (${confidence.toFixed(2)})` : ""}`],
          ["Tokens", usage && num(usage.input_tokens) !== undefined ? `${formatCount(usage.input_tokens ?? 0)} in` : undefined],
          ["Cost", num(usage?.cost) !== undefined ? formatCost(usage?.cost ?? 0) : undefined],
          // Only worth a row when a transient failure was retried.
          ["Attempts", (num(field(span.detail, "attempts")) ?? 1) > 1 ? num(field(span.detail, "attempts")) : undefined],
          ["Reason", field<string>(span.detail, "reason")],
        ]}
      />
      {checks.length > 0 && (
        <table className="devtools-checks">
          <thead>
            <tr><th>Check</th><th>Reading</th><th>Threshold</th><th /></tr>
          </thead>
          <tbody>
            {checks.map((check) => (
              <tr key={check.key} className={check.passed === false ? "is-fail" : undefined}>
                <td><code>{check.key}</code></td>
                <td>{check.probability === null ? "—" : check.probability.toFixed(2)}</td>
                <td>{check.threshold.toFixed(2)}</td>
                <td>{check.passed === null ? "no reading" : check.passed ? "pass" : "fail"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
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

interface TreeNode {
  span: TraceSpan;
  children: TreeNode[];
}

/** Nest spans under their parents, keeping stream order at every level. A span
 * whose parent hasn't arrived (it can't, today - parents are emitted first) is
 * shown at the top level rather than dropped. */
function buildTree(spans: TraceSpan[]): TreeNode[] {
  const nodes = new Map(spans.map((span) => [span.id, { span, children: [] as TreeNode[] }]));
  const roots: TreeNode[] = [];
  for (const span of spans) {
    const node = nodes.get(span.id)!;
    const parent = span.parent_id ? nodes.get(span.parent_id) : undefined;
    (parent ? parent.children : roots).push(node);
  }
  return roots;
}

interface Row {
  node: TreeNode;
  depth: number;
}

function visibleRows(nodes: TreeNode[], collapsed: Set<string>, depth = 1): Row[] {
  return nodes.flatMap((node) => [
    { node, depth },
    ...(collapsed.has(node.span.id) ? [] : visibleRows(node.children, collapsed, depth + 1)),
  ]);
}

function spanLabel(span: TraceSpan): { title: string; meta: string | null } {
  if (span.kind === "llm") {
    const turn = field<number>(span.detail, "turn");
    return { title: turn ? `Turn ${turn}` : "Model turn", meta: span.name };
  }
  if (span.kind === "verifier") return { title: "Verification", meta: span.name };
  return { title: span.name, meta: null };
}

function TimeBar({ start, duration, scale }: { start: number; duration: number; scale: number }) {
  const left = scale > 0 ? (start / scale) * 100 : 0;
  const width = scale > 0 ? (duration / scale) * 100 : 0;
  return (
    <span className="devtools-bar" title={`started at ${formatDuration(start)} \u00b7 took ${formatDuration(duration)}`}>
      <i style={{ left: `${left}%`, width: `max(2px, ${width}%)` }} />
    </span>
  );
}

function TreeRow({
  row,
  scale,
  selected,
  collapsed,
  onSelect,
  onToggle,
}: {
  row: Row;
  scale: number;
  selected: boolean;
  collapsed: boolean;
  onSelect: () => void;
  onToggle: () => void;
}) {
  const { span, children } = row.node;
  const { title, meta } = spanLabel(span);
  return (
    <li className={`devtools-node is-${span.status} ${selected ? "is-selected" : ""}`} style={{ ["--depth" as string]: row.depth }}>
      {children.length > 0 ? (
        <button
          type="button"
          className={`devtools-twisty ${collapsed ? "" : "is-open"}`}
          aria-expanded={!collapsed}
          aria-label={`${collapsed ? "Expand" : "Collapse"} ${title}`}
          onClick={onToggle}
        >
          <ChevronRight />
        </button>
      ) : (
        <span className="devtools-twisty" aria-hidden />
      )}
      <button type="button" className="devtools-node-main" aria-current={selected ? "true" : undefined} onClick={onSelect}>
        <span className="devtools-node-line">
          <code className="devtools-kind">{KIND_TAG[span.kind]}</code>
          <strong>{title}</strong>
          {meta && <small>{meta}</small>}
          <span className="devtools-duration">{span.kind === "submit" ? "\u2014" : formatDuration(span.duration_ms)}</span>
        </span>
        <TimeBar start={span.start_ms} duration={span.duration_ms} scale={scale} />
      </button>
    </li>
  );
}

// --- the selected span --------------------------------------------------------

function SpanPane({ span }: { span: TraceSpan }) {
  const { title, meta } = spanLabel(span);
  return (
    <div className="devtools-pane-inner">
      <div className="devtools-pane-head">
        <code className="devtools-kind">{KIND_TAG[span.kind]}</code>
        <h3>{title}</h3>
        {span.status !== "ok" && <span className={`devtools-status is-${span.status}`}>{span.status}</span>}
      </div>
      <p className="devtools-pane-meta">
        {meta && <>{meta} · </>}started at {formatDuration(span.start_ms)}
        {span.kind !== "submit" && <> · took {formatDuration(span.duration_ms)}</>}
      </p>
      <p className={`devtools-pane-summary is-${span.status}`}>{span.summary}</p>
      <div className="devtools-detail">
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
  const outcome = running ? "Running" : error ? "Failed" : spans.some((span) => span.kind === "submit" && span.status === "ok") ? "Answered" : "Ended without an answer";
  return (
    <div className="devtools-pane-inner">
      <div className="devtools-pane-head">
        <code className="devtools-kind">run</code>
        <h3>{question ?? "Agent run"}</h3>
      </div>
      <Facts
        rows={[
          ["Outcome", outcome],
          ["Error", error ?? undefined],
          ["Elapsed", formatDuration(summary.elapsed)],
          ["Model turns", summary.turns],
          ["Tool calls", summary.tools],
          ["Tokens", formatCount(summary.tokens)],
          ["Cost", summary.cost !== null ? formatCost(summary.cost) : undefined],
        ]}
      />
      {spans.length > 0 && (
        <div className="devtools-timeline">
          <span className="devtools-section-label">Timeline</span>
          <ol>
            {spans.map((span) => (
              <li key={span.id} className={`is-${span.status}`}>
                <button type="button" onClick={() => onSelect(span.id)}>
                  <span>{spanLabel(span).title}</span>
                  <TimeBar start={span.start_ms} duration={span.duration_ms} scale={summary.elapsed} />
                  <small>{span.kind === "submit" ? "\u2014" : formatDuration(span.duration_ms)}</small>
                </button>
              </li>
            ))}
          </ol>
        </div>
      )}
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
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const treeRef = useRef<HTMLOListElement>(null);

  // A new run opens on its root, fully expanded.
  useEffect(() => {
    setSelectedId(RUN_ID);
    setCollapsed(new Set());
  }, [question]);

  // A failed run opens on the span that failed - that is the one you came for.
  useEffect(() => {
    if (!error) return;
    const failed = [...spans].reverse().find((span) => span.status === "error");
    if (failed) setSelectedId(failed.id);
    // Only when the run fails, not on every span that arrives afterwards.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [error]);

  // Follow the run as it streams, unless the reader has scrolled up.
  useEffect(() => {
    const tree = treeRef.current;
    if (!tree || !running) return;
    if (tree.scrollHeight - tree.scrollTop - tree.clientHeight < 80) tree.scrollTop = tree.scrollHeight;
  }, [spans.length, running]);

  const tree = useMemo(() => buildTree(spans), [spans]);
  const rows = useMemo(() => visibleRows(tree, collapsed), [tree, collapsed]);

  if (!open) return null;

  const summary = totals(spans);
  const selected = spans.find((span) => span.id === selectedId) ?? null;
  const toggle = (id: string) =>
    setCollapsed((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

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
          <p>No agent run traced yet. Every model turn, tool call and payload for the next run will appear here as it happens.</p>
          {onStartAgent && <button type="button" onClick={onStartAgent}>Switch to Agent mode</button>}
        </div>
      ) : (
        <>
          <dl className="devtools-stats">
            <div><dt>Elapsed</dt><dd>{formatDuration(summary.elapsed)}</dd></div>
            <div><dt>Turns</dt><dd>{summary.turns}</dd></div>
            <div><dt>Tool calls</dt><dd>{summary.tools}</dd></div>
            <div><dt>Tokens</dt><dd>{formatCount(summary.tokens)}</dd></div>
            {summary.cost !== null && <div><dt>Cost</dt><dd>{formatCost(summary.cost)}</dd></div>}
          </dl>

          <div className="devtools-body">
            <nav className="devtools-tree" aria-label="Trace tree">
              <ol ref={treeRef}>
                <li className={`devtools-node is-root ${selectedId === RUN_ID ? "is-selected" : ""}`} style={{ ["--depth" as string]: 0 }}>
                  <span className="devtools-twisty" aria-hidden />
                  <button
                    type="button"
                    className="devtools-node-main"
                    aria-current={selectedId === RUN_ID ? "true" : undefined}
                    onClick={() => setSelectedId(RUN_ID)}
                  >
                    <span className="devtools-node-line">
                      <code className="devtools-kind">run</code>
                      <strong>Agent run</strong>
                      <span className="devtools-duration">{formatDuration(summary.elapsed)}</span>
                    </span>
                  </button>
                </li>
                {rows.map((row) => (
                  <TreeRow
                    key={row.node.span.id}
                    row={row}
                    scale={summary.elapsed}
                    selected={row.node.span.id === selectedId}
                    collapsed={collapsed.has(row.node.span.id)}
                    onSelect={() => setSelectedId(row.node.span.id)}
                    onToggle={() => toggle(row.node.span.id)}
                  />
                ))}
              </ol>
              {(running || error) && (
                <footer className={`devtools-foot ${error && !running ? "is-error" : ""}`} aria-live="polite">
                  {running ? <Loader2 className="animate-spin" /> : null}
                  <span>{running ? activity ?? "Running\u2026" : `Run failed: ${error}`}</span>
                </footer>
              )}
            </nav>

            <section className="devtools-pane" aria-label="Selected span" key={selectedId}>
              {selected ? (
                <SpanPane span={selected} />
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
