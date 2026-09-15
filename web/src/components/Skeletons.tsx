"use client";

import type { CSSProperties } from "react";

/* ---------------------------------------------------------------------------
   Loading states.

   Deliberately not the default "randomly-sized grey bars pulsing in unison"
   treatment. Two rules here:

   1. Motion lives in exactly one place - a 2px indeterminate line at the top
      of the pane. The placeholders themselves never animate.
   2. Placeholders reproduce the real geometry, column for column: the same
      44px rows, the same icon tile, the same jurisdiction/identifier/decision
      column widths, the same indent depths in the tree. The load previews the
      layout that is arriving instead of decorating the wait.
--------------------------------------------------------------------------- */

/** A single inert placeholder block. Kept low-contrast so a screenful of them
 * never competes with real content that has already rendered elsewhere. */
export function Bar({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return <div style={style} className={`bg-line-soft rounded-[3px] ${className}`} />;
}

/** Column widths mirror ResultsList exactly - see the constants there. */
export function ResultsSkeleton() {
  // Fixed, not random: a repeating pattern of name lengths reads as a table of
  // real rows, where randomised widths read as a shimmer effect.
  const nameWidths = ["15%", "9%", "11%", "18%"];

  return (
    <div className="border-line bg-surface overflow-hidden rounded-xl border">
      <div className="progress-line" />
      <ul className="divide-line-soft divide-y">
        {nameWidths.map((w, i) => (
          <li key={i} className="flex h-11 items-center gap-3 px-3.5">
            <Bar className="h-7 w-7 shrink-0 rounded-md" />
            <span className="min-w-0 flex-1">
              <Bar className="h-2.5" style={{ width: w }} />
            </span>
            <Bar className="hidden h-2.5 w-8 shrink-0 sm:block" />
            <span className="hidden w-[11.5rem] shrink-0 md:block">
              <Bar className="h-2.5 w-[8.5rem]" />
            </span>
            <span className="flex w-[6.75rem] shrink-0 justify-end">
              {i === 0 && <Bar className="h-3.5 w-16 rounded" />}
            </span>
            <span className="w-4 shrink-0" />
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Mirrors the tree's row height, indent guides and indent depths, so the
 * shape of the hierarchy is already on screen before the data lands. */
export function TreeSkeleton() {
  const rows = [
    { depth: 0, width: "17%" },
    { depth: 1, width: "11%" },
    { depth: 1, width: "14%" },
    { depth: 2, width: "9%" },
    { depth: 1, width: "13%" },
    { depth: 2, width: "10%" },
    { depth: 2, width: "8%" },
    { depth: 1, width: "12%" },
  ];

  return (
    <div className="h-full w-full">
      <div className="progress-line" />
      <div className="p-2">
        {rows.map((row, i) => (
          <div key={i} className="flex h-9 items-center" style={{ paddingLeft: row.depth * 22 }}>
            {/* The indent guide is drawn for real, not approximated, so the
                skeleton and the loaded tree share one silhouette. */}
            {row.depth > 0 && <span className="bg-line mr-[11px] h-9 w-px shrink-0" />}
            <Bar className="mr-2 h-3 w-3 shrink-0 rounded-full" />
            <Bar className="h-2.5" style={{ width: row.width }} />
          </div>
        ))}
      </div>
    </div>
  );
}
