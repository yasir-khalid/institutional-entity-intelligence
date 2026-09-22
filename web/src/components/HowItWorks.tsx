"use client";

import { useEffect, useState } from "react";
import {
  ArrowDown,
  Check,
  ChevronRight,
  CircleDot,
  Crosshair,
  Database,
  Fingerprint,
  Network,
  PanelRight,
  Search,
  type LucideIcon,
} from "lucide-react";
import { SectionLabel } from "@/components/ui";

const STEPS: { icon: LucideIcon; title: string; desc: string; demoLabel: string }[] = [
  { icon: Search, title: "Search", desc: "Start from a name, an LEI, or a security ID — whatever identifier you happen to have.", demoLabel: "A name is entered and matched against entity records." },
  { icon: Crosshair, title: "Resolve", desc: "Candidates are scored and ranked, with a clear match resolved automatically.", demoLabel: "Candidate entities are ranked and a high-confidence result is selected." },
  { icon: Network, title: "Explore", desc: "Walk the GLEIF relationship tree — parent companies, subsidiaries and managed funds.", demoLabel: "The selected entity expands into its direct legal relationships." },
  { icon: PanelRight, title: "Inspect", desc: "Open any entity for its identifiers, lineage, provenance and SEC 13F activity.", demoLabel: "An entity profile opens with identifiers and source provenance." },
];

function SearchDemo() {
  return <div className="workflow-demo-frame"><div className="workflow-demo-topline"><span>Query</span><span className="workflow-demo-status">Name</span></div><div className="workflow-search-field"><Search className="h-3.5 w-3.5 shrink-0" /><span className="workflow-typing">Point72</span><span className="workflow-caret" /></div><div className="workflow-result-row workflow-reveal-1"><span className="workflow-icon-tile"><Database className="h-3.5 w-3.5" /></span><span className="min-w-0 flex-1"><span className="workflow-name">Point72 Credit, LLC</span><span className="workflow-subline">KY · legal entity</span></span><ChevronRight className="h-3.5 w-3.5 text-ink-faint" /></div></div>;
}

function ResolveDemo() {
  return <div className="workflow-demo-frame"><div className="workflow-demo-topline"><span>Candidate set</span><span className="workflow-demo-status">3 found</span></div><div className="workflow-candidate workflow-reveal-1"><span className="workflow-rank">01</span><span className="workflow-name flex-1">Point72 Credit, LLC</span><span className="workflow-score">96%</span></div><div className="workflow-candidate workflow-reveal-2"><span className="workflow-rank">02</span><span className="workflow-name flex-1">Point72 Associates</span><span className="workflow-score text-ink-subtle">68%</span></div><div className="workflow-autopick workflow-reveal-3"><Check className="h-3.5 w-3.5" /><span>Auto matched · clear lead</span></div></div>;
}

function ExploreDemo() {
  return <div className="workflow-demo-frame"><div className="workflow-demo-topline"><span>Relationship tree</span><span className="workflow-demo-status">2 levels</span></div><div className="workflow-tree-root workflow-reveal-1"><CircleDot className="h-3.5 w-3.5 fill-accent text-accent" /><span className="workflow-name">Point72 Credit, LLC</span></div><div className="workflow-tree-branch workflow-reveal-2"><div className="workflow-tree-row"><ArrowDown className="h-3.5 w-3.5 text-downward" /><span className="workflow-name">Point72 Lending Corp.</span><span className="workflow-relationship">Subsidiary</span></div><div className="workflow-tree-row workflow-reveal-3"><ArrowDown className="h-3.5 w-3.5 text-downward" /><span className="workflow-name">Point72 Strategies</span><span className="workflow-relationship">Fund</span></div></div></div>;
}

function InspectDemo() {
  return <div className="workflow-demo-frame"><div className="workflow-demo-topline"><span>Entity profile</span><span className="workflow-demo-status">Active</span></div><div className="workflow-profile-head workflow-reveal-1"><span className="workflow-icon-tile"><Fingerprint className="h-3.5 w-3.5" /></span><span><span className="workflow-name">Point72 Credit, LLC</span><span className="workflow-subline font-mono">254900ESP1ZKG7UNS007</span></span></div><div className="workflow-provenance workflow-reveal-2"><span className="workflow-provenance-key">LEI</span><span className="font-mono text-[10px] text-ink">254900ESP1ZKG7UNS007</span><ChevronRight className="ml-auto h-3.5 w-3.5 text-ink-faint" /></div><div className="workflow-source workflow-reveal-3"><span>Source</span><span>GLEIF · snapshot 11 Sep 2026</span></div></div>;
}

function WorkflowPreview({ active }: { active: number }) {
  const demos = [<SearchDemo key="search" />, <ResolveDemo key="resolve" />, <ExploreDemo key="explore" />, <InspectDemo key="inspect" />];
  return <div key={active} className="workflow-demo animate-fade-in" role="img" aria-label={STEPS[active].demoLabel}><div className="workflow-demo-caption"><span className="workflow-demo-pulse" /> Auto-playing workflow preview · 2.8 s per step</div>{demos[active]}</div>;
}

export default function HowItWorks() {
  const [active, setActive] = useState(0);
  const [drawn, setDrawn] = useState(false);

  useEffect(() => { const t = setTimeout(() => setDrawn(true), 80); return () => clearTimeout(t); }, []);
  useEffect(() => { const interval = window.setInterval(() => setActive((current) => (current + 1) % STEPS.length), 2800); return () => window.clearInterval(interval); }, []);

  return <section className="w-full max-w-2xl" aria-label="How it works"><div className="mb-6 flex justify-center"><SectionLabel>How it works</SectionLabel></div><div className="relative"><div className="pointer-events-none absolute top-[22px] right-[12.5%] left-[12.5%] h-px overflow-hidden"><div className="via-line to-line from-line h-px w-full origin-left bg-gradient-to-r transition-transform duration-[900ms] ease-out" style={{ transform: drawn ? "scaleX(1)" : "scaleX(0)" }} /></div><ol className="relative flex items-start">{STEPS.map((step, i) => { const Icon = step.icon; const isActive = i === active; return <li key={step.title} className="flex flex-1 justify-center"><span aria-current={isActive ? "step" : undefined} className="flex flex-col items-center gap-2.5"><span className={`bg-surface flex h-11 w-11 items-center justify-center rounded-xl border transition-all duration-200 ${isActive ? "border-accent/35 text-accent shadow-[0_0_0_4px_var(--color-accent-soft)]" : "border-line text-ink-subtle"}`}><Icon className="h-[18px] w-[18px]" strokeWidth={1.75} /></span><span className="flex flex-col items-center gap-0.5"><span className={`text-[10px] font-semibold tabular transition-colors ${isActive ? "text-accent/70" : "text-ink-faint"}`}>{String(i + 1).padStart(2, "0")}</span><span className={`text-[13px] font-medium transition-colors ${isActive ? "text-ink" : "text-ink-muted"}`}>{step.title}</span></span></span></li>; })}</ol></div><div className="mx-auto mt-5 flex h-9 max-w-md items-start justify-center"><p key={active} className="animate-fade-in text-ink-muted text-center text-[12.5px] leading-relaxed">{STEPS[active].desc}</p></div><WorkflowPreview active={active} /></section>;
}
