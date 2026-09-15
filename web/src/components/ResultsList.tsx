"use client";

import { Building2, ChevronRight, AlertCircle } from "lucide-react";
import type { SearchResult } from "@/lib/api";
import { Badge, Mono, type BadgeVariant } from "@/components/ui";

const DECISION_VARIANT: Record<string, BadgeVariant> = {
  AUTO_MATCH: "positive",
  REVIEW: "caution",
  UNMATCHED: "critical",
};

const DECISION_LABEL: Record<string, string> = {
  AUTO_MATCH: "Auto match",
  REVIEW: "Review",
  UNMATCHED: "Unmatched",
};

export default function ResultsList({
  results,
  onSelect,
}: {
  results: SearchResult[];
  onSelect: (entityId: string) => void;
}) {
  if (results.length === 0) {
    return (
      <div className="border-line text-ink-subtle flex items-center gap-2 rounded-lg border border-dashed px-4 py-6 text-[13px]">
        <AlertCircle className="h-4 w-4" strokeWidth={1.75} />
        No entities matched that query.
      </div>
    );
  }

  return (
    <ul className="divide-line-soft border-line bg-surface divide-y overflow-hidden rounded-xl border">
      {results.map((r) => {
        const unresolved = r.entity_id.startsWith("unresolved-cik-");
        return (
          <li key={r.entity_id}>
            <button
              onClick={() => onSelect(r.entity_id)}
              disabled={unresolved}
              className="group hover:bg-canvas/60 flex h-11 w-full items-center gap-3 px-3.5 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
            >
              <span className="bg-canvas text-ink-subtle group-hover:bg-accent-soft group-hover:text-accent group-disabled:group-hover:bg-canvas group-disabled:group-hover:text-ink-subtle flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors">
                <Building2 className="h-3.5 w-3.5" strokeWidth={1.75} />
              </span>

              {/* Columns, not a stacked block: the identifier and jurisdiction
                  line up down the list so the eye can scan one field at a time
                  across ten near-identical legal names. */}
              <span className="text-ink min-w-0 flex-1 truncate text-[13px] font-medium">
                {r.canonical_name}
              </span>

              {unresolved ? (
                <span className="text-ink-subtle shrink-0 text-[11px]">
                  CIK {r.cik} · not resolved to a GLEIF LEI
                </span>
              ) : (
                <>
                  <span className="text-ink-muted hidden w-14 shrink-0 text-[11.5px] sm:block">
                    {r.jurisdiction ?? "—"}
                  </span>
                  <Mono className="text-ink-subtle hidden w-[13.5rem] shrink-0 md:block">{r.entity_id}</Mono>
                </>
              )}

              {/* Only the adjudicated decision is surfaced. The raw retrieval
                  score is deliberately not shown: it is an unnormalised BM25
                  value, so a bare "40" means nothing to a reader and the list
                  is already ordered by it. */}
              {r.decision && (
                <Badge variant={DECISION_VARIANT[r.decision] ?? "neutral"}>
                  {DECISION_LABEL[r.decision] ?? r.decision}
                </Badge>
              )}

              <ChevronRight
                className="text-ink-faint group-hover:text-ink-subtle h-4 w-4 shrink-0 transition-colors"
                strokeWidth={2}
              />
            </button>
          </li>
        );
      })}
    </ul>
  );
}
