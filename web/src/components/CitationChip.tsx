"use client";

import type { Evidence } from "@/lib/api";
import { getEvidencePresentation } from "@/components/EvidenceLayer";

/* ---------------------------------------------------------------------------
   An inline [n] citation marker in an agent answer. Hovering (or keyboard
   focusing) the chip reveals a small provenance card - source, criteria,
   record count, as-of date - anchored to it, so a reader can see where a claim
   came from without travelling to the sources rail. Clicking the chip scrolls
   the sources rail to the matching card and highlights it.

   The reveal is deliberately pure CSS (`:hover` / `:focus-within` on the
   wrapper) rather than React mouse events + a portal + timers: the popover is
   a normal child of the wrapper, so the pointer moving from the chip into the
   card keeps the wrapper hovered and there is no gap, delay, or portal that
   can fail to mount. The card is only rendered when its Evidence is available.
--------------------------------------------------------------------------- */

export default function CitationChip({
  marker,
  evidence,
  onOpen,
}: {
  marker: number;
  evidence: Evidence | undefined;
  onOpen?: (evidenceId: string) => void;
}) {
  const presentation = evidence ? getEvidencePresentation(evidence) : null;
  const open = () => {
    if (evidence) onOpen?.(evidence.evidence_id);
  };

  return (
    <span className="citation-wrap">
      <button type="button" className="citation" onClick={open} aria-label={`Source ${marker}`}>
        {marker}
      </button>

      {evidence && (
        <span className="citation-pop" role="tooltip">
          <span className="citation-pop-head">
            <span className="source-dot" />
            <span className="citation-pop-source">{evidence.source}</span>
          </span>
          {presentation && <span className={`citation-pop-kind is-${evidence.fact_type}`}>{presentation.label}</span>}
          {evidence.criteria[0] && <span className="citation-pop-title">{evidence.criteria[0]}</span>}
          {evidence.criteria.length > 1 && (
            <span className="citation-pop-body">{evidence.criteria.slice(1).join(" · ")}</span>
          )}
          <span className="citation-pop-meta">
            {evidence.result_count ?? "—"} record{evidence.result_count === 1 ? "" : "s"}
            {evidence.source_timestamp ? ` · as of ${evidence.source_timestamp}` : ""}
          </span>
          {evidence.warnings.length > 0 && (
            <span className="citation-pop-warning">{evidence.warnings.join(" ")}</span>
          )}
          {onOpen && (
            <button
              type="button"
              className="citation-pop-link"
              onClick={(event) => {
                event.stopPropagation();
                onOpen(evidence.evidence_id);
              }}
            >
              Inspect evidence →
            </button>
          )}
        </span>
      )}
    </span>
  );
}
