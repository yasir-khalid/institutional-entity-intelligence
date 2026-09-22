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

/* Column widths live here, once, and every row renders every cell - including
 * an empty one where a row has no decision badge. That is the whole point:
 * with a conditionally-rendered cell, a single badged row pushes its
 * neighbours' jurisdiction and LEI left by the badge's width, and the table
 * stops lining up down the page. */
const COL_JURISDICTION = "w-16";
const COL_IDENTIFIER = "w-[11.5rem]";
const COL_DECISION = "w-[6.75rem]";

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
              className="group hover:bg-canvas/60 focus-visible:ring-accent focus-visible:ring-inset flex min-h-14 w-full items-center gap-3 px-3.5 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent sm:h-11 sm:min-h-0"
            >
              <span className="bg-canvas text-ink-subtle group-hover:bg-accent-soft group-hover:text-accent group-disabled:group-hover:bg-canvas group-disabled:group-hover:text-ink-subtle flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors">
                <Building2 className="h-3.5 w-3.5" strokeWidth={1.75} />
              </span>

              {/* Columns, not a stacked block: jurisdiction, identifier and
                  decision line up down the list so the eye can scan one field
                  at a time across ten near-identical legal names. */}
              <span className="min-w-0 flex-1">
                <span className="text-ink block truncate text-[13px] font-medium">{r.canonical_name}</span>
                <span className="text-ink-subtle mt-0.5 block truncate text-[11px] sm:hidden">
                  {unresolved
                    ? `CIK ${r.cik} · unresolved`
                    : [r.jurisdiction ?? r.legal_country, r.decision ? (DECISION_LABEL[r.decision] ?? r.decision) : "Candidate"]
                        .filter(Boolean)
                        .join(" · ")}
                </span>
              </span>

              <span className={`text-ink-muted hidden shrink-0 text-[11.5px] sm:block ${COL_JURISDICTION}`}>
                {unresolved ? "—" : (r.jurisdiction ?? "—")}
              </span>

              {unresolved ? (
                <span
                  className={`text-ink-subtle hidden shrink-0 truncate text-[11px] md:block ${COL_IDENTIFIER}`}
                  title={`CIK ${r.cik} · not resolved to a GLEIF LEI`}
                >
                  CIK {r.cik} · unresolved
                </span>
              ) : (
                <Mono className={`text-ink-subtle hidden shrink-0 md:block ${COL_IDENTIFIER}`}>{r.entity_id}</Mono>
              )}

              <span className={`flex shrink-0 justify-end ${COL_DECISION}`}>
                {r.decision && (
                  <Badge variant={DECISION_VARIANT[r.decision] ?? "neutral"}>
                    {DECISION_LABEL[r.decision] ?? r.decision}
                  </Badge>
                )}
              </span>

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
