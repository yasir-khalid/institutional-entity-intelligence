import { ChevronDown, Database, Fingerprint, GitBranch, SearchCheck } from "lucide-react";
import type { Citation, Evidence } from "@/lib/api";
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
  return { label: "Direct lookup", variant: "neutral" };
}

function cleanClaim(value: string): string {
  return value
    .replace(/\[([^\]]+)\]\([^\)]+\)/g, "$1")
    .replace(/[`*_>#]/g, "")
    .replace(/^[-+\d.)\s]+/, "")
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

function claimsByEvidenceId(contexts: EvidenceAnswerContext[]): Map<string, string[]> {
  const claims = new Map<string, string[]>();
  for (const context of contexts) {
    for (const citation of context.citations) {
      const claim = claimBeforeMarker(context.answer, citation.marker);
      if (!claim) continue;
      const existing = claims.get(citation.evidence_id) ?? [];
      if (!existing.includes(claim)) existing.push(claim);
      claims.set(citation.evidence_id, existing);
    }
  }
  return claims;
}

function methodStepLabel(evidence: Evidence[]): string {
  const sources = evidence.map((item) => item.source.toLowerCase());
  if (evidence.some((item) => item.fact_type === "search_match")) return "Resolved the entity";
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
}: {
  evidence: Evidence;
  highlighted: boolean;
  claims: string[];
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
          {claims.map((claim) => <blockquote key={claim}>{claim}</blockquote>)}
        </div>
      )}

      <FieldGrid>
        <Field label="Lookup">
          <ul className="evidence-criteria">
            {evidence.criteria.map((criterion) => <li key={criterion}>{criterion}</li>)}
          </ul>
        </Field>
        <Field label="Result">
          <span className="tabular">{evidence.result_count ?? "—"} record{evidence.result_count === 1 ? "" : "s"}</span>
        </Field>
        {evidence.source_timestamp && <Field label="Data as of"><span className="tabular">{evidence.source_timestamp}</span></Field>}
      </FieldGrid>

      {evidence.warnings.length > 0 && <p className="evidence-warning">{evidence.warnings.join(" ")}</p>}
      <TechnicalProvenance evidence={evidence} />
    </section>
  );
}

function CompactEvidenceCard({ evidence, highlighted, claims }: { evidence: Evidence; highlighted: boolean; claims: string[] }) {
  const presentation = getEvidencePresentation(evidence);
  return (
    <section id={`evidence-${evidence.evidence_id}`} className={`source-card ${highlighted ? "is-focused" : ""}`}>
      <div className="source-card-head">
        <span className="source-dot" />
        <h3>{evidence.source}</h3>
      </div>
      <span className={`source-kind is-${evidence.fact_type}`}>{presentation.label}</span>
      {claims[0] && <p className="source-card-claim">“{claims[0]}”</p>}
      {evidence.criteria.length > 0 && <p className="source-card-criteria">{evidence.criteria.join(" · ")}</p>}
      <p className="source-card-meta">
        {evidence.result_count ?? "—"} record{evidence.result_count === 1 ? "" : "s"}
        {evidence.source_timestamp ? ` · as of ${evidence.source_timestamp}` : ""}
      </p>
      {evidence.warnings.length > 0 && <p className="source-card-warning">{evidence.warnings.join(" ")}</p>}
    </section>
  );
}

export default function EvidenceList({
  evidence,
  focusedEvidenceId,
  compact = false,
  contexts = [],
}: {
  evidence: Record<string, Evidence>;
  focusedEvidenceId: string | null;
  compact?: boolean;
  contexts?: EvidenceAnswerContext[];
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
          />
        ) : (
          <EvidenceCard
            key={item.evidence_id}
            evidence={item}
            highlighted={item.evidence_id === focusedEvidenceId}
            claims={claimMap.get(item.evidence_id) ?? []}
          />
        ))}
      </div>
      <p className="evidence-footnote"><SearchCheck /> Citations point only to evidence returned by this conversation&apos;s verified data tools.</p>
    </div>
  );
}
