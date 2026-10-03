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

/* Each variant is a tinted surface + a same-hue text colour dark enough to
   read on it (700/800, not 600) + a ring one step stronger than the fill, so
   badges hold their shape against both white cards and the canvas. */
const BADGE_VARIANTS = {
  neutral: "bg-slate-100 text-slate-700 ring-slate-300/70",
  accent: "bg-indigo-50 text-indigo-700 ring-indigo-300/70",
  positive: "bg-emerald-50 text-emerald-800 ring-emerald-300/70",
  caution: "bg-amber-50 text-amber-800 ring-amber-300/70",
  critical: "bg-rose-50 text-rose-700 ring-rose-300/70",
  upward: "bg-emerald-50 text-emerald-800 ring-emerald-300/70",
  downward: "bg-violet-50 text-violet-800 ring-violet-300/70",
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
