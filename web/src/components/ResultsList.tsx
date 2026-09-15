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
      <div className="flex items-center gap-2 rounded-lg border border-dashed border-slate-200 px-4 py-6 text-[13px] text-slate-400">
        <AlertCircle className="h-4 w-4" strokeWidth={1.75} />
        No entities matched that query.
      </div>
    );
  }

  return (
    <ul className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white">
      {results.map((r) => {
        const unresolved = r.entity_id.startsWith("unresolved-cik-");
        return (
          <li key={r.entity_id}>
            <button
              onClick={() => onSelect(r.entity_id)}
              disabled={unresolved}
              className="group flex h-11 w-full items-center gap-3 px-3.5 text-left transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
            >
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-slate-100 text-slate-400 transition-colors group-hover:bg-indigo-50 group-hover:text-indigo-500 group-disabled:group-hover:bg-slate-100 group-disabled:group-hover:text-slate-400">
                <Building2 className="h-3.5 w-3.5" strokeWidth={1.75} />
              </span>

              {/* Columns, not a stacked block: the identifier and jurisdiction
                  line up down the list so the eye can scan one field at a time
                  across ten near-identical legal names. */}
              <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-slate-900">
                {r.canonical_name}
              </span>

              {unresolved ? (
                <span className="shrink-0 text-[11px] text-slate-400">
                  CIK {r.cik} · not resolved to a GLEIF LEI
                </span>
              ) : (
                <>
                  <span className="hidden w-14 shrink-0 text-[11.5px] text-slate-500 sm:block">
                    {r.jurisdiction ?? "—"}
                  </span>
                  <Mono className="hidden w-[13.5rem] shrink-0 text-slate-400 md:block">{r.entity_id}</Mono>
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
                className="h-4 w-4 shrink-0 text-slate-300 transition-colors group-hover:text-slate-400"
                strokeWidth={2}
              />
            </button>
          </li>
        );
      })}
    </ul>
  );
}
