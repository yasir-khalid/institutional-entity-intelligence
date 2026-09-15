"use client";

import { useEffect, useState } from "react";
import { Search, Crosshair, Network, PanelRight, type LucideIcon } from "lucide-react";
import { SectionLabel } from "@/components/ui";

const STEPS: { icon: LucideIcon; title: string; desc: string }[] = [
  {
    icon: Search,
    title: "Search",
    desc: "Start from a name, an LEI, or a security ID — whatever identifier you happen to have.",
  },
  {
    icon: Crosshair,
    title: "Resolve",
    desc: "Candidates are scored and ranked, with a clear match resolved automatically.",
  },
  {
    icon: Network,
    title: "Explore",
    desc: "Walk the GLEIF relationship tree — parent companies, subsidiaries and managed funds.",
  },
  {
    icon: PanelRight,
    title: "Inspect",
    desc: "Open any entity for its identifiers, lineage, provenance and SEC 13F activity.",
  },
];

export default function HowItWorks() {
  const [active, setActive] = useState(0);
  // The connector draws itself in on mount so the row reads as a sequence
  // rather than four unrelated icons that happen to sit in a line.
  const [drawn, setDrawn] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setDrawn(true), 80);
    return () => clearTimeout(t);
  }, []);

  return (
    <section className="w-full max-w-2xl" aria-label="How it works">
      <div className="mb-6 flex justify-center">
        <SectionLabel>How it works</SectionLabel>
      </div>

      <div className="relative">
        {/* Connector sits at the vertical centre of the icon tiles and spans
            centre-to-centre of the first and last step. */}
        <div className="pointer-events-none absolute top-[22px] right-[12.5%] left-[12.5%] h-px overflow-hidden">
          <div
            className="via-line to-line from-line h-px w-full origin-left bg-gradient-to-r transition-transform duration-[900ms] ease-out"
            style={{ transform: drawn ? "scaleX(1)" : "scaleX(0)" }}
          />
        </div>

        <ol className="relative flex items-start">
          {STEPS.map((step, i) => {
            const Icon = step.icon;
            const isActive = i === active;
            return (
              <li key={step.title} className="flex flex-1 justify-center">
                <button
                  type="button"
                  onMouseEnter={() => setActive(i)}
                  onFocus={() => setActive(i)}
                  aria-current={isActive}
                  className="group flex flex-col items-center gap-2.5 outline-none"
                >
                  <span
                    className={`bg-surface flex h-11 w-11 items-center justify-center rounded-xl border transition-all duration-200 ${
                      isActive
                        ? "border-accent/35 text-accent shadow-[0_0_0_4px_var(--color-accent-soft)]"
                        : "border-line text-ink-subtle group-hover:border-ink-faint group-hover:text-ink-muted"
                    }`}
                  >
                    <Icon className="h-[18px] w-[18px]" strokeWidth={1.75} />
                  </span>
                  <span className="flex flex-col items-center gap-0.5">
                    <span
                      className={`text-[10px] font-semibold tabular transition-colors ${
                        isActive ? "text-accent/70" : "text-ink-faint"
                      }`}
                    >
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span
                      className={`text-[13px] font-medium transition-colors ${
                        isActive ? "text-ink" : "text-ink-muted"
                      }`}
                    >
                      {step.title}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>

      {/* Fixed height so swapping descriptions never shifts the page. */}
      <div className="mx-auto mt-5 flex h-9 max-w-md items-start justify-center">
        <p key={active} className="animate-fade-in text-ink-muted text-center text-[12.5px] leading-relaxed">
          {STEPS[active].desc}
        </p>
      </div>
    </section>
  );
}
