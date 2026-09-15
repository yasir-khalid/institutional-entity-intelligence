"use client";

import { useState } from "react";
import type { EntityDetail, EntityIdentifier } from "@/lib/api";
import { Bar } from "@/components/Skeletons";
import LineageTimeline from "@/components/LineageTimeline";

function formatUsd(value: number | null): string {
  if (value === null) return "-";
  return `$${value.toLocaleString()}`;
}

function formatDate(value: string | null): string {
  if (!value) return "-";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString();
}

function DetailsSkeleton() {
  return (
    <div className="flex flex-col gap-4 p-4">
      <div>
        <Bar className="mb-2 h-5 w-3/4" />
        <Bar className="h-3 w-1/3" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Bar key={i} className="h-4 w-full" />
        ))}
      </div>
      <Bar className="h-16 w-full rounded-lg" />
      <div>
        <Bar className="mb-2 h-4 w-24" />
        {Array.from({ length: 3 }).map((_, i) => (
          <Bar key={i} className="mb-1 h-4 w-full" />
        ))}
      </div>
      <div>
        <Bar className="mb-2 h-4 w-32" />
        {Array.from({ length: 5 }).map((_, i) => (
          <Bar key={i} className="mb-1 h-4 w-full" />
        ))}
      </div>
    </div>
  );
}

/** One identifier row, expandable to reveal its provenance (source file,
 * snapshot date, ingestion timestamp) - kept collapsed by default so the
 * table stays scannable, but the data is one click away rather than nowhere
 * at all. A chevron ▸/▾ makes the affordance obvious. */
function IdentifierRow({ identifier }: { identifier: EntityIdentifier }) {
  const [open, setOpen] = useState(false);
  const hasProvenance = identifier.source_file || identifier.snapshot_date || identifier.ingested_at;

  return (
    <>
      <tr
        onClick={() => hasProvenance && setOpen((v) => !v)}
        className={hasProvenance ? "cursor-pointer hover:bg-slate-50" : undefined}
      >
        <td className="py-0.5 pr-2">
          <span className="inline-flex items-center gap-1">
            {hasProvenance && <span className="text-[9px] text-slate-400">{open ? "▾" : "▸"}</span>}
            {identifier.identifier_type}
          </span>
        </td>
        <td className="py-0.5 pr-2 break-all">{identifier.identifier_value}</td>
        <td className="py-0.5">{identifier.source}</td>
      </tr>
      {open && hasProvenance && (
        <tr>
          <td colSpan={3} className="bg-slate-50 px-2 py-1.5 text-[10px] text-slate-500">
            <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
              <span className="text-slate-400">Source file</span>
              <span className="break-all">{identifier.source_file ?? "-"}</span>
              <span className="text-slate-400">Snapshot</span>
              <span>{formatDate(identifier.snapshot_date)}</span>
              <span className="text-slate-400">Ingested</span>
              <span>{formatDate(identifier.ingested_at)}</span>
              <span className="text-slate-400">Confidence</span>
              <span>{identifier.confidence}</span>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function DetailsPanel({
  detail,
  loading,
  error,
}: {
  detail: EntityDetail | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return <DetailsSkeleton />;
  }
  if (error) {
    return <div className="p-4 text-sm text-red-600">{error}</div>;
  }
  if (!detail) {
    return <div className="p-4 text-sm text-slate-400">Click a node in the tree to see its details here.</div>;
  }

  return (
    <div className="flex flex-col gap-4 overflow-y-auto p-4">
      <div>
        <h2 className="text-lg font-semibold text-slate-900">{detail.canonical_name}</h2>
        <p className="text-xs text-slate-500">{detail.entity_id}</p>
      </div>

      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="text-slate-500">Status</div>
        <div>{detail.entity_status ?? "-"}</div>
        <div className="text-slate-500">Type</div>
        <div>{detail.entity_type ?? "-"}</div>
        <div className="text-slate-500">Jurisdiction</div>
        <div>{detail.jurisdiction ?? "-"}</div>
        <div className="text-slate-500">Country</div>
        <div>{detail.legal_country ?? "-"}</div>
        <div className="text-slate-500">Parents</div>
        <div>{detail.parent_count}</div>
        <div className="text-slate-500">Subsidiaries / funds</div>
        <div>{detail.subsidiary_count}</div>
      </div>

      <div className="rounded-lg border border-slate-200 p-3">
        <LineageTimeline lineage={detail.lineage} />
      </div>

      <div>
        <h3 className="mb-1 text-sm font-semibold text-slate-700">
          Identifiers <span className="font-normal text-slate-400">(click a row for provenance)</span>
        </h3>
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="pb-1 font-medium">Type</th>
              <th className="pb-1 font-medium">Value</th>
              <th className="pb-1 font-medium">Source</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="py-0.5 pr-2">LEI</td>
              <td className="py-0.5 pr-2 break-all">{detail.entity_id}</td>
              <td className="py-0.5">gleif</td>
            </tr>
            {detail.identifiers.map((id, i) => (
              <IdentifierRow key={i} identifier={id} />
            ))}
          </tbody>
        </table>
      </div>

      <div>
        <h3 className="mb-1 text-sm font-semibold text-slate-700">SEC 13F activity</h3>
        {detail.sec_13f === null ? (
          <p className="text-xs text-slate-400">Not a resolved 13F filer.</p>
        ) : (
          <>
            <p className="text-xs text-slate-600">
              CIK {detail.sec_13f.cik} - latest filing {detail.sec_13f.latest_filing_date ?? "-"} for period{" "}
              {detail.sec_13f.latest_period_of_report ?? "-"} ({detail.sec_13f.reported_security_count} securities)
            </p>
            <p className="mb-1 text-[10px] italic text-slate-400">
              Latest SEC Form 13F reported holdings snapshot - not a complete portfolio (excludes shorts,
              derivatives, non-US securities, private investments, and sub-threshold positions).
            </p>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500">
                  <th className="pb-1 font-medium">Issuer</th>
                  <th className="pb-1 font-medium text-right">Value</th>
                </tr>
              </thead>
              <tbody>
                {detail.sec_13f.top_reported_holdings.map((h, i) => (
                  <tr key={i}>
                    <td className="pr-2 py-0.5">{h.name_of_issuer}</td>
                    <td className="py-0.5 text-right">{formatUsd(h.value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}
