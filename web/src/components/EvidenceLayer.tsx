import { ChevronDown, Database, ExternalLink, Fingerprint, GitBranch, SearchCheck } from "lucide-react";
import { apiUrl, type Citation, type Derivation, type Evidence, type Fact } from "@/lib/api";
import FactValues from "@/components/FactValues";
import { Badge, Field, FieldGrid, Mono, type BadgeVariant } from "@/components/ui";

/* ---------------------------------------------------------------------------
   The user-facing evidence projection. It deliberately separates three ideas:
   claim support (the nearby answer text), source provenance (the evidence
   receipt), and method lineage (a compact grouping of the lookups performed).
   Raw model messages and tool payloads remain in developer observability.
--------------------------------------------------------------------------- */

export interface EvidenceAnswerContext {
  answer: string;
  citations: Citation[];
}

interface EvidencePresentation {
  label: string;
  variant: BadgeVariant;
}

export function getEvidencePresentation(evidence: Evidence): EvidencePresentation {
  if (evidence.fact_type === "search_match") return { label: "Resolution decision", variant: "accent" };
  if (evidence.fact_type === "records") return { label: "Record set", variant: "positive" };
  if (evidence.fact_type === "derivation") return { label: "Calculation", variant: "caution" };
  return { label: "Direct lookup", variant: "neutral" };
}

function cleanClaim(value: string): string {
  return value
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1")
    .replace(/[`*_>#]/g, "")
    // A list marker ("- ", "2. ", "3) "), not any leading digits - "13F
    // filing" must keep its "13".
    .replace(/^\s*(?:[-+]|\d+[.)])\s+/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function claimBeforeMarker(answer: string, marker: number): string | null {
  const markerText = `[${marker}]`;
  const markerIndex = answer.indexOf(markerText);
  if (markerIndex < 0) return null;

  const preceding = answer.slice(0, markerIndex).trimEnd();
  const sentenceStart = Math.max(
    preceding.lastIndexOf(". "),
    preceding.lastIndexOf("! "),
    preceding.lastIndexOf("? "),
    preceding.lastIndexOf("\n"),
  );
  let claim = cleanClaim(preceding.slice(sentenceStart < 0 ? 0 : sentenceStart + 1));
  if (!claim) return null;
  if (claim.length > 190) claim = `…${claim.slice(-187)}`;
  return claim;
}

/** A sentence of the answer that cites a piece of evidence, with the [n]
 * marker it carries there - so a source card can show the same number. */
interface SupportedClaim {
  marker: number;
  text: string;
}

function claimsByEvidenceId(contexts: EvidenceAnswerContext[]): Map<string, SupportedClaim[]> {
  const claims = new Map<string, SupportedClaim[]>();
  for (const context of contexts) {
    for (const citation of context.citations) {
      const text = claimBeforeMarker(context.answer, citation.marker);
      if (!text) continue;
      const existing = claims.get(citation.evidence_id) ?? [];
      if (!existing.some((claim) => claim.text === text)) existing.push({ marker: citation.marker, text });
      claims.set(citation.evidence_id, existing);
    }
  }
  return claims;
}

/** The claims a source backs, each as the answer's own [n] chip followed by
 * the sentence under a highlighter - the same number the reader just saw in
 * the answer, so the two read as one thing rather than a quote in a box. */
function SupportedClaims({ claims, limit }: { claims: SupportedClaim[]; limit?: number }) {
  const shown = limit ? claims.slice(0, limit) : claims;
  if (shown.length === 0) return null;
  return (
    <ul className="supported-claims">
      {shown.map((claim) => (
        <li key={`${claim.marker}-${claim.text}`}>
          <span className="citation is-static" aria-label={`Cited as source ${claim.marker}`}>{claim.marker}</span>
          <span className="supported-claim-text"><mark>{claim.text}</mark></span>
        </li>
      ))}
    </ul>
  );
}

/** A source's coverage, as a glyph: a solid dot is a complete record, a
 * half-filled one a record that is only part of the picture (13F reports
 * long US equity only, say). The same glyph opens the sentence saying what is
 * missing, so the caveat reads as part of the source rather than a warning
 * stapled to it. */
export function CoverageDot({ partial }: { partial: boolean }) {
  return <span className={`source-dot ${partial ? "is-partial" : ""}`} aria-hidden />;
}

export function CoverageNote({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    // A span, not a <p>: it also renders inside an answer paragraph's citation popover.
    <span className="coverage-note">
      <CoverageDot partial />
      <span><strong>Partial view.</strong> {warnings.join(" ")}</span>
    </span>
  );
}

function methodStepLabel(evidence: Evidence[]): string {
  const sources = evidence.map((item) => item.source.toLowerCase());
  if (evidence.some((item) => item.fact_type === "search_match")) return "Resolved the entity";
  if (evidence.some((item) => item.fact_type === "derivation")) return "Calculated from reported rows";
  if (sources.some((source) => source.includes("relationship"))) return "Traced entity relationships";
  if (sources.some((source) => source.includes("entity record"))) return "Read the canonical profile";
  if (sources.some((source) => source.includes("13f"))) return "Read the latest reported filing activity";
  return "Consulted source records";
}

function methodStepResult(evidence: Evidence[]): string {
  const firstCount = evidence[0]?.result_count;
  if (evidence.some((item) => item.fact_type === "search_match")) {
    return `${firstCount ?? 0} candidate${firstCount === 1 ? "" : "s"} returned`;
  }
  if (evidence.length > 1) return `${evidence.length} evidence sections returned`;
  return `${firstCount ?? 0} record${firstCount === 1 ? "" : "s"} returned`;
}

function MethodSummary({ evidence, compact }: { evidence: Evidence[]; compact: boolean }) {
  const grouped = new Map<string, Evidence[]>();
  for (const item of evidence) grouped.set(item.query_hash, [...(grouped.get(item.query_hash) ?? []), item]);
  const steps = [...grouped.entries()];

  return (
    <details className={`method-summary ${compact ? "is-compact" : ""}`}>
      <summary>
        <span className="method-summary-icon"><GitBranch /></span>
        <span className="method-summary-copy">
          <strong>How this answer was produced</strong>
          <small>{steps.length} verified lookup{steps.length === 1 ? "" : "s"}, summarized for readability</small>
        </span>
        <ChevronDown className="method-summary-chevron" />
      </summary>
      <ol className="method-steps">
        {steps.map(([queryHash, receipts], index) => {
          const sources = [...new Set(receipts.map((item) => item.source))];
          return (
            <li key={queryHash}>
              <span className="method-step-index">{index + 1}</span>
              <span>
                <strong>{methodStepLabel(receipts)}</strong>
                <small>{methodStepResult(receipts)} · {sources.join(" · ")}</small>
              </span>
            </li>
          );
        })}
      </ol>
      <p className="method-note">This is a high-level lineage, not the model&apos;s private reasoning or a raw tool log.</p>
    </details>
  );
}

function TechnicalProvenance({ evidence }: { evidence: Evidence }) {
  return (
    <details className="evidence-technical">
      <summary><Fingerprint /> Technical provenance <ChevronDown /></summary>
      <div className="evidence-technical-body">
        {evidence.record_refs.length > 0 && (
          <div>
            <span>Record references</span>
            <div className="evidence-token-list">
              {evidence.record_refs.slice(0, 4).map((ref) => <Mono key={ref}>{ref}</Mono>)}
              {evidence.record_refs.length > 4 && <small>+{evidence.record_refs.length - 4} more</small>}
            </div>
          </div>
        )}
        {evidence.fields_used.length > 0 && (
          <div>
            <span>Fields used</span>
            <div className="evidence-token-list">
              {evidence.fields_used.map((field) => <code key={field}>{field}</code>)}
            </div>
          </div>
        )}
        <div>
          <span>Reproducibility fingerprint</span>
          <Mono>{evidence.query_hash}</Mono>
        </div>
      </div>
    </details>
  );
}

function EvidenceCard({
  evidence,
  highlighted,
  claims,
  facts,
  derivations,
}: {
  evidence: Evidence;
  highlighted: boolean;
  claims: SupportedClaim[];
  facts: Record<string, Fact>;
  derivations: Record<string, Derivation>;
}) {
  const presentation = getEvidencePresentation(evidence);
  return (
    <section id={`evidence-${evidence.evidence_id}`} className={`evidence-receipt ${highlighted ? "is-focused" : ""}`}>
      <header className="evidence-receipt-head">
        <span className="evidence-receipt-icon"><Database /></span>
        <div>
          <h3>{evidence.source}</h3>
          <Badge variant={presentation.variant}>{presentation.label}</Badge>
        </div>
      </header>

      {claims.length > 0 && (
        <div className="evidence-claims">
          <span>Supports in this answer</span>
          <SupportedClaims claims={claims} />
        </div>
      )}

      <FieldGrid>
        <Field label={evidence.fact_type === "derivation" ? "Formula" : "Lookup"}>
          <ul className="evidence-criteria">
            {evidence.criteria.map((criterion) => <li key={criterion}>{criterion}</li>)}
          </ul>
        </Field>
        <Field label="Result">
          <span className="tabular">
            {evidence.result_count ?? "—"} {evidence.fact_type === "derivation" ? "value" : "record"}
            {evidence.result_count === 1 ? "" : "s"}
          </span>
        </Field>
        {evidence.source_timestamp && <Field label="Data as of"><span className="tabular">{evidence.source_timestamp}</span></Field>}
      </FieldGrid>

      <FactValues evidenceId={evidence.evidence_id} facts={facts} derivations={derivations} />
      <CoverageNote warnings={evidence.warnings} />
      {evidence.source_uri && (
        <a className="evidence-source-link" href={apiUrl(evidence.source_uri)} target="_blank" rel="noreferrer">
          Open original{evidence.page ? ` at page ${evidence.page}` : ""} <ExternalLink />
        </a>
      )}
      <TechnicalProvenance evidence={evidence} />
    </section>
  );
}

function CompactEvidenceCard({
  evidence,
  highlighted,
  claims,
  facts,
  derivations,
}: {
  evidence: Evidence;
  highlighted: boolean;
  claims: SupportedClaim[];
  facts: Record<string, Fact>;
  derivations: Record<string, Derivation>;
}) {
  const presentation = getEvidencePresentation(evidence);
  return (
    <section id={`evidence-${evidence.evidence_id}`} className={`source-card ${highlighted ? "is-focused" : ""}`}>
      <div className="source-card-head">
        <CoverageDot partial={evidence.warnings.length > 0} />
        <h3>{evidence.source}</h3>
      </div>
      <SupportedClaims claims={claims} limit={1} />
      {evidence.criteria.length > 0 && <p className="source-card-criteria">{evidence.criteria.join(" · ")}</p>}
      <p className="source-card-meta">
        {presentation.label} · {evidence.result_count ?? "—"} record{evidence.result_count === 1 ? "" : "s"}
        {evidence.source_timestamp ? ` · as of ${evidence.source_timestamp}` : ""}
      </p>
      <FactValues evidenceId={evidence.evidence_id} facts={facts} derivations={derivations} />
      <CoverageNote warnings={evidence.warnings} />
      {evidence.source_uri && (
        <a className="evidence-source-link" href={apiUrl(evidence.source_uri)} target="_blank" rel="noreferrer">
          Open original{evidence.page ? ` at page ${evidence.page}` : ""} <ExternalLink />
        </a>
      )}
    </section>
  );
}

export default function EvidenceList({
  evidence,
  focusedEvidenceId,
  compact = false,
  contexts = [],
  facts = {},
  derivations = {},
}: {
  evidence: Record<string, Evidence>;
  focusedEvidenceId: string | null;
  compact?: boolean;
  contexts?: EvidenceAnswerContext[];
  /** The addressed values the answer stated, shown on the card of the
   * evidence each came from. */
  facts?: Record<string, Fact>;
  derivations?: Record<string, Derivation>;
}) {
  const entries = Object.values(evidence);
  const claimMap = claimsByEvidenceId(contexts);

  if (entries.length === 0) return <p className="text-ink-subtle text-[12.5px]">No evidence yet.</p>;

  return (
    <div className={compact ? "evidence-list is-compact" : "evidence-list"}>
      <MethodSummary evidence={entries} compact={compact} />
      <div className={compact ? "source-cards" : "evidence-receipts"}>
        {entries.map((item) => compact ? (
          <CompactEvidenceCard
            key={item.evidence_id}
            evidence={item}
            highlighted={item.evidence_id === focusedEvidenceId}
            claims={claimMap.get(item.evidence_id) ?? []}
            facts={facts}
            derivations={derivations}
          />
        ) : (
          <EvidenceCard
            key={item.evidence_id}
            evidence={item}
            highlighted={item.evidence_id === focusedEvidenceId}
            claims={claimMap.get(item.evidence_id) ?? []}
            facts={facts}
            derivations={derivations}
          />
        ))}
      </div>
      <p className="evidence-footnote"><SearchCheck /> Citations point only to evidence returned by this conversation&apos;s verified data tools.</p>
    </div>
  );
}
