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

const AUTO_ADVANCE_MS = 3200;

export default function HowItWorks() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (paused) return;
    const t = setInterval(() => setIndex((i) => (i + 1) % STEPS.length), AUTO_ADVANCE_MS);
    return () => clearInterval(t);
  }, [paused]);

  return (
    <div
      className="w-full max-w-md"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <h2 className="mb-3 text-center text-xs font-semibold uppercase tracking-widest text-slate-400">
        How it works
      </h2>

      <div className="relative h-40 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div
          className="flex h-full transition-transform duration-500 ease-out"
          style={{ transform: `translateX(-${index * 100}%)` }}
        >
          {STEPS.map((step, i) => (
            <div
              key={step.title}
              className="flex w-full shrink-0 flex-col items-center justify-center gap-1.5 px-8 text-center"
            >
              <span className="text-2xl">{step.icon}</span>
              <div className="text-sm font-semibold text-slate-900">
                <span className="mr-1.5 text-slate-300">{i + 1}.</span>
                {step.title}
              </div>
              <p className="text-xs leading-snug text-slate-500">{step.desc}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3 flex justify-center gap-1.5">
        {STEPS.map((step, i) => (
          <button
            key={step.title}
            onClick={() => setIndex(i)}
            aria-label={`Go to step ${i + 1}: ${step.title}`}
            className={`h-1.5 rounded-full transition-all duration-300 ${
              i === index ? "w-5 bg-blue-600" : "w-1.5 bg-slate-300 hover:bg-slate-400"
            }`}
          />
        ))}
      </div>
    </div>
  );
}
