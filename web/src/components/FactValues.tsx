"use client";

import { ExternalLink, Sigma } from "lucide-react";
import { apiUrl, type Derivation, type Fact } from "@/lib/api";

/* ---------------------------------------------------------------------------
   Addressed values (er.agent.models.Fact). Every number an answer states is
   one of these - shown here with the exact place it came from, and for a
   computed one, the formula and the inputs it was computed from.
--------------------------------------------------------------------------- */

export function factLabel(predicate: string): string {
  const parts = predicate.split(":")[0].split(".");
  const name = parts[parts.length - 1];
  // "position.value" reads as "value" alone - keep the noun it belongs to.
  const label = ["value", "change"].includes(name) && parts.length > 1 ? `${parts[parts.length - 2]} ${name}` : name;
  return label.replace(/_/g, " ");
}

export function formatFactValue(fact: Pick<Fact, "value" | "unit" | "predicate">): string {
  const { value, unit } = fact;
  const signed = fact.predicate.includes("change");
  if (value === null) return "—";
  const number = typeof value === "number" ? value : Number(value);
  if (typeof value !== "boolean" && value !== "" && Number.isFinite(number) && /^-?[\d.]+$/.test(String(value))) {
    if (unit === "USD") return `${number < 0 ? "−" : signed ? "+" : ""}$${Math.abs(number).toLocaleString("en-US")}`;
    if (unit === "USD_THOUSANDS") return `$${number.toLocaleString("en-US")} thousand`;
    if (unit === "percent") return `${signed && number > 0 ? "+" : ""}${number.toLocaleString("en-US")}%`;
    if (unit === "shares") return `${number.toLocaleString("en-US")} shares`;
    if (unit === "points") return `${number.toLocaleString("en-US")} pts`;
  }
  return String(value);
}

/** Where a value lives: document, locator and, when there is one, a link to
 * the original (an EDGAR filing, a PDF page). */
export function FactAddress({ fact }: { fact: Fact }) {
  const { address } = fact;
  return (
    <span className="fact-address">
      <code title={address.locator}>{address.locator}</code>
      {address.uri && (
        <a href={apiUrl(address.uri)} target="_blank" rel="noreferrer">
          {address.page ? `page ${address.page}` : "original"} <ExternalLink />
        </a>
      )}
    </span>
  );
}

/** A computed value's formula and inputs. An input that is itself computed
 * (a period total feeding a change) unfolds once more, down to the filed
 * rows, so every figure ends at a source address. */
export function DerivationDetail({
  derivation,
  facts,
  derivations,
  depth = 0,
}: {
  derivation: Derivation;
  facts: Record<string, Fact>;
  derivations: Record<string, Derivation>;
  depth?: number;
}) {
  return (
    <div className="fact-derivation">
      <span className="fact-formula"><Sigma /> {factLabel(facts[derivation.fact_id]?.predicate ?? derivation.formula_id)} = {derivation.expression}</span>
      <ol>
        {derivation.inputs.map((inputId) => {
          const input = facts[inputId];
          if (!input) return <li key={inputId}><code>{inputId}</code></li>;
          const nested = derivations[inputId];
          return (
            <li key={inputId}>
              <span className="fact-input-value">{formatFactValue(input)}</span>
              <span className="fact-input-meta">{input.as_of}</span>
              {nested && depth < 2 ? (
                <DerivationDetail derivation={nested} facts={facts} derivations={derivations} depth={depth + 1} />
              ) : (
                <FactAddress fact={input} />
              )}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** The values an evidence record supplied to the answer. */
export default function FactValues({
  evidenceId,
  facts,
  derivations,
}: {
  evidenceId: string;
  facts: Record<string, Fact>;
  derivations: Record<string, Derivation>;
}) {
  const used = Object.values(facts).filter((fact) => fact.evidence_id === evidenceId);
  if (used.length === 0) return null;
  return (
    <div className="fact-values">
      <span className="fact-values-label">Values in this answer</span>
      <ul>
        {used.map((fact) => (
          <li key={fact.fact_id}>
            <div className="fact-row">
              <span className="fact-name">{factLabel(fact.predicate)}</span>
              <strong>{formatFactValue(fact)}</strong>
            </div>
            {derivations[fact.fact_id] ? (
              <DerivationDetail derivation={derivations[fact.fact_id]} facts={facts} derivations={derivations} />
            ) : (
              <FactAddress fact={fact} />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
