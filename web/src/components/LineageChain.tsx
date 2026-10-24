"use client";

import type { ReactNode } from "react";
import { Check, Dot, Sigma } from "lucide-react";
import { type Derivation, type Evidence, type Fact } from "@/lib/api";
import { DerivationDetail, FactAddress, factLabel, formatFactValue } from "@/components/FactValues";

/* ---------------------------------------------------------------------------
   The numeric trust chain, after Kepler's evidence model. Every figure an
   answer states walks the same seven steps from a primary document to the
   reader:

     01 Source          the primary record the value was read from
     02 Address         the stable place in it (document + locator)
     03 Fact            the typed value (predicate, unit, as-of period)
     04 Transformation  the formula applied, or "reported as filed"
     05 Derived proof   the recomputation, or a direct value
     06 Rendered        the exact string the answer shows
     07 Citation        the [n] marker back to the source card

   Rendering the whole chain - not just the value - is the difference between
   trusting a number and being able to reproduce it. A computed value embeds
   its input derivation at steps 04-05, so every branch still ends at a filed
   row rather than at another computed number.
--------------------------------------------------------------------------- */

interface Step {
  index: string;
  label: string;
  value: ReactNode;
  computed?: boolean;
}

function StepRow({ step, last }: { step: Step; last: boolean }) {
  return (
    <li className={`lineage-step ${step.computed ? "is-computed" : ""}`}>
      <span className="lineage-rail" aria-hidden>
        <span className="lineage-index">{step.index}</span>
        {!last && <span className="lineage-thread" />}
      </span>
      <span className="lineage-body">
        <span className="lineage-label">{step.label}</span>
        <span className="lineage-value">{step.value}</span>
      </span>
    </li>
  );
}

export default function LineageChain({
  fact,
  derivation,
  evidence,
  facts,
  derivations,
}: {
  fact: Fact;
  derivation?: Derivation;
  evidence?: Evidence;
  facts: Record<string, Fact>;
  derivations: Record<string, Derivation>;
}) {
  const computed = Boolean(derivation);
  const inputs = derivation?.inputs.length ?? 0;

  const steps: Step[] = [
    {
      index: "01",
      label: "Source",
      value: <span className="lineage-strong">{evidence?.source ?? fact.address.source}</span>,
    },
    {
      index: "02",
      label: "Source address",
      value: <FactAddress fact={fact} />,
    },
    {
      index: "03",
      label: "Typed fact",
      value: (
        <>
          <span className="lineage-strong">{factLabel(fact.predicate)}</span>
          {fact.unit && <span className="lineage-chip">{fact.unit}</span>}
          {fact.as_of && <span className="lineage-meta">as of {fact.as_of}</span>}
        </>
      ),
    },
    {
      index: "04",
      label: "Transformation",
      computed,
      value: computed ? (
        <span className="lineage-formula">
          <Sigma /> {derivation!.expression} <span className="lineage-meta">({derivation!.formula_id})</span>
        </span>
      ) : (
        <span className="lineage-meta">Reported as filed · no transformation</span>
      ),
    },
    {
      index: "05",
      label: "Derived proof",
      computed,
      value: computed ? (
        <>
          <span className="lineage-strong">
            <Check /> Recomputed from {inputs} input{inputs === 1 ? "" : "s"}
          </span>
          <DerivationDetail derivation={derivation!} facts={facts} derivations={derivations} />
        </>
      ) : (
        <span className="lineage-meta">Direct value · nothing computed</span>
      ),
    },
    {
      index: "06",
      label: "Rendered",
      value: <span className="lineage-rendered">{formatFactValue(fact)}</span>,
    },
    {
      index: "07",
      label: "Citation",
      value: <span className="lineage-mono" title={fact.evidence_id}>{fact.evidence_id}</span>,
    },
  ];

  return (
    <div className={`lineage ${computed ? "is-computed" : ""}`}>
      <span className="lineage-title">
        <Dot /> Lineage · source to rendered number
      </span>
      <ol className="lineage-steps">
        {steps.map((step, index) => (
          <StepRow key={step.index} step={step} last={index === steps.length - 1} />
        ))}
      </ol>
      <dl className="lineage-ledger">
        <div>
          <dt>Provenance</dt>
          <dd>{fact.provenance_class ?? (computed ? "DERIVED_FACT" : "SOURCE_FACT")}</dd>
        </div>
        <div>
          <dt>Unit</dt>
          <dd>{fact.unit ?? "—"}</dd>
        </div>
        <div>
          <dt>Fact id</dt>
          <dd className="lineage-mono" title={fact.fact_id}>{fact.fact_id}</dd>
        </div>
        {evidence && (
          <div>
            <dt>Query hash</dt>
            <dd className="lineage-mono" title={evidence.query_hash}>{evidence.query_hash}</dd>
          </div>
        )}
      </dl>
    </div>
  );
}
