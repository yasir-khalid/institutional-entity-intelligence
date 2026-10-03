import { ChevronDown, CircleSlash, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import type { Verification, VerificationCheck } from "@/lib/api";

/* ---------------------------------------------------------------------------
   The verification badge that closes an answer.

   Mirrors er.agent.verifier: after the agent finishes, the answer and every
   tool result behind it go to Jev - a decision model that returns a calibrated
   probability per typed question instead of prose - and the four probabilities
   plus the overall verdict are turned into one status by a threshold rule that
   lives in config/dev.yaml, not here. This component only renders that result.

   Three rules it is built around:

   1. "Not checked" is not "not verified". A verifier that could not be reached
      renders grey and neutral, never red - claiming an answer failed a check
      that never ran would be worse than showing no badge at all.
   2. The badge shows the verdict and the four scores, nothing else - no
      model name, timings or explanatory copy. Those live on the verifier row
      of the Developer panel.
   3. Colour is spent only where it carries information. The panel surface is
      always neutral - an earlier cut tinted the whole card green or amber by
      status, which made a routine "partially verified" shout as loudly as a
      real failure, and read as decoration rather than as data. Status lives in
      the glyph; a bar turns red only when it fell short. Never colour alone
      either: every state ships an icon and a worded label, and every meter
      carries its own numeric reading.
--------------------------------------------------------------------------- */

const STATUS_ICON = {
  verified: <ShieldCheck />,
  partial: <ShieldQuestion />,
  unverified: <ShieldAlert />,
  unavailable: <CircleSlash />,
};

function statusIcon(status: string) {
  return STATUS_ICON[status as keyof typeof STATUS_ICON] ?? STATUS_ICON.unavailable;
}

/** One check: a label, a meter, and its reading. The meter's track is a light
 * step of the fill's own hue so the unfilled remainder still reads as state,
 * and a hairline tick marks the threshold the check had to clear - without it
 * "0.62" is a number with nothing to be measured against. */
function CheckMeter({ check }: { check: VerificationCheck }) {
  const state = check.passed === null ? "unknown" : check.passed ? "pass" : "fail";
  const reading = check.probability;
  const percent = reading === null ? 0 : Math.round(Math.max(0, Math.min(1, reading)) * 100);

  return (
    <li className={`verify-check is-${state}`}>
      <span className="verify-check-label">{check.label}</span>
      <span
        className="verify-meter"
        role="meter"
        aria-label={check.label}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={reading ?? undefined}
        aria-valuetext={
          reading === null
            ? "No reading returned"
            : `${reading.toFixed(2)} against a ${check.threshold.toFixed(2)} threshold`
        }
      >
        <i className="verify-meter-fill" style={{ width: `${percent}%` }} />
        <i className="verify-meter-threshold" style={{ left: `${Math.round(check.threshold * 100)}%` }} aria-hidden />
      </span>
      <span className="verify-check-value tabular">{reading === null ? "no reading" : reading.toFixed(2)}</span>
    </li>
  );
}

export default function VerificationBadge({ verification }: { verification: Verification | null | undefined }) {
  if (!verification) return null;

  const readings = verification.checks.filter((check) => check.passed !== null);
  const cleared = readings.filter((check) => check.passed).length;
  const header = (
    <>
      <span className="verify-icon">{statusIcon(verification.status)}</span>
      <span className="verify-summary-copy">
        <strong>{verification.headline}</strong>
        {readings.length > 0 && <small>{cleared}/{readings.length} checks cleared</small>}
      </span>
    </>
  );

  // Just the verdict and the scores. Which model checked it, how long it took,
  // and why a check didn't run are developer detail - they live on the
  // verifier row of the Developer panel, not under every answer.
  if (verification.checks.length === 0) {
    return <div className={`verify is-${verification.status}`}><div className="verify-row">{header}</div></div>;
  }

  return (
    <details className={`verify is-${verification.status}`}>
      <summary>
        {header}
        <ChevronDown className="verify-chevron" />
      </summary>
      <ul className="verify-checks">
        {verification.checks.map((check) => <CheckMeter key={check.key} check={check} />)}
      </ul>
    </details>
  );
}
