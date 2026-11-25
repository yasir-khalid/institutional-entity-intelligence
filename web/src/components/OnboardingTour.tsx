"use client";

import { useRef, useState, useSyncExternalStore } from "react";
import { ArrowRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";

const SEEN_KEY = "iei-onboarding-v1";

function seenBefore() {
  try {
    return Boolean(localStorage.getItem(SEEN_KEY));
  } catch {
    return true; // storage blocked: skip the tour rather than show it on every visit
  }
}

const STEPS = [
  {
    title: "Resolve any name to one legal entity",
    description:
      "The same firm is spelled differently in every filing. Each name is matched to a GLEIF LEI with a score you can inspect, and close calls go to review instead of being guessed.",
    Illustration: ResolveIllustration,
  },
  {
    title: "Follow ownership and filings",
    description:
      "From an entity, see its parent, the adviser behind it, its funds, 13F holdings and Form D raises. Every link is labelled with the source that asserts it.",
    Illustration: GraphIllustration,
  },
  {
    title: "Ask, and get cited answers",
    description:
      "The research agent answers from those records. Every number is a cited fact, re-checked against its source before you see it.",
    Illustration: AnswerIllustration,
  },
];

export function OnboardingTour() {
  const seen = useSyncExternalStore(() => () => {}, seenBefore, () => true);
  const [dismissed, setDismissed] = useState(false);
  const [step, setStep] = useState(0);
  const next = useRef<HTMLButtonElement>(null);

  function close(next: boolean) {
    if (next) return;
    setDismissed(true);
    try {
      localStorage.setItem(SEEN_KEY, new Date().toISOString());
    } catch {}
  }

  const last = step === STEPS.length - 1;
  const { title, description, Illustration } = STEPS[step];
  return (
    <Dialog open={!seen && !dismissed} onOpenChange={close}>
      <DialogContent
        className="tour gap-0 overflow-hidden p-0 sm:max-w-[34rem]"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          next.current?.focus();
        }}
      >
        <div key={step} className="tour-stage" aria-hidden>
          <Illustration />
        </div>
        <div className="grid gap-2 px-6 pt-5">
          <p className="text-xs text-muted-foreground tabular-nums">
            Step {step + 1} of {STEPS.length}
          </p>
          <DialogTitle className="text-lg leading-snug">{title}</DialogTitle>
          <DialogDescription className="leading-relaxed">{description}</DialogDescription>
        </div>
        <div className="flex items-center gap-2 px-6 pt-6 pb-5">
          <div className="tour-dots mr-auto" role="tablist" aria-label="Tour steps">
            {STEPS.map((item, index) => (
              <button
                key={item.title}
                type="button"
                role="tab"
                aria-selected={index === step}
                aria-label={`Step ${index + 1}`}
                onClick={() => setStep(index)}
              />
            ))}
          </div>
          {step > 0 ? (
            <Button variant="ghost" size="sm" onClick={() => setStep(step - 1)}>
              Back
            </Button>
          ) : (
            <Button variant="ghost" size="sm" onClick={() => close(false)}>
              Skip
            </Button>
          )}
          <Button ref={next} size="sm" onClick={() => (last ? close(false) : setStep(step + 1))}>
            {last ? "Start researching" : "Next"}
            <ArrowRight />
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

const NAMES = [
  "POINT72 ASSET MANAGEMENT, L.P.",
  "Point72 Asset Mgmt LP",
  "Point 72 AM",
];

function ResolveIllustration() {
  return (
    <div className="tour-resolve">
      <ul className="tour-names">
        {NAMES.map((name, index) => (
          <li key={name} style={{ "--i": index } as React.CSSProperties}>
            {name}
          </li>
        ))}
      </ul>
      <svg className="tour-links" viewBox="0 0 100 120" preserveAspectRatio="none">
        {[20, 60, 100].map((y, index) => (
          <path
            key={y}
            d={`M0 ${y} C50 ${y} 50 60 100 60`}
            pathLength={1}
            style={{ "--i": index } as React.CSSProperties}
          />
        ))}
      </svg>
      <div className="tour-entity">
        <span className="tour-entity-kicker">One LEI</span>
        <strong>Point72 Asset Management, L.P.</strong>
        <span className="tour-entity-badge">
          <Check aria-hidden /> Auto-matched
        </span>
      </div>
    </div>
  );
}

const NODES = [
  { x: 180, y: 26, label: "Parent", source: "GLEIF" },
  { x: 180, y: 84, label: "Adviser", source: "Form ADV" },
  { x: 64, y: 142, label: "Master fund", source: "N-PORT" },
  { x: 180, y: 142, label: "Holding", source: "13F" },
  { x: 296, y: 142, label: "Private raise", source: "Form D" },
];
const EDGES = [
  [0, 1],
  [1, 2],
  [1, 3],
  [1, 4],
];

function GraphIllustration() {
  return (
    <svg className="tour-graph" viewBox="0 0 360 170">
      {EDGES.map(([from, to], index) => {
        const a = NODES[from];
        const b = NODES[to];
        const mid = (a.y + b.y) / 2;
        return (
          <path
            key={`${from}-${to}`}
            d={`M${a.x} ${a.y + 15} C${a.x} ${mid} ${b.x} ${mid} ${b.x} ${b.y - 15}`}
            pathLength={1}
            style={{ "--i": index } as React.CSSProperties}
          />
        );
      })}
      {NODES.map((node, index) => (
        <g key={node.label} style={{ "--i": index } as React.CSSProperties}>
          <rect x={node.x - 50} y={node.y - 15} width={100} height={30} rx={7} />
          <text x={node.x} y={node.y - 2}>{node.label}</text>
          <text x={node.x} y={node.y + 9} className="tour-graph-source">
            {node.source}
          </text>
        </g>
      ))}
    </svg>
  );
}

function AnswerIllustration() {
  return (
    <div className="tour-answer">
      <p className="tour-question">Who manages Albacore Partners I?</p>
      <div className="tour-reply">
        <span className="tour-line" style={{ "--w": "94%", "--i": 0 } as React.CSSProperties} />
        <span className="tour-line-row">
          <span className="tour-line" style={{ "--w": "58%", "--i": 1 } as React.CSSProperties} />
          <span className="tour-cite">1</span>
        </span>
        <span className="tour-line" style={{ "--w": "76%", "--i": 2 } as React.CSSProperties} />
      </div>
      <div className="tour-source">
        <span className="tour-cite">1</span>
        <span className="tour-source-text">GLEIF relationship record</span>
        <span className="tour-verified">
          <Check aria-hidden /> Re-checked
        </span>
      </div>
    </div>
  );
}
