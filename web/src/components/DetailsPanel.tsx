"use client";

import type { EntityDetail } from "@/lib/api";

function formatUsd(value: number | null): string {
  if (value === null) return "-";
  return `$${value.toLocaleString()}`;
}

function SkeletonBar({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded bg-slate-200 ${className}`} />;
}

function DetailsSkeleton() {
  return (
    <div className="flex flex-col gap-4 p-4">
      <div>
        <SkeletonBar className="mb-2 h-5 w-3/4" />
        <SkeletonBar className="h-3 w-1/3" />
      </div>
      <div className="grid grid-cols-2 gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <SkeletonBar key={i} className="h-4 w-full" />
        ))}
      </div>
      <div>
        <SkeletonBar className="mb-2 h-4 w-24" />
        {Array.from({ length: 3 }).map((_, i) => (
          <SkeletonBar key={i} className="mb-1 h-4 w-full" />
        ))}
      </div>
      <div>
        <SkeletonBar className="mb-2 h-4 w-32" />
        {Array.from({ length: 5 }).map((_, i) => (
          <SkeletonBar key={i} className="mb-1 h-4 w-full" />
        ))}
      </div>
    </div>
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

      <div>
        <h3 className="mb-1 text-sm font-semibold text-slate-700">Identifiers</h3>
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
              <td className="pr-2 py-0.5">LEI</td>
              <td className="pr-2 py-0.5 break-all">{detail.entity_id}</td>
              <td className="py-0.5">gleif</td>
            </tr>
            {detail.identifiers.map((id, i) => (
              <tr key={i}>
                <td className="pr-2 py-0.5">{id.identifier_type}</td>
                <td className="pr-2 py-0.5 break-all">{id.identifier_value}</td>
                <td className="py-0.5">{id.source}</td>
              </tr>
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
