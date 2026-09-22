"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Boxes,
  Check,
  ChevronRight,
  CircleDot,
  Fingerprint,
  History,
  Lightbulb,
  Network,
  ReceiptText,
  X,
  type LucideIcon,
} from "lucide-react";

/* ---------------------------------------------------------------------------
   "Why this matters" - a floating trigger on the landing page that opens a
   drawer explaining what this product is actually for: an agent is only as
   reliable as the entity layer underneath it.

   Every example below is a real, measured result from this repo (see
   experiments/*.md and docs/phases.md), not illustrative copy. If one of those
   numbers changes, change it here too.
--------------------------------------------------------------------------- */

/* A miniature of the thing each topic argues for, using the same visual
   grammar as the how-it-works preview. Staged in once on drawer open. */
function EntityResolutionDemo({ index }: { index: number }) {
  const base = 300 + index * 70;
  return (
    <div className="workflow-demo-frame why-demo-wrap">
      <div className="workflow-tree-root">
        <CircleDot className="h-3.5 w-3.5 fill-accent text-accent" />
        <span className="workflow-name">&ldquo;Point72&rdquo;</span>
      </div>
      <div className="workflow-tree-branch">
        <div className="workflow-tree-row why-demo-step" style={{ animationDelay: `${base + 120}ms` }}>
          <span className="workflow-name">Point72 Credit, LLC</span>
          <span className="workflow-relationship">DE</span>
        </div>
        <div className="workflow-tree-row why-demo-step" style={{ animationDelay: `${base + 260}ms` }}>
          <span className="workflow-name">Point72 Strategies</span>
          <span className="workflow-relationship">KY</span>
        </div>
        <div className="workflow-tree-row why-demo-step" style={{ animationDelay: `${base + 400}ms` }}>
          <span className="workflow-name">Point72 HK Ltd</span>
          <span className="workflow-relationship">HK</span>
        </div>
      </div>
    </div>
  );
}

function IdentifiersDemo({ index }: { index: number }) {
  const base = 300 + index * 70;
  return (
    <div className="workflow-demo-frame why-demo-wrap">
      <div className="why-demo-conflict why-demo-step" style={{ animationDelay: `${base}ms` }}>
        <span className="workflow-name">&ldquo;Point72 Capital&rdquo;</span>
        <span className="why-demo-conflict-tag">2 different firms</span>
      </div>
      <div className="workflow-autopick why-demo-step" style={{ animationDelay: `${base + 240}ms` }}>
        <Check className="h-3.5 w-3.5" />
        <span className="font-mono">254900ESP1ZKG7UNS007 · exact match</span>
      </div>
    </div>
  );
}

function HierarchyDemo({ index }: { index: number }) {
  const base = 300 + index * 70;
  return (
    <div className="workflow-demo-frame why-demo-wrap">
      <div className="workflow-tree-root">
        <CircleDot className="h-3.5 w-3.5 fill-accent text-accent" />
        <span className="workflow-name">Master Fund</span>
        <span className="why-demo-rollup">$420M</span>
      </div>
      <div className="workflow-tree-branch">
        <div className="workflow-tree-row why-demo-step" style={{ animationDelay: `${base + 120}ms` }}>
          <span className="workflow-name">Feeder A</span>
          <span className="workflow-relationship">$260M</span>
        </div>
        <div className="workflow-tree-row why-demo-step" style={{ animationDelay: `${base + 260}ms` }}>
          <span className="workflow-name">Feeder B</span>
          <span className="workflow-relationship">$160M</span>
        </div>
      </div>
    </div>
  );
}

function LineageDemo({ index }: { index: number }) {
  const base = 300 + index * 70;
  return (
    <div className="workflow-demo-frame why-demo-wrap">
      <div className="why-demo-timeline">
        <span className="why-demo-tl-dot why-demo-step" style={{ animationDelay: `${base}ms` }} />
        <span className="why-demo-tl-dot why-demo-step" style={{ animationDelay: `${base + 100}ms` }} />
        <span className="why-demo-tl-dot why-demo-step" style={{ animationDelay: `${base + 200}ms` }} />
        <span className="why-demo-tl-dot why-demo-tl-active why-demo-step" style={{ animationDelay: `${base + 300}ms` }} />
      </div>
      <div className="why-demo-tl-labels">
        <span>Created</span>
        <span>Registered</span>
        <span>Updated</span>
        <span>Renewal</span>
      </div>
      <div className="workflow-source why-demo-step" style={{ animationDelay: `${base + 420}ms` }}>
        <span>Status</span>
        <span className="why-demo-status-active">ACTIVE</span>
      </div>
    </div>
  );
}

function ProvenanceDemo({ index }: { index: number }) {
  const base = 300 + index * 70;
  return (
    <div className="workflow-demo-frame why-demo-wrap">
      <div className="workflow-provenance">
        <span className="workflow-provenance-key">LEI</span>
        <span className="font-mono text-[10px] text-ink">254900ESP1ZKG7UNS007</span>
        <ChevronRight className="ml-auto h-3.5 w-3.5 text-ink-faint" />
      </div>
      <div className="why-demo-expand">
        <div className="why-demo-expand-row why-demo-step" style={{ animationDelay: `${base}ms` }}>
          <span>Source file</span>
          <span>GLEIF_LEI-CDF.xml</span>
        </div>
        <div className="why-demo-expand-row why-demo-step" style={{ animationDelay: `${base + 130}ms` }}>
          <span>Snapshot</span>
          <span>11 Sep 2026</span>
        </div>
        <div className="why-demo-expand-row why-demo-step" style={{ animationDelay: `${base + 260}ms` }}>
          <span>Ingested</span>
          <span>12 Sep 2026 · 04:11 UTC</span>
        </div>
      </div>
    </div>
  );
}

const TOPICS: {
  icon: LucideIcon;
  title: string;
  takeaway: string;
  why: string;
  example: string;
  Demo: (props: { index: number }) => React.JSX.Element;
}[] = [
  {
    icon: Boxes,
    title: "Entity resolution",
    takeaway: "Turn a brand name into the legal entity that actually owns the risk.",
    why: "A brand name is not a legal entity. “Point72” is not one company — it is a dozen separate legal entities across Delaware, the Cayman Islands, Hong Kong, Japan and the DIFC. An agent that treats the string as the thing will silently merge a lending vehicle with an asset manager and report the total as one firm.",
    example:
      "Resolving names properly took benchmark Recall@20 from 74.9% to 88.35% on this dataset.",
    Demo: EntityResolutionDemo,
  },
  {
    icon: Fingerprint,
    title: "Identifiers",
    takeaway: "Replace plausible joins with exact, source-backed identity.",
    why: "Names are not keys. The same entity is spelled a dozen ways across filings, and two unrelated firms can share a name. An LEI, CIK, CUSIP or ISIN is exact, so joining on identifiers is the difference between a join that is right and one that merely looks right.",
    example:
      "Every entity here carries its identifiers from each source, each with its own match confidence.",
    Demo: IdentifiersDemo,
  },
  {
    icon: Network,
    title: "Hierarchy",
    takeaway: "See exposure through the entities that control and hold it.",
    why: "Exposure questions are never about one node. “How much do we hold through this manager?” means walking parents, subsidiaries and managed funds — and a feeder fund’s holdings belong to its master, not to itself. Answer from the node alone and you undercount, sometimes by everything that matters.",
    example:
      "Fixing master/feeder handling took the dangerous-failure rate from 26.1% to 0.0%, precision 53.9% → 100%.",
    Demo: HierarchyDemo,
  },
  {
    icon: History,
    title: "Lineage",
    takeaway: "Know whether a confident result is still current.",
    why: "A record that resolves is not the same as a record that is current. An LEI can be LAPSED, RETIRED or pending transfer and still return a confident-looking answer. An agent needs the registration status and the last-updated date, or it will cite a dead entity in a live decision.",
    example:
      "Each entity shows created, registered, last updated and renewal-due, plus its registration status.",
    Demo: LineageDemo,
  },
  {
    icon: ReceiptText,
    title: "Provenance",
    takeaway: "Let every answer carry its evidence and its date.",
    why: "“How do you know?” is the question that makes an answer usable. Every identifier here records the file it came from, the snapshot it was taken from, and when it was ingested — so any claim can be traced to a source and a date rather than asserted.",
    example:
      "Click any identifier row in the details panel to expand its source file, snapshot and ingestion time.",
    Demo: ProvenanceDemo,
  },
];

function Topic({ icon: Icon, title, takeaway, why, example, index, Demo }: (typeof TOPICS)[number] & { index: number }) {
  return (
    <section className="why-topic border-line-soft border-t pt-5 first:border-t-0 first:pt-0" style={{ animationDelay: `${120 + index * 70}ms` }}>
      <h3 className="text-ink flex items-center gap-2 text-[13.5px] font-semibold">
        <span className="why-topic-icon bg-accent-soft text-accent flex h-6 w-6 shrink-0 items-center justify-center rounded-md" style={{ animationDelay: `${180 + index * 70}ms` }}>
          <Icon className="h-3.5 w-3.5" strokeWidth={2} />
        </span>
        {title}
      </h3>
      <p className="text-ink mt-2 text-[12.5px] font-medium leading-relaxed">{takeaway}</p>
      <p className="text-ink-muted mt-2 text-[12px] leading-relaxed">{why}</p>
      <p className="border-accent/30 bg-accent-soft/40 text-ink-muted mt-2.5 border-l-2 px-3 py-2 text-[11.5px] leading-relaxed">
        {example}
      </p>
      <Demo index={index} />
    </section>
  );
}

export default function WhyItMatters() {
  const [open, setOpen] = useState(false);
  const closeRef = useRef<HTMLButtonElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  const close = useCallback(() => {
    setOpen(false);
    triggerRef.current?.focus();
  }, []);

  // Escape closes, and the page behind must not scroll while the drawer is up.
  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        close();
        return;
      }
      if (e.key !== "Tab") return;
      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, close]);

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        aria-expanded={open}
        className="border-line bg-surface text-ink-muted hover:border-accent/40 hover:text-ink focus-visible:ring-accent-soft fixed right-5 bottom-5 z-30 flex items-center gap-2 rounded-full border py-2.5 pr-4 pl-3 text-[12.5px] font-medium shadow-[0_2px_12px_rgba(15,23,42,0.10)] transition-all hover:shadow-[0_4px_18px_rgba(15,23,42,0.14)] focus-visible:ring-4 focus-visible:outline-none"
      >
        <span className="bg-accent-soft text-accent flex h-6 w-6 items-center justify-center rounded-full">
          <Lightbulb className="h-3.5 w-3.5" strokeWidth={2} />
        </span>
        Why this matters
      </button>

      {open && (
        <div className="fixed inset-0 z-40">
          <div
            className="animate-fade-in absolute inset-0 bg-slate-900/25 backdrop-blur-[1px]"
            onClick={close}
            aria-hidden
          />

          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="why-title"
            aria-describedby="why-description"
            className="animate-slide-in-right border-line bg-surface absolute inset-y-0 right-0 flex w-[min(32rem,100vw)] flex-col border-l shadow-[-8px_0_32px_rgba(15,23,42,0.12)]"
          >
            <header className="border-line-soft flex shrink-0 items-start justify-between gap-4 border-b px-6 py-5">
              <div>
                <h2 id="why-title" className="text-ink text-[16px] font-semibold tracking-[-0.01em]">Why an entity layer matters</h2>
                <span className="why-title-rule" aria-hidden />
                <p id="why-description" className="text-ink-muted mt-1.5 text-[12.5px] leading-relaxed">
                  An agent is only as reliable as the entity layer underneath it. These five properties are what
                  separate a lookup from context you can act on.
                </p>
              </div>
              <button
                ref={closeRef}
                type="button"
                onClick={close}
                aria-label="Close"
                className="text-ink-subtle hover:bg-canvas hover:text-ink focus-visible:ring-accent-soft -mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors focus-visible:ring-4 focus-visible:outline-none"
              >
                <X className="h-4 w-4" strokeWidth={2} />
              </button>
            </header>

            <div className="scroll-thin flex flex-col gap-5 overflow-y-auto px-6 py-5">
              {TOPICS.map((t, index) => (
                <Topic key={t.title} {...t} index={index} />
              ))}

              <p className="border-line-soft text-ink-subtle border-t pt-5 text-[11.5px] leading-relaxed">
                The figures above are measured, not estimated — the methodology and the full before/after results
                live in <code className="text-ink-muted font-mono text-[11px]">experiments/</code> in the repository.
              </p>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
