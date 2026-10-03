"use client";

import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, ArrowRight, ChevronDown, ChevronRight, ExternalLink, Loader2, Sigma } from "lucide-react";
import {
  getPositionHistory,
  submitReview,
  type ConnectionGroup,
  type EntityDetail,
  type MatchDecision,
  type MatchReview,
  type ToolResult,
} from "@/lib/api";
import { DerivationDetail, formatFactValue } from "@/components/FactValues";

/* ---------------------------------------------------------------------------
   The entity profile under search results. Each section is one kind of claim
   with its own source, kept apart on purpose: GLEIF identity, how other
   sources' records were linked to this LEI, ownership and control from
   filings and registers, and latest reported 13F holdings.
--------------------------------------------------------------------------- */

const COLLAPSE_AT = 8;

const GROUP_LABELS: Record<string, { outgoing: string; incoming: string; note: string }> = {
  BENEFICIAL_OWNER: {
    outgoing: "Holds over 5% of",
    incoming: "Owners of over 5%",
    note: "Schedule 13D (active) / 13G (passive) beneficial ownership - not 13F investment discretion.",
  },
  BANK_CONTROL_PARENT: {
    outgoing: "Controlled by (bank holding company)",
    incoming: "Controls (banking)",
    note: "FFIEC NIC regulatory control - not the same as a GLEIF accounting parent.",
  },
  SIGNIFICANT_CONTROL: {
    outgoing: "Has significant control over",
    incoming: "Persons with significant control",
    note: "Companies House PSC register.",
  },
  INSIDER_OF: {
    outgoing: "Insider of",
    incoming: "Insiders (officers, directors, 10% owners)",
    note: "SEC Forms 3, 4 and 5.",
  },
  SUCCEEDED_BY: {
    outgoing: "Succeeded by",
    incoming: "Successor to",
    note: "The record that replaced this one after a merger or other succession.",
  },
};

const SOURCE_LABELS: Record<string, string> = {
  sec_13dg: "13D/G",
  ffiec_nic: "FFIEC NIC",
  companies_house_psc: "Companies House",
  sec_insiders: "Forms 3/4/5",
  gleif: "GLEIF",
  sec_13f_crosswalk: "13F crosswalk",
  human_review: "Human review",
  nport: "N-PORT",
  gleif_registration_id: "GLEIF registration ID",
};

function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source.replace(/_/g, " ");
}

function formatUsd(value: number | null, unit: string): string {
  if (value === null) return "—";
  return unit === "USD_THOUSANDS" ? `$${value.toLocaleString("en-US")} thousand` : `$${value.toLocaleString("en-US")}`;
}

function ProfileSection({ title, hint, children }: { title: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <section className="profile-section">
      <div className="profile-section-head">
        <h3>{title}</h3>
        {hint && <span>{hint}</span>}
      </div>
      {children}
    </section>
  );
}

function Collapsible<T>({ items, render }: { items: T[]; render: (item: T, index: number) => ReactNode }) {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? items : items.slice(0, COLLAPSE_AT);
  return (
    <>
      {shown.map(render)}
      {items.length > COLLAPSE_AT && (
        <button type="button" className="profile-more" onClick={() => setExpanded((value) => !value)}>
          {expanded ? "Show fewer" : `Show ${items.length - COLLAPSE_AT} more`}
        </button>
      )}
    </>
  );
}

function Identifiers({ detail }: { detail: EntityDetail }) {
  const linked = detail.connections.linked_records;
  return (
    <ProfileSection
      title="Identifiers"
      hint={
        detail.identifier_total > detail.identifiers.length
          ? `${(detail.identifier_total + 1).toLocaleString()} attached · showing ${detail.identifiers.length + 1}`
          : `${detail.identifiers.length + 1} attached`
      }
    >
      <ul className="profile-rows">
        <li>
          <span className="profile-key">LEI</span>
          <code>{detail.entity_id}</code>
          <span className="profile-tag">GLEIF</span>
        </li>
        <Collapsible
          items={detail.identifiers}
          render={(identifier, index) => (
            <li key={`${identifier.identifier_type}-${identifier.identifier_value}-${index}`}>
              <span className="profile-key">{identifier.identifier_type}</span>
              <code>{identifier.identifier_value}</code>
              <span className={`profile-tag ${identifier.confidence === "REVIEW" ? "is-caution" : ""}`}>
                {identifier.confidence === "SOURCE" ? sourceLabel(identifier.source) : identifier.confidence.replace(/_/g, " ")}
              </span>
            </li>
          )}
        />
      </ul>
      {linked.length > 0 && (
        <>
          <p className="profile-subhead">Same entity in other sources</p>
          <ul className="profile-rows">
            {linked.map((record) => (
              <li key={record.node_id}>
                <span className="profile-key">{record.node_id.split(":")[0].toUpperCase()}</span>
                <span className="profile-name">{record.display_name ?? record.node_id}</span>
                <span className="profile-tag">{sourceLabel(record.source)}</span>
              </li>
            ))}
          </ul>
        </>
      )}
    </ProfileSection>
  );
}

function ReviewForm({ decision, onSaved }: { decision: MatchDecision; onSaved: (review: MatchReview) => void }) {
  const [reviewer, setReviewer] = useState("");
  const [rationale, setRationale] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(outcome: MatchReview["outcome"]) {
    setSaving(true);
    setError(null);
    try {
      onSaved(await submitReview({ node_id: decision.node_id, lei: decision.lei ?? "", outcome, reviewer, rationale }));
      setRationale("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The review could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="review-form">
      <input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder="Reviewer" aria-label="Reviewer" />
      <input value={rationale} onChange={(event) => setRationale(event.target.value)} placeholder="Rationale" aria-label="Rationale" />
      <button type="button" disabled={saving || !reviewer.trim()} onClick={() => void save("CONFIRMED")}>Confirm link</button>
      <button type="button" className="is-reject" disabled={saving || !reviewer.trim()} onClick={() => void save("REJECTED")}>Reject link</button>
      {error && <p className="review-error">{error}</p>}
    </div>
  );
}

function DecisionCard({ decision, onOpenEntity }: { decision: MatchDecision; onOpenEntity: (lei: string) => void }) {
  const [reviews, setReviews] = useState(decision.reviews);
  const features = Object.entries(decision.feature_contributions).sort((a, b) => b[1] - a[1]);
  const maxPoints = Math.max(1, ...features.map(([, points]) => Math.abs(points)));
  const latest = reviews[reviews.length - 1];

  return (
    <article className="decision-card">
      <header>
        <div>
          <span className="profile-key">{decision.node_id.split(":")[0].toUpperCase()}</span>
          <code>{decision.node_id.split(":")[1]}</code>
          {decision.source_name && <span className="profile-name">{decision.source_name}</span>}
        </div>
        <span className={`profile-tag ${decision.decision === "AUTO_MATCH" ? "is-positive" : "is-caution"}`}>
          {decision.decision.replace(/_/g, " ")}
        </span>
      </header>

      <dl className="decision-grid">
        <dt>Score</dt><dd>{decision.score?.toFixed(1) ?? "—"}</dd>
        <dt>Gap to runner-up</dt><dd>{decision.gap?.toFixed(1) ?? "—"}</dd>
        <dt>Runner-up</dt>
        <dd>
          {decision.runner_up_lei ? (
            <button type="button" className="profile-link" onClick={() => onOpenEntity(decision.runner_up_lei!)}>
              {decision.runner_up_name ?? decision.runner_up_lei}
            </button>
          ) : "—"}
          {decision.runner_up_score !== null && <small> · {decision.runner_up_score.toFixed(1)}</small>}
        </dd>
        <dt>Config</dt><dd><code>{decision.config_hash ?? "—"}</code>{decision.decided_on && <small> · {decision.decided_on}</small>}</dd>
      </dl>
      {decision.reason && <p className="decision-reason">{decision.reason}</p>}

      {features.length > 0 && (
        <ul className="feature-bars" aria-label="Points per matching feature">
          {features.map(([feature, points]) => (
            <li key={feature}>
              <span>{feature.replace(/_/g, " ")}</span>
              <i style={{ width: `${(Math.abs(points) / maxPoints) * 100}%` }} className={points < 0 ? "is-penalty" : ""} />
              <strong>{points > 0 ? "+" : ""}{points}</strong>
            </li>
          ))}
        </ul>
      )}

      <div className="decision-reviews">
        <p className="profile-subhead">
          Human review{latest ? ` · latest: ${latest.outcome.toLowerCase()} by ${latest.reviewer}` : " · none yet"}
        </p>
        {reviews.length > 0 && (
          <ul>
            {reviews.map((review) => (
              <li key={`${review.reviewer}-${review.reviewed_at}`}>
                <span className={`profile-tag ${review.outcome === "CONFIRMED" ? "is-positive" : "is-critical"}`}>{review.outcome}</span>
                <span>{review.reviewer}</span>
                <small>{review.reviewed_at}</small>
                {review.rationale && <em>{review.rationale}</em>}
              </li>
            ))}
          </ul>
        )}
        <ReviewForm decision={decision} onSaved={(review) => setReviews((current) => [...current, review])} />
        <small className="decision-footnote">A review never edits the decision. It is stored separately and changes the graph link on the next knowledge-graph build.</small>
      </div>
    </article>
  );
}

function Resolution({ detail, onOpenEntity }: { detail: EntityDetail; onOpenEntity: (lei: string) => void }) {
  if (detail.match_decisions.length === 0) return null;
  return (
    <ProfileSection title="How other records were linked" hint="deterministic matcher, citable">
      {detail.match_decisions.map((decision) => (
        <DecisionCard key={decision.node_id} decision={decision} onOpenEntity={onOpenEntity} />
      ))}
    </ProfileSection>
  );
}

function ConnectionList({ group, onOpenEntity }: { group: ConnectionGroup; onOpenEntity: (lei: string) => void }) {
  const labels = GROUP_LABELS[group.edge_type];
  return (
    <div className="connection-group">
      <div className="connection-group-head">
        <strong>{labels ? labels[group.direction] : group.edge_type}</strong>
        <span>{group.total > group.connections.length ? `top ${group.connections.length} of ${group.total.toLocaleString()}` : group.total}</span>
      </div>
      {labels && <p className="connection-note">{labels.note}</p>}
      <ul className="profile-rows">
        <Collapsible
          items={group.connections}
          render={(connection) => {
            const lei = connection.other_node_id.startsWith("lei:") ? connection.other_node_id.slice(4) : null;
            return (
              <li key={`${connection.other_node_id}-${connection.source}`} className={connection.valid_to ? "is-ended" : ""}>
                {lei ? (
                  <button type="button" className="profile-link profile-name" onClick={() => onOpenEntity(lei)}>
                    {connection.other_name ?? lei}
                  </button>
                ) : (
                  <span className="profile-name" title={connection.other_node_id}>{connection.other_name ?? connection.other_node_id}</span>
                )}
                {connection.percent !== null && <span className="profile-figure">{connection.percent.toLocaleString("en-US")}%</span>}
                <small>{connection.valid_to ? `ended ${connection.valid_to}` : connection.valid_from ? `since ${connection.valid_from}` : ""}</small>
                <span className="profile-tag">{sourceLabel(connection.source)}</span>
                {connection.source_url && (
                  <a className="profile-icon-link" href={connection.source_url} target="_blank" rel="noreferrer" aria-label="Open the filing">
                    <ExternalLink />
                  </a>
                )}
              </li>
            );
          }}
        />
      </ul>
    </div>
  );
}

function Connections({ detail, onOpenEntity }: { detail: EntityDetail; onOpenEntity: (lei: string) => void }) {
  const groups = detail.connections.groups;
  return (
    <ProfileSection title="Ownership & control" hint="beyond GLEIF's hierarchy">
      {groups.length === 0 ? (
        <p className="profile-empty">No bank-control, beneficial-ownership, PSC, insider or succession records for this entity or its linked records.</p>
      ) : (
        groups.map((group) => (
          <ConnectionList key={`${group.edge_type}-${group.direction}`} group={group} onOpenEntity={onOpenEntity} />
        ))
      )}
    </ProfileSection>
  );
}

function PositionHistory({ cik, cusip }: { cik: string; cusip: string }) {
  const [result, setResult] = useState<ToolResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openFormula, setOpenFormula] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    getPositionHistory(cik, cusip).then(
      (value) => current && setResult(value),
      (reason) => current && setError(reason instanceof Error ? reason.message : "Position history is unavailable."),
    );
    return () => {
      current = false;
    };
  }, [cik, cusip]);

  if (error) return <p className="profile-empty">{error}</p>;
  if (!result) return <p className="profile-loading"><Loader2 className="animate-spin" /> Reading information-table rows…</p>;
  if (!result.data.found) return <p className="profile-empty">No long position in this CUSIP across recent reports.</p>;

  const facts = Object.fromEntries(result.facts.map((fact) => [fact.fact_id, fact]));
  const derivations = Object.fromEntries(result.derivations.map((derivation) => [derivation.fact_id, derivation]));
  const periods = result.data.periods as { period_of_report: string; position_value_fact_id: string }[];
  const changes = result.data.changes as {
    to_period: string;
    change_fact_id: string | null;
    percent_change_fact_id: string | null;
  }[];
  const changeFor = new Map(changes.map((change) => [change.to_period, change]));
  const warnings = [...new Set(result.evidence.flatMap((item) => item.warnings))];

  function derived(factId: string | null) {
    if (!factId || !facts[factId]) return <span>—</span>;
    const open = openFormula === factId;
    return (
      <button type="button" className={`derived-value ${open ? "is-open" : ""}`} onClick={() => setOpenFormula(open ? null : factId)}>
        {formatFactValue(facts[factId])} <Sigma />
      </button>
    );
  }

  const opened = openFormula ? derivations[openFormula] : null;

  return (
    <div className="position-history">
      <table>
        <thead>
          <tr><th>Period</th><th>Position</th><th>Change</th><th>%</th></tr>
        </thead>
        <tbody>
          {periods.map((period) => {
            const change = changeFor.get(period.period_of_report);
            return (
              <tr key={period.period_of_report}>
                <td>{period.period_of_report}</td>
                <td>{derived(period.position_value_fact_id)}</td>
                <td>{derived(change?.change_fact_id ?? null)}</td>
                <td>{derived(change?.percent_change_fact_id ?? null)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {opened && <DerivationDetail derivation={opened} facts={facts} derivations={derivations} />}
      {warnings.map((warning) => <p key={warning} className="profile-caveat">{warning}</p>)}
    </div>
  );
}

function Holdings({ detail }: { detail: EntityDetail }) {
  const [openCusip, setOpenCusip] = useState<string | null>(null);
  const sec = detail.sec_13f;
  if (!sec) return null;
  return (
    <ProfileSection title="Latest reported 13F holdings" hint={`${sec.reported_security_count.toLocaleString()} securities · ${sec.latest_period_of_report ?? "—"}`}>
      <p className="profile-caveat">
        Latest reported 13F holdings only — excludes short positions, derivatives, non-US securities, private investments and
        sub-threshold positions. Put and call rows are left out of positions.
      </p>
      {sec.scale_suspect_filings.length > 0 && (
        <p className="profile-warning">
          <AlertTriangle /> Filing {sec.scale_suspect_filings.join(", ")} was filed in whole dollars, but its implied share prices sit
          near 1/1000 of other filers&apos; - the values may really be in thousands. Shown as filed.
        </p>
      )}
      {sec.quarantined_filings.length > 0 && (
        <p className="profile-warning">
          <AlertTriangle /> {sec.quarantined_filings.length} filing{sec.quarantined_filings.length === 1 ? "" : "s"} kept out because the
          information table did not reconcile with the summary page: {sec.quarantined_filings.join("; ")}
        </p>
      )}
      <ul className="holding-rows">
        {sec.top_reported_holdings.map((holding) => {
          const open = holding.cusip !== null && openCusip === holding.cusip;
          return (
            <li key={holding.cusip ?? holding.name_of_issuer}>
              <button
                type="button"
                disabled={!holding.cusip}
                onClick={() => setOpenCusip(open ? null : holding.cusip)}
                aria-expanded={open}
              >
                {open ? <ChevronDown /> : <ChevronRight />}
                <span className="profile-name">{holding.name_of_issuer}</span>
                <code>{holding.cusip}</code>
                <strong>{formatUsd(holding.value, sec.value_unit)}</strong>
              </button>
              {open && holding.cusip && <PositionHistory cik={sec.cik} cusip={holding.cusip} />}
            </li>
          );
        })}
      </ul>
      <p className="profile-hint">Open a holding for its position across recent reports. Each total and change is computed by a named formula from the filed rows.</p>
    </ProfileSection>
  );
}

export default function EntityProfile({
  detail,
  loading,
  onOpenEntity,
}: {
  detail: EntityDetail | null;
  loading: boolean;
  onOpenEntity: (lei: string) => void;
}) {
  if (loading) {
    return <div id="entity-profile" className="entity-profile-loading"><Loader2 className="animate-spin" /> Opening entity profile…</div>;
  }
  if (!detail) return null;

  const successor = detail.connections.groups
    .find((group) => group.edge_type === "SUCCEEDED_BY" && group.direction === "outgoing")
    ?.connections[0];

  return (
    <section id="entity-profile" className="entity-profile">
      <div className="entity-profile-heading">
        <span>Entity profile</span>
        <a href={`https://search.gleif.org/#/search/lei/${detail.entity_id}`} target="_blank" rel="noreferrer">View in GLEIF ↗</a>
      </div>
      <h2>{detail.canonical_name}</h2>
      {successor && (
        <button
          type="button"
          className="profile-successor"
          onClick={() => successor.other_node_id.startsWith("lei:") && onOpenEntity(successor.other_node_id.slice(4))}
        >
          Succeeded by {successor.other_name ?? successor.other_node_id} <ArrowRight />
        </button>
      )}
      <div className="entity-profile-grid">
        <div><small>LEI</small><code>{detail.entity_id}</code></div>
        <div><small>Status</small><p>{detail.entity_status ?? "—"}</p></div>
        <div><small>Jurisdiction</small><p>{detail.jurisdiction ?? detail.legal_country ?? "—"}</p></div>
        <div><small>Registration</small><p>{detail.lineage?.registration_status ?? "—"}</p></div>
        <div><small>Next renewal</small><p>{detail.lineage?.next_renewal_date?.slice(0, 10) ?? "—"}</p></div>
        <div><small>GLEIF parents · children</small><p>{detail.parent_count} · {detail.subsidiary_count}</p></div>
      </div>
      <Identifiers detail={detail} />
      <Resolution detail={detail} onOpenEntity={onOpenEntity} />
      <Connections detail={detail} onOpenEntity={onOpenEntity} />
      <Holdings detail={detail} />
    </section>
  );
}
