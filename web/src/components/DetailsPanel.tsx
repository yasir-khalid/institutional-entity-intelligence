"use client";

import { useState } from "react";
import {
  Building2,
  ChevronDown,
  ChevronRight,
  Fingerprint,
  History,
  Info,
  MousePointerClick,
  TrendingUp,
} from "lucide-react";
import type { EntityDetail, EntityIdentifier } from "@/lib/api";
import { Bar } from "@/components/Skeletons";
import LineageTimeline from "@/components/LineageTimeline";
import { Badge, Field, FieldGrid, Mono, SectionLabel, type BadgeVariant } from "@/components/ui";

function formatUsd(value: number | null): string {
  if (value === null) return "—";
  return `$${value.toLocaleString("en-US")}`;
}

function formatTimestamp(value: string | null): string {
  if (!value) return "—";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const CONFIDENCE_VARIANT: Record<string, BadgeVariant> = {
  AUTO_MATCH: "positive",
  REVIEW: "caution",
  SOURCE: "neutral",
};

/** GLEIF LEI registration status - distinct from the entity's own operating
 * status (ACTIVE/INACTIVE) shown in Overview. */
const REGISTRATION_VARIANT: Record<string, BadgeVariant> = {
  ISSUED: "positive",
  LAPSED: "caution",
  PENDING_TRANSFER: "caution",
  PENDING_ARCHIVAL: "caution",
  RETIRED: "neutral",
  ANNULLED: "critical",
  DUPLICATE: "critical",
};

function Section({
  title,
  icon,
  hint,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  /** Right-aligned slot on the heading row - a count, a caption, or a badge. */
  hint?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="border-t border-slate-100 px-5 py-4 first:border-t-0">
      <div className="mb-3 flex items-center justify-between gap-2">
        <SectionLabel icon={icon}>{title}</SectionLabel>
        {typeof hint === "string" ? <span className="text-[10.5px] text-slate-400">{hint}</span> : hint}
      </div>
      {children}
    </section>
  );
}

function DetailsSkeleton() {
  return (
    <div className="flex flex-col gap-5 p-5">
      <div className="flex flex-col gap-2">
        <Bar className="h-5 w-3/4" />
        <Bar className="h-3 w-2/5" />
      </div>
      <div className="grid grid-cols-[7.5rem_1fr] gap-x-4 gap-y-2.5">
        {Array.from({ length: 10 }).map((_, i) => (
          <Bar key={i} className="h-3" />
        ))}
      </div>
      <Bar className="h-20 w-full rounded-lg" />
      <div className="flex flex-col gap-2">
        <Bar className="h-3 w-24" />
        {Array.from({ length: 3 }).map((_, i) => (
          <Bar key={i} className="h-3.5 w-full" />
        ))}
      </div>
    </div>
  );
}

/** One identifier row, expandable to reveal its provenance (source file,
 * snapshot date, ingestion timestamp). Collapsed by default so the list stays
 * scannable, but one click away rather than nowhere at all. */
function IdentifierRow({ identifier }: { identifier: EntityIdentifier }) {
  const [open, setOpen] = useState(false);
  const hasProvenance = Boolean(identifier.source_file || identifier.snapshot_date || identifier.ingested_at);

  return (
    <li className="border-b border-slate-100 last:border-b-0">
      <button
        type="button"
        onClick={() => hasProvenance && setOpen((v) => !v)}
        disabled={!hasProvenance}
        className="group flex w-full items-center gap-2 py-2 text-left transition-colors hover:bg-slate-50/70 disabled:cursor-default disabled:hover:bg-transparent"
      >
        <span className="flex h-4 w-4 shrink-0 items-center justify-center text-slate-300 group-hover:text-slate-400 group-disabled:opacity-0">
          {open ? (
            <ChevronDown className="h-3.5 w-3.5" strokeWidth={2.25} />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" strokeWidth={2.25} />
          )}
        </span>
        <span className="w-11 shrink-0 text-[11px] font-semibold tracking-wide text-slate-500">
          {identifier.identifier_type}
        </span>
        <Mono className="min-w-0 flex-1 truncate text-slate-900">{identifier.identifier_value}</Mono>
        <Badge variant={CONFIDENCE_VARIANT[identifier.confidence] ?? "neutral"}>
          {identifier.confidence === "SOURCE" ? identifier.source : identifier.confidence.replace(/_/g, " ")}
        </Badge>
      </button>

      {open && hasProvenance && (
        <div className="animate-fade-in mb-2 ml-6 rounded-lg bg-slate-50 px-3 py-2.5">
          <dl className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5">
            <dt className="text-[10.5px] text-slate-400">Source</dt>
            <dd className="text-[10.5px] text-slate-700">{identifier.source}</dd>
            <dt className="text-[10.5px] text-slate-400">Source file</dt>
            <dd className="truncate text-[10.5px] text-slate-700" title={identifier.source_file ?? undefined}>
              {identifier.source_file ?? "—"}
            </dd>
            <dt className="text-[10.5px] text-slate-400">Snapshot</dt>
            <dd className="tabular text-[10.5px] text-slate-700">{formatTimestamp(identifier.snapshot_date)}</dd>
            <dt className="text-[10.5px] text-slate-400">Ingested</dt>
            <dd className="tabular text-[10.5px] text-slate-700">{formatTimestamp(identifier.ingested_at)}</dd>
          </dl>
        </div>
      )}
    </li>
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
  if (loading) return <DetailsSkeleton />;

  if (error) {
    return (
      <div className="flex items-start gap-2 p-5 text-[13px] text-rose-600">
        <Info className="mt-0.5 h-4 w-4 shrink-0" strokeWidth={1.75} />
        <span>{error}</span>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2.5 p-8 text-center">
        <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-50 text-slate-300">
          <MousePointerClick className="h-5 w-5" strokeWidth={1.5} />
        </span>
        <p className="text-[12.5px] text-slate-400">Select an entity in the tree to inspect it.</p>
      </div>
    );
  }

  const sec = detail.sec_13f;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <header className="px-5 pt-4 pb-4">
        <div className="flex items-start gap-2.5">
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
            <Building2 className="h-4 w-4" strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <h2 className="text-[15px] leading-snug font-semibold text-slate-900">{detail.canonical_name}</h2>
            <Mono className="mt-0.5 block text-slate-400">{detail.entity_id}</Mono>
          </div>
        </div>
      </header>

      <Section title="Overview" icon={<Info className="h-3 w-3" strokeWidth={2} />}>
        <FieldGrid>
          <Field label="Status">
            <Badge variant={detail.entity_status === "ACTIVE" ? "positive" : "neutral"}>
              {detail.entity_status ?? "unknown"}
            </Badge>
          </Field>
          <Field label="Type">{detail.entity_type ?? "—"}</Field>
          <Field label="Jurisdiction">{detail.jurisdiction ?? "—"}</Field>
          <Field label="Country">{detail.legal_country ?? "—"}</Field>
          <Field label="Parents">
            <span className="tabular">{detail.parent_count}</span>
          </Field>
          <Field label="Subsidiaries">
            <span className="tabular">{detail.subsidiary_count}</span>
          </Field>
        </FieldGrid>
      </Section>

      {detail.lineage && (
        <Section
          title="Lineage"
          icon={<History className="h-3 w-3" strokeWidth={2} />}
          hint={
            detail.lineage.registration_status ? (
              <Badge variant={REGISTRATION_VARIANT[detail.lineage.registration_status] ?? "neutral"}>
                {detail.lineage.registration_status.replace(/_/g, " ")}
              </Badge>
            ) : undefined
          }
        >
          <LineageTimeline lineage={detail.lineage} />
        </Section>
      )}

      <Section
        title="Identifiers"
        icon={<Fingerprint className="h-3 w-3" strokeWidth={2} />}
        hint="click a row for provenance"
      >
        <ul className="-mt-2">
          <li className="border-b border-slate-100">
            <div className="flex items-center gap-2 py-2">
              <span className="h-4 w-4 shrink-0" />
              <span className="w-11 shrink-0 text-[11px] font-semibold tracking-wide text-slate-500">LEI</span>
              <Mono className="min-w-0 flex-1 truncate text-slate-900">{detail.entity_id}</Mono>
              <Badge variant="neutral">gleif</Badge>
            </div>
          </li>
          {detail.identifiers.map((id, i) => (
            <IdentifierRow key={`${id.identifier_type}-${id.identifier_value}-${i}`} identifier={id} />
          ))}
        </ul>
      </Section>

      <Section
        title="SEC 13F activity"
        icon={<TrendingUp className="h-3 w-3" strokeWidth={2} />}
        hint={sec ? `${sec.reported_security_count.toLocaleString()} securities` : undefined}
      >
        {!sec ? (
          <p className="text-[12px] text-slate-400">Not a resolved 13F filer.</p>
        ) : (
          <>
            <FieldGrid>
              <Field label="Filer CIK">
                <Mono className="text-slate-900">{sec.cik}</Mono>
              </Field>
              <Field label="Period">
                <span className="tabular">{sec.latest_period_of_report ?? "—"}</span>
              </Field>
              <Field label="Filed">
                <span className="tabular">{sec.latest_filing_date ?? "—"}</span>
              </Field>
            </FieldGrid>

            <p className="mt-3 rounded-lg bg-amber-50/60 px-2.5 py-2 text-[10.5px] leading-relaxed text-amber-800/80 ring-1 ring-amber-100 ring-inset">
              Latest reported 13F holdings only — excludes short positions, derivatives, non-US securities, private
              investments and sub-threshold positions.
            </p>

            <table className="mt-3 w-full">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="pb-1.5 text-left text-[10px] font-semibold uppercase tracking-[0.06em] text-slate-400">
                    Issuer
                  </th>
                  <th className="pb-1.5 text-right text-[10px] font-semibold uppercase tracking-[0.06em] text-slate-400">
                    Value
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-50">
                {sec.top_reported_holdings.map((h, i) => (
                  <tr key={`${h.name_of_issuer}-${i}`}>
                    <td className="truncate py-1.5 pr-3 text-[12px] text-slate-700" title={h.name_of_issuer}>
                      {h.name_of_issuer}
                    </td>
                    <td className="tabular py-1.5 text-right text-[12px] font-medium text-slate-900">
                      {formatUsd(h.value)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Section>
    </div>
  );
}
