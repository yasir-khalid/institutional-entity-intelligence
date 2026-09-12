"use client";

import type { SearchResult } from "@/lib/api";

const DECISION_COLOR: Record<string, string> = {
  AUTO_MATCH: "text-green-700 bg-green-50",
  REVIEW: "text-amber-700 bg-amber-50",
  UNMATCHED: "text-red-700 bg-red-50",
};

export default function ResultsList({
  results,
  onSelect,
}: {
  results: SearchResult[];
  onSelect: (entityId: string) => void;
}) {
  if (results.length === 0) {
    return <p className="text-sm text-slate-400">No results.</p>;
  }

  return (
    <ul className="flex flex-col divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
      {results.map((r) => (
        <li key={r.entity_id}>
          <button
            onClick={() => onSelect(r.entity_id)}
            disabled={r.entity_id.startsWith("unresolved-cik-")}
            className="flex w-full items-center justify-between px-4 py-2.5 text-left hover:bg-slate-50 disabled:opacity-40"
          >
            <div>
              <div className="text-sm font-medium text-slate-900">{r.canonical_name}</div>
              <div className="text-xs text-slate-500">
                {r.entity_id.startsWith("unresolved-cik-") ? `CIK ${r.cik} (not resolved to a GLEIF LEI)` : r.entity_id}
                {r.jurisdiction ? ` · ${r.jurisdiction}` : ""}
              </div>
            </div>
            {r.decision ? (
              <span className={`rounded px-2 py-0.5 text-xs font-medium ${DECISION_COLOR[r.decision] ?? ""}`}>
                {r.decision}
              </span>
            ) : r.score !== null ? (
              <span className="text-xs text-slate-400">score {r.score.toFixed(0)}</span>
            ) : null}
          </button>
        </li>
      ))}
    </ul>
  );
}
