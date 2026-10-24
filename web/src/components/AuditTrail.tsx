"use client";

import { ChevronDown, CircleCheck, CircleAlert, ScrollText } from "lucide-react";
import type { AskResponse } from "@/lib/api";

/* ---------------------------------------------------------------------------
   The answer's audit trail. Where the verification badge reports whether the
   answer held up against retrieved records, this reports how the answer was
   assembled: Kepler's seven layers, counted from the answer's own payload. A
   reader can see at a glance that the answer rests on N primary records, M
   addressed facts, K registered formulas, and Q citations - and that every
   deterministic gate passed before the answer was allowed to submit.

   The gates are not probabilities; a failed gate rejects the submission, so a
   failed row here reads as a hard failure, never a low score.
--------------------------------------------------------------------------- */

interface Layer {
  index: string;
  label: string;
  value: string;
  detail: string;
}

export default function AuditTrail({ answer }: { answer: AskResponse }) {
  const evidence = Object.values(answer.evidence);
  const facts = Object.values(answer.facts);
  const derivations = Object.values(answer.derivations);
  const gates = answer.gates ?? [];

  const sources = [...new Set(evidence.map((item) => item.source))];
  const addressed = facts.filter((fact) => fact.address?.locator);
  const units = [...new Set(facts.map((fact) => fact.unit).filter(Boolean))];
  const formulas = [...new Set(derivations.map((item) => item.formula_id))];
  const passedGates = gates.filter((gate) => gate.passed).length;

  const layers: Layer[] = [
    { index: "01", label: "Primary sources", value: `${evidence.length}`, detail: sources.join(" · ") || "—" },
    { index: "02", label: "Stable addresses", value: `${addressed.length}`, detail: addressed.length ? "document + locator on every value" : "—" },
    { index: "03", label: "Typed facts", value: `${facts.length}`, detail: units.length ? `${units.join(" · ")}` : "—" },
    { index: "04", label: "Deterministic formulas", value: `${formulas.length}`, detail: formulas.join(" · ") || "no computed values" },
    { index: "05", label: "Derived proofs", value: `${derivations.length}`, detail: derivations.length ? "each recomputed from its inputs" : "—" },
    { index: "06", label: "Rendered numbers", value: `${facts.length}`, detail: "late-bound from the fact, never typed by the model" },
    { index: "07", label: "Citations", value: `${answer.citations.length}`, detail: "restricted to evidence this run produced" },
  ];

  return (
    <details className="audit">
      <summary>
        <span className="audit-icon"><ScrollText /></span>
        <span className="audit-summary">
          <strong>Audit trail</strong>
          <small>
            {facts.length} value{facts.length === 1 ? "" : "s"} · {derivations.length} computed ·{" "}
            {gates.length ? `${passedGates}/${gates.length} gates passed` : "no gates recorded"}
          </small>
        </span>
        <ChevronDown className="audit-chevron" />
      </summary>

      <ol className="audit-layers">
        {layers.map((layer) => (
          <li key={layer.index}>
            <span className="audit-layer-index">{layer.index}</span>
            <span className="audit-layer-body">
              <span className="audit-layer-head">
                <strong>{layer.label}</strong>
                <span className="audit-layer-value tabular">{layer.value}</span>
              </span>
              <small>{layer.detail}</small>
            </span>
          </li>
        ))}
      </ol>

      {gates.length > 0 && (
        <div className="audit-gates">
          <span className="audit-gates-label">Submission gates</span>
          <ul>
            {gates.map((gate) => {
              const Icon = gate.passed ? CircleCheck : CircleAlert;
              return (
                <li key={gate.key} className={gate.passed ? "is-pass" : "is-fail"}>
                  <Icon aria-hidden />
                  <span className="audit-gate-label">{gate.label}</span>
                  {gate.message && <span className="audit-gate-message">{gate.message}</span>}
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </details>
  );
}
