"use client";

import type { EntityLineage } from "@/lib/api";

function formatDate(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "2-digit" });
}

/** GLEIF's own identity timeline for an entity - created, first registered,
 * last updated by its registrar, next renewal due. This data has been in the
 * pipeline since Phase 2 but never reached a consumer before Phase 16. The
 * registration_status badge is rendered by the parent section header, not
 * here, so the timeline itself stays a single clean row of dated points. */
export default function LineageTimeline({ lineage }: { lineage: EntityLineage | null }) {
  if (!lineage) return null;

  const points = [
    { label: "Created", value: lineage.entity_creation_date },
    { label: "Registered", value: lineage.initial_registration_date },
    { label: "Updated", value: lineage.last_update_date },
    { label: "Renewal", value: lineage.next_renewal_date },
  ];

  return (
    <div className="rounded-xl border border-slate-200 px-4 py-3.5">
      <div className="relative">
        <div className="absolute top-[3px] right-[12.5%] left-[12.5%] h-px bg-slate-200" />
        <ol className="relative flex">
          {points.map((p) => (
            <li key={p.label} className="flex flex-1 flex-col items-center gap-1.5 text-center">
              <span
                className={`h-[7px] w-[7px] rounded-full ring-2 ring-white ${
                  p.value ? "bg-indigo-500" : "bg-slate-300"
                }`}
              />
              <span className="text-[9px] font-semibold tracking-[0.06em] text-slate-400 uppercase">{p.label}</span>
              <span className="tabular text-[11px] text-slate-700">{formatDate(p.value)}</span>
            </li>
          ))}
        </ol>
      </div>

      {lineage.gleif_snapshot_date && (
        <p className="mt-3.5 border-t border-slate-100 pt-2.5 text-[10.5px] text-slate-400">
          GLEIF snapshot {formatDate(lineage.gleif_snapshot_date)}
        </p>
      )}
    </div>
  );
}
