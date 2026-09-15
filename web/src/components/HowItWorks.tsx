"use client";

import { useEffect, useState } from "react";

const STEPS = [
  {
    icon: "🔍",
    title: "Search",
    desc: "Search a name, LEI, or security ID (CUSIP) - whatever you have on hand.",
  },
  {
    icon: "🎯",
    title: "Resolve",
    desc: "Pick the right entity from ranked results, or jump straight in on a clear match.",
  },
  {
    icon: "🌳",
    title: "Explore",
    desc: "Browse the GLEIF relationship tree - parents, subsidiaries, and managed funds.",
  },
  {
    icon: "📋",
    title: "Inspect",
    desc: "Click any entity for its full profile: identifiers and SEC 13F reported holdings.",
  },
];

export default function HowItWorks() {
  const [active, setActive] = useState(0);
  // Draws the connecting line in on mount rather than having it appear
  // instantly - a small touch that makes the "flow" read as a flow.
  const [lineDrawn, setLineDrawn] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setLineDrawn(true), 50);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className="w-full max-w-2xl">
      <h2 className="mb-6 text-center text-xs font-semibold uppercase tracking-widest text-slate-400">
        How it works
      </h2>

      <div className="relative flex items-start justify-between px-2">
        {/* Connecting line sits behind the circles, spanning center-to-center
            of the first and last step - drawn in via a scaleX transition. */}
        <div
          className="absolute top-6 right-[12.5%] left-[12.5%] h-0.5 origin-left bg-slate-200 transition-transform duration-700 ease-out"
          style={{ transform: lineDrawn ? "scaleX(1)" : "scaleX(0)" }}
        />

        {STEPS.map((step, i) => {
          const isActive = i === active;
          return (
            <button
              key={step.title}
              onMouseEnter={() => setActive(i)}
              onFocus={() => setActive(i)}
              className="group relative z-10 flex flex-1 flex-col items-center gap-2 text-center"
            >
              <span
                className={`flex h-12 w-12 items-center justify-center rounded-full border-2 bg-white text-xl transition-all duration-200 ${
                  isActive
                    ? "scale-110 border-blue-600 shadow-md shadow-blue-100"
                    : "border-slate-200 group-hover:border-slate-300"
                }`}
              >
                {step.icon}
              </span>
              <div className={`text-xs font-semibold transition-colors ${isActive ? "text-blue-600" : "text-slate-500"}`}>
                {i + 1}. {step.title}
              </div>
            </button>
          );
        })}
      </div>

      <div className="mx-auto mt-5 h-10 max-w-sm text-center">
        <p key={active} className="animate-fade-in-up text-xs leading-snug text-slate-500">
          {STEPS[active].desc}
        </p>
      </div>
    </div>
  );
}
