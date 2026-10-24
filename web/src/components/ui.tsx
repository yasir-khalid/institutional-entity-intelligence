"use client";

import type { ReactNode } from "react";

/* ---------------------------------------------------------------------------
   Shared primitives. Every section heading, badge, identifier and label/value
   pair in the app goes through these, so type scale, weight, colour and
   spacing stay identical everywhere instead of drifting per-component.
--------------------------------------------------------------------------- */

/** The one section heading treatment used across the app. */
export function SectionLabel({ children, icon }: { children: ReactNode; icon?: ReactNode }) {
  return (
    <div className="text-ink-subtle flex items-center gap-1.5 text-[11px] font-semibold tracking-[0.08em] uppercase">
      {icon}
      {children}
    </div>
  );
}

/* The app's semantic badge variants live on the shadcn Badge itself so every
   badge in the app resolves to one component and one variant table. */
export { Badge, type BadgeVariant } from "@/components/ui/badge";

/** Identifiers (LEI/CIK/CUSIP/ISIN) - tabular figures so they align when
 * stacked. Deliberately not monospace: the UI has one typeface. */
export function Mono({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`tabular text-[11px] tracking-tight ${className}`}>{children}</span>;
}

/** One label/value pair inside a definition grid. The grid itself owns the
 * column widths so every value in a panel starts on the same x-position. */
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-ink-subtle text-[12px]">{label}</dt>
      <dd className="text-ink text-[12.5px] font-medium">{children}</dd>
    </>
  );
}

export function FieldGrid({ children }: { children: ReactNode }) {
  return <dl className="grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)] items-baseline gap-x-4 gap-y-2">{children}</dl>;
}
