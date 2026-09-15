"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown } from "lucide-react";

/* A height-capped scroll area that says so. A clipped list with no affordance
 * reads as a rendering bug rather than as "there is more below", so this pairs
 * the gradient fade with an explicit control: it appears only when content is
 * actually cut off, disappears on reaching the bottom, and scrolls a page when
 * clicked. */
export default function ScrollPane({
  children,
  className = "",
  contentClassName = "",
}: {
  children: ReactNode;
  /** Applied to the outer positioned wrapper (borders, background). */
  className?: string;
  /** Applied to the scroller itself - set the height cap and padding here. */
  contentClassName?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [more, setMore] = useState(false);

  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setMore(el.scrollHeight - el.clientHeight - el.scrollTop > 8);
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    measure();
    // Content can change height without a scroll event (results arrive, a row
    // wraps, the window resizes), so watch the box as well as the scroll.
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    if (el.firstElementChild) ro.observe(el.firstElementChild);
    return () => ro.disconnect();
  }, [measure, children]);

  return (
    // z-20 so the control, which straddles the pane's bottom edge, paints over
    // whatever follows it in the layout rather than under it.
    <div className={`relative z-20 ${className}`}>
      <div ref={ref} onScroll={measure} className={`scroll-thin overflow-y-auto ${contentClassName}`}>
        {children}
      </div>

      {more && (
        <>
          <div className="from-surface pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t to-transparent" />
          <button
            type="button"
            onClick={() => ref.current?.scrollBy({ top: (ref.current.clientHeight ?? 200) * 0.8, behavior: "smooth" })}
            aria-label="Scroll for more results"
            // Centred with a negative margin rather than -translate-x-1/2: the
            // nudge animation owns `transform`, and a translate utility here
            // would fight it.
            // Straddles the pane's bottom edge so it never covers a row, and
            // centred with a negative margin rather than -translate-x-1/2: the
            // nudge animation owns `transform`, and a translate utility here
            // would fight it.
            className="border-line bg-surface text-ink-muted hover:border-accent/50 hover:text-accent focus-visible:ring-accent-soft animate-nudge-down absolute -bottom-[0.875rem] left-1/2 -ml-3.5 flex h-7 w-7 items-center justify-center rounded-full border shadow-[0_2px_8px_rgba(15,23,42,0.12)] transition-colors focus-visible:ring-4 focus-visible:outline-none"
          >
            <ChevronDown className="h-4 w-4" strokeWidth={2.25} />
          </button>
        </>
      )}
    </div>
  );
}
