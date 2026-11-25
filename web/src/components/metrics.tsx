"use client";

import { type ReactNode } from "react";
import {
  ArrowDownRight,
  ArrowUpRight,
  BookOpen,
  Database,
  Info,
  TriangleAlert,
  Minus,
} from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

/**
 * A metric's definition travels with the number, not on a separate
 * "methodology" page. `MetricInfo` is the little (i) beside a figure; it opens
 * a sheet with the measure, the arithmetic, the filed field and the caveats.
 * Every figure that a reader might misread gets one.
 */
export type MetricDefinition = {
  /** The label as it appears beside the number. */
  label: string;
  /** One or two sentences: what this is, in plain language. */
  definition: string;
  /** How the figure is derived, in words or as a short expression. */
  formula?: string;
  /** The filing, register or table the figure comes from. */
  source: string;
  /** The field, item or item column within that source. */
  field?: string;
  /** The observation date the shown value describes. */
  asOf?: string;
  /** What the number is not, or how it is commonly misread. */
  caveats?: string[];
  /** Optional deep link to the public source. */
  href?: string;
  hrefLabel?: string;
  /** Optional value preview shown at the top of the sheet. */
  value?: ReactNode;
};

export function MetricInfo({
  metric,
  className,
}: {
  metric: MetricDefinition;
  className?: string;
}) {
  return (
    <Sheet>
      <SheetTrigger asChild>
        <button
          type="button"
          className={cn("metric-info", className)}
          aria-label={`How ${metric.label} is calculated`}
          title={`How ${metric.label} is calculated`}
        >
          <Info aria-hidden />
        </button>
      </SheetTrigger>
      <SheetContent
        side="right"
        className="metric-sheet w-full sm:max-w-[27rem]"
      >
        <SheetHeader>
          <p className="page-head-eyebrow">Metric note</p>
          <SheetTitle>{metric.label}</SheetTitle>
          <SheetDescription>{metric.definition}</SheetDescription>
        </SheetHeader>
        <div className="metric-sheet-body">
          {metric.value !== undefined && (
            <div className="metric-sheet-value">
              <small>Latest figure</small>
              <strong>{metric.value}</strong>
            </div>
          )}
          {metric.formula && (
            <section className="metric-sheet-block">
              <h3>
                <BookOpen aria-hidden className="size-3.5" /> How it is
                calculated
              </h3>
              <p className="metric-formula">{metric.formula}</p>
            </section>
          )}
          <section className="metric-sheet-block">
            <h3>
              <Database aria-hidden className="size-3.5" /> Source and
              provenance
            </h3>
            <dl className="metric-source">
              <div>
                <dt>Source</dt>
                <dd>{metric.source}</dd>
              </div>
              {metric.field && (
                <div>
                  <dt>Field</dt>
                  <dd>{metric.field}</dd>
                </div>
              )}
              {metric.asOf && (
                <div>
                  <dt>As of</dt>
                  <dd>{metric.asOf}</dd>
                </div>
              )}
            </dl>
          </section>
          {metric.caveats && metric.caveats.length > 0 && (
            <section className="metric-sheet-block">
              <h3>
                <TriangleAlert aria-hidden className="size-3.5" /> Read it
                carefully
              </h3>
              <ul className="metric-caveats">
                {metric.caveats.map((caveat) => (
                  <li key={caveat}>
                    <TriangleAlert aria-hidden />
                    <span>{caveat}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          <div className="metric-sheet-foot">
            {metric.href && (
              <a
                className="workspace-text-link"
                href={metric.href}
                target="_blank"
                rel="noreferrer"
              >
                {metric.hrefLabel ?? "Open the source"} <ArrowUpRight className="size-3" />
              </a>
            )}
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
}

/** A single figure with its definition attached. */
export function MetricCard({
  metric,
  value,
  unit,
  delta,
  deltaNote,
  footnote,
  className,
}: {
  metric: MetricDefinition;
  value: ReactNode;
  unit?: string;
  /** Percent change; null or omitted hides the badge. */
  delta?: number | null;
  deltaNote?: string;
  footnote?: ReactNode;
  className?: string;
}) {
  return (
    <article className={cn("metric-card", className)}>
      <div className="metric-label">
        <span>{metric.label}</span>
        <MetricInfo metric={metric} />
      </div>
      <div className="metric-value">
        {value}
        {unit && <span className="metric-unit">{unit}</span>}
      </div>
      {(delta !== undefined || footnote) && (
        <div className="metric-foot">
          {delta !== undefined && delta !== null && (
            <span
              className={cn(
                "metric-delta",
                delta > 0 ? "is-up" : delta < 0 ? "is-down" : "is-flat",
              )}
            >
              {delta > 0 ? (
                <ArrowUpRight aria-hidden />
              ) : delta < 0 ? (
                <ArrowDownRight aria-hidden />
              ) : (
                <Minus aria-hidden />
              )}
              {delta > 0 ? "+" : ""}
              {delta.toFixed(1)}%
              {deltaNote && <span className="sr-only"> {deltaNote}</span>}
            </span>
          )}
          {footnote && <span>{footnote}</span>}
        </div>
      )}
    </article>
  );
}

export function MetricGrid({ children }: { children: ReactNode }) {
  return <div className="metric-grid">{children}</div>;
}
