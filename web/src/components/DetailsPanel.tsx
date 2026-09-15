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
    <section className="border-line-soft border-t px-5 py-4 first:border-t-0">
      <div className="mb-3 flex items-center justify-between gap-2">
        <SectionLabel icon={icon}>{title}</SectionLabel>
        {typeof hint === "string" ? <span className="text-ink-subtle text-[11px]">{hint}</span> : hint}
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
    <li className="border-line-soft border-b last:border-b-0">
      <button
        type="button"
        onClick={() => hasProvenance && setOpen((v) => !v)}
        disabled={!hasProvenance}
        className="hover:bg-canvas/60 group flex w-full items-center gap-2 py-2 text-left transition-colors disabled:cursor-default disabled:hover:bg-transparent"
      >
        <span className="text-ink-faint group-hover:text-ink-subtle flex h-4 w-4 shrink-0 items-center justify-center group-disabled:opacity-0">
          {open ? (
            <ChevronDown className="h-3.5 w-3.5" strokeWidth={2.25} />
          ) : (
            <ChevronRight className="h-3.5 w-3.5" strokeWidth={2.25} />
          )}
        </span>
        <span className="text-ink-subtle w-11 shrink-0 text-[11px] font-semibold tracking-wide">
          {identifier.identifier_type}
        </span>
        <Mono className="text-ink min-w-0 flex-1 truncate">{identifier.identifier_value}</Mono>
        <Badge variant={CONFIDENCE_VARIANT[identifier.confidence] ?? "neutral"}>
          {identifier.confidence === "SOURCE" ? identifier.source : identifier.confidence.replace(/_/g, " ")}
        </Badge>
      </button>

      {open && hasProvenance && (
        <div className="animate-fade-in bg-canvas/70 mb-2 ml-6 rounded-lg px-3 py-2.5">
          <dl className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5">
            <dt className="text-ink-subtle text-[11px]">Source</dt>
            <dd className="text-ink-muted text-[11px]">{identifier.source}</dd>
            <dt className="text-ink-subtle text-[11px]">Source file</dt>
            <dd className="text-ink-muted truncate text-[11px]" title={identifier.source_file ?? undefined}>
              {identifier.source_file ?? "—"}
            </dd>
            <dt className="text-ink-subtle text-[11px]">Snapshot</dt>
            <dd className="tabular text-ink-muted text-[11px]">{formatTimestamp(identifier.snapshot_date)}</dd>
            <dt className="text-ink-subtle text-[11px]">Ingested</dt>
            <dd className="tabular text-ink-muted text-[11px]">{formatTimestamp(identifier.ingested_at)}</dd>
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
        <span className="bg-canvas text-ink-subtle flex h-10 w-10 items-center justify-center rounded-xl">
          <MousePointerClick className="h-5 w-5" strokeWidth={1.5} />
        </span>
        <p className="text-ink-subtle text-[12.5px]">Select an entity in the tree to inspect it.</p>
      </div>
    );
  }

  const sec = detail.sec_13f;

  return (
    <div className="scroll-thin h-full overflow-y-auto">
      <header className="px-5 pt-4 pb-4">
        <div className="flex items-start gap-2.5">
          <span className="bg-accent-soft text-accent mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg">
            <Building2 className="h-4 w-4" strokeWidth={1.75} />
          </span>
          <div className="min-w-0">
            <h2 className="text-ink text-[15px] leading-snug font-semibold">{detail.canonical_name}</h2>
            <Mono className="text-ink-subtle mt-0.5 block">{detail.entity_id}</Mono>
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
          <li className="border-line-soft border-b">
            <div className="flex items-center gap-2 py-2">
              <span className="h-4 w-4 shrink-0" />
              <span className="text-ink-subtle w-11 shrink-0 text-[11px] font-semibold tracking-wide">LEI</span>
              <Mono className="text-ink min-w-0 flex-1 truncate">{detail.entity_id}</Mono>
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
          <p className="text-ink-subtle text-[12px]">Not a resolved 13F filer.</p>
        ) : (
          <>
            <FieldGrid>
              <Field label="Filer CIK">
                <Mono className="text-ink">{sec.cik}</Mono>
              </Field>
              <Field label="Period">
                <span className="tabular">{sec.latest_period_of_report ?? "—"}</span>
              </Field>
              <Field label="Filed">
                <span className="tabular">{sec.latest_filing_date ?? "—"}</span>
              </Field>
            </FieldGrid>

            <p className="mt-3 rounded-lg bg-amber-50 px-2.5 py-2 text-[11px] leading-relaxed text-amber-900 ring-1 ring-amber-200/70 ring-inset">
              Latest reported 13F holdings only — excludes short positions, derivatives, non-US securities, private
              investments and sub-threshold positions.
            </p>

            <table className="mt-3 w-full">
              <thead>
                <tr className="border-line-soft border-b">
                  <th className="text-ink-subtle pb-1.5 text-left text-[10px] font-semibold tracking-[0.06em] uppercase">
                    Issuer
                  </th>
                  <th className="text-ink-subtle pb-1.5 text-right text-[10px] font-semibold tracking-[0.06em] uppercase">
                    Value
                  </th>
                </tr>
              </thead>
              <tbody className="divide-line-soft divide-y">
                {sec.top_reported_holdings.map((h, i) => (
                  <tr key={`${h.name_of_issuer}-${i}`}>
                    <td className="text-ink-muted truncate py-1.5 pr-3 text-[12px]" title={h.name_of_issuer}>
                      {h.name_of_issuer}
                    </td>
                    <td className="tabular text-ink py-1.5 text-right text-[12px] font-medium">
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
