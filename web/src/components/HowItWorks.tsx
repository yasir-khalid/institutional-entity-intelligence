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
            className="h-px w-full origin-left bg-gradient-to-r from-slate-200 via-slate-200 to-slate-200 transition-transform duration-[900ms] ease-out"
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
                    className={`flex h-11 w-11 items-center justify-center rounded-xl border bg-white transition-all duration-200 ${
                      isActive
                        ? "border-indigo-200 text-indigo-600 shadow-[0_0_0_4px_rgb(238_242_255)]"
                        : "border-slate-200 text-slate-400 group-hover:border-slate-300 group-hover:text-slate-500"
                    }`}
                  >
                    <Icon className="h-[18px] w-[18px]" strokeWidth={1.75} />
                  </span>
                  <span className="flex flex-col items-center gap-0.5">
                    <span
                      className={`text-[10px] font-semibold tabular transition-colors ${
                        isActive ? "text-indigo-400" : "text-slate-300"
                      }`}
                    >
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span
                      className={`text-[13px] font-medium transition-colors ${
                        isActive ? "text-slate-900" : "text-slate-500"
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
        <p key={active} className="animate-fade-in text-center text-[12.5px] leading-relaxed text-slate-500">
          {STEPS[active].desc}
        </p>
      </div>
    </section>
  );
}
