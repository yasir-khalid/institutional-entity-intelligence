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
    <div className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.08em] text-slate-400">
      {icon}
      {children}
    </div>
  );
}

const BADGE_VARIANTS = {
  neutral: "bg-slate-100 text-slate-600 ring-slate-200",
  accent: "bg-indigo-50 text-indigo-700 ring-indigo-200",
  positive: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  caution: "bg-amber-50 text-amber-700 ring-amber-200",
  critical: "bg-rose-50 text-rose-700 ring-rose-200",
  upward: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  downward: "bg-violet-50 text-violet-700 ring-violet-200",
} as const;

export type BadgeVariant = keyof typeof BADGE_VARIANTS;

export function Badge({
  children,
  variant = "neutral",
  className = "",
}: {
  children: ReactNode;
  variant?: BadgeVariant;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide ring-1 ring-inset ${BADGE_VARIANTS[variant]} ${className}`}
    >
      {children}
    </span>
  );
}

/** Identifiers (LEI/CIK/CUSIP/ISIN) - always monospace + tabular so they read
 * as codes and align when stacked. */
export function Mono({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`tabular font-mono text-[11px] tracking-tight ${className}`}>{children}</span>;
}

/** One label/value pair inside a definition grid. The grid itself owns the
 * column widths so every value in a panel starts on the same x-position. */
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-[12px] text-slate-500">{label}</dt>
      <dd className="text-[12px] font-medium text-slate-900">{children}</dd>
    </>
  );
}

export function FieldGrid({ children }: { children: ReactNode }) {
  return <dl className="grid grid-cols-[minmax(0,7.5rem)_minmax(0,1fr)] items-baseline gap-x-4 gap-y-2">{children}</dl>;
}
