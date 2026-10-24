import { CircleCheck, CircleSlash, CircleAlert, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Verification, VerificationCheck } from "@/lib/api";

// The server owns decision thresholds. Probabilities remain in the Developer panel.
const STATUS = {
  verified: { icon: ShieldCheck, label: "Checked against retrieved records" },
  partial: { icon: ShieldQuestion, label: "Some checks need review" },
  unverified: { icon: ShieldAlert, label: "Answer needs review" },
  unavailable: { icon: CircleSlash, label: "Verification unavailable" },
};

function CheckBadge({ check }: { check: VerificationCheck }) {
  const state = check.passed === true ? "pass" : check.passed === false ? "fail" : "unknown";
  const Icon = state === "pass" ? CircleCheck : state === "fail" ? CircleAlert : CircleSlash;
  const label = state === "pass" ? "Passed" : state === "fail" ? "Needs review" : "Not checked";

  return (
    <li className={`verify-check is-${state}`}>
      <span className="verify-check-label">{check.label}</span>
      <Badge variant={state === "fail" ? "destructive" : state === "pass" ? "secondary" : "outline"}>
        <Icon aria-hidden="true" />
        {label}
      </Badge>
    </li>
  );
}

export default function VerificationBadge({ verification }: { verification: Verification | null | undefined }) {
  if (!verification) return null;
  const { icon: Icon, label } = STATUS[verification.status];

  return (
    <section className={`verify is-${verification.status}`} aria-label="Answer checks">
      <div className="verify-row">
        <span className="verify-icon"><Icon aria-hidden="true" /></span>
        <span className="verify-summary-copy">
          <strong>{label}</strong>
          <small>Checks compare this answer with the retrieved records.</small>
        </span>
      </div>
      {verification.checks.length > 0 && (
        <ul className="verify-checks">
          {verification.checks.map((check) => <CheckBadge key={check.key} check={check} />)}
        </ul>
      )}
    </section>
  );
}
