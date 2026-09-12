"use client";

export function Bar({ className = "", style }: { className?: string; style?: React.CSSProperties }) {
  return <div style={style} className={`animate-pulse rounded bg-slate-200 ${className}`} />;
}

export function ResultsSkeleton() {
  return (
    <div className="flex flex-col divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="flex items-center justify-between px-4 py-2.5">
          <div className="flex-1">
            <Bar className="mb-1.5 h-4 w-48" />
            <Bar className="h-3 w-32" />
          </div>
          <Bar className="h-4 w-16" />
        </div>
      ))}
    </div>
  );
}

/** Loosely mimics the org-chart card layout (a root card, a row of child
 * cards) so the loading state previews the shape of what's coming, rather
 * than a generic spinner. */
export function TreeSkeleton() {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-6 rounded-lg border border-slate-200 bg-slate-50 p-8">
      <Bar className="h-14 w-56 rounded-lg" />
      <div className="h-6 w-px bg-slate-200" />
      <div className="flex gap-6">
        {Array.from({ length: 4 }).map((_, i) => (
          <Bar key={i} className="h-14 w-40 rounded-lg" style={{ animationDelay: `${i * 100}ms` }} />
        ))}
      </div>
    </div>
  );
}
