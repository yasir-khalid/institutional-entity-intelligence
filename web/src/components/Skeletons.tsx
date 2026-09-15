"use client";

import type { CSSProperties } from "react";

export function Bar({ className = "", style }: { className?: string; style?: CSSProperties }) {
  return <div style={style} className={`bg-canvas animate-pulse rounded ${className}`} />;
}

/** Mirrors ResultsList's row geometry exactly - 44px rows, icon tile, name,
 * jurisdiction and identifier columns - so the swap to real rows doesn't
 * shift anything on the page. */
export function ResultsSkeleton() {
  return (
    <ul className="divide-line-soft border-line bg-surface divide-y overflow-hidden rounded-xl border">
      {Array.from({ length: 4 }).map((_, i) => (
        <li key={i} className="flex h-11 items-center gap-3 px-3.5">
          <Bar className="h-7 w-7 shrink-0 rounded-md" />
          <Bar
            className="h-3 flex-1"
            style={{ maxWidth: `${22 + ((i * 9) % 16)}%`, animationDelay: `${i * 80}ms` }}
          />
          <Bar className="hidden h-3 w-14 shrink-0 sm:block" style={{ animationDelay: `${i * 80}ms` }} />
          <Bar className="hidden h-3 w-[13.5rem] shrink-0 md:block" style={{ animationDelay: `${i * 80}ms` }} />
          <Bar className="h-4 w-4 shrink-0 rounded" />
        </li>
      ))}
    </ul>
  );
}

/** Mirrors the tree's row geometry and indentation so the loading state
 * previews the shape of what's coming rather than a generic spinner. No card
 * chrome here either - the panel owns it, same as EntityTreeView. */
export function TreeSkeleton() {
  const rows = [0, 1, 1, 2, 1, 1, 2, 2, 1];
  return (
    <div className="h-full w-full p-2">
      {rows.map((depth, i) => (
        <div key={i} className="flex h-9 items-center gap-2" style={{ paddingLeft: depth * 22 }}>
          <Bar className="h-3.5 w-3.5 shrink-0 rounded" style={{ animationDelay: `${i * 60}ms` }} />
          <Bar
            className="h-3 rounded"
            style={{ width: `${34 - depth * 6 + ((i * 7) % 18)}%`, animationDelay: `${i * 60}ms` }}
          />
        </div>
      ))}
    </div>
  );
}
