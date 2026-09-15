"use client";

import type { EntityLineage } from "@/lib/api";

function formatDate(value: string | null): string {
  if (!value) return "-";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

const STATUS_COLOR: Record<string, string> = {
  ISSUED: "bg-green-100 text-green-700",
  LAPSED: "bg-amber-100 text-amber-700",
  RETIRED: "bg-slate-200 text-slate-600",
  ANNULLED: "bg-red-100 text-red-700",
};

/** Renders GLEIF's own identity timeline for an entity - when it was created,
 * first registered, last updated by the issuing registrar, and next due for
 * renewal. This data existed in the pipeline since Phase 2 but never reached
 * any consumer before now (see docs/phases.md Phase 16) - "entity identity,
 * lineage, provenance" is durable, foundational data that deserves to
 * actually be visible, not just captured at ingestion time. */
export default function LineageTimeline({ lineage }: { lineage: EntityLineage | null }) {
  if (!lineage) return null;

  const points = [
    { label: "Created", value: lineage.entity_creation_date },
    { label: "Registered", value: lineage.initial_registration_date },
    { label: "Last updated", value: lineage.last_update_date },
    { label: "Renewal due", value: lineage.next_renewal_date },
  ];

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-700">Lineage</h3>
        {lineage.registration_status && (
          <span
            className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
              STATUS_COLOR[lineage.registration_status] ?? "bg-slate-100 text-slate-600"
            }`}
          >
            {lineage.registration_status}
          </span>
        )}
      </div>

      <div className="relative flex justify-between pt-1">
        <div className="absolute top-[13px] right-4 left-4 h-px bg-slate-200" />
        {points.map((p) => (
          <div key={p.label} className="relative z-10 flex flex-1 flex-col items-center text-center">
            <span className={`h-2 w-2 rounded-full ${p.value ? "bg-blue-600" : "bg-slate-300"}`} />
            <span className="mt-1.5 text-[9px] font-medium uppercase tracking-wide text-slate-400">{p.label}</span>
            <span className="text-[11px] text-slate-700">{formatDate(p.value)}</span>
          </div>
        ))}
      </div>

      {lineage.gleif_snapshot_date && (
        <p className="mt-2 text-[10px] text-slate-400">As of GLEIF snapshot {formatDate(lineage.gleif_snapshot_date)}</p>
      )}
    </div>
  );
}
