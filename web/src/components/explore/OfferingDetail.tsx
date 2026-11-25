"use client";

import Link from "next/link";
import { ExternalLink } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadError, Loading } from "@/components/WorkspaceStates";
import { PageHeader } from "@/components/PageHeader";
import { MetricCard, MetricGrid, type MetricDefinition } from "@/components/metrics";
import { useResource } from "@/hooks/use-resource";
import type { Offering } from "@/lib/api";
import { count, day, edgarFiling, usd } from "@/lib/format";

// Form D Item 6 codes, as SEC's data set reports them.
const EXEMPTIONS: Record<string, string> = {
  "06b": "Rule 506(b)", "06c": "Rule 506(c)", "04a5": "Section 4(a)(5)", "3C": "Investment Company Act 3(c)",
  "3C.1": "3(c)(1)", "3C.7": "3(c)(7)", "3C.5": "3(c)(5)", "504": "Rule 504",
};

function Detail({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-1 py-2.5 text-sm">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  );
}

export default function OfferingDetail({ accession }: { accession: string }) {
  const resource = useResource<Offering>(`/api/offerings/${encodeURIComponent(accession)}`);
  const doc = resource.data;
  if (!doc)
    return <div className="workspace-page">{resource.error ? <LoadError error={resource.error} retry={resource.refresh} /> : <Loading />}</div>;
  const progress = doc.total_offering && doc.total_sold !== null ? (doc.total_sold / doc.total_offering) * 100 : null;
  const source = "SEC Form D notice, EDGAR";
  const asOf = day(doc.filing_date);

  const soldMetric: MetricDefinition = {
    label: "Amount sold",
    definition:
      "The cumulative amount the issuer reports having sold in this offering as of the filing.",
    formula:
      "Form D Item 13(b), “Total Amount Sold”. An amendment (D/A) restates the running total rather than reporting only new sales in the period.",
    source,
    field: "Item 13(b) — total amount sold",
    asOf,
    value: usd(doc.total_sold),
    caveats: [
      "Amounts are self-reported and cumulative; an amendment includes earlier sales.",
      "A filing is a notice, not evidence that the offering closed or that the money was called.",
      "A later amendment can restate the same offering, so compare against the latest notice before using the number.",
    ],
    href: edgarFiling(doc.issuer_cik, doc.accession_number),
    hrefLabel: "Open on EDGAR",
  };
  const offeringMetric: MetricDefinition = {
    label: "Offering size",
    definition:
      "The total amount the issuer says it may offer under this exemption.",
    formula:
      "Form D Item 13(a), “Total Offering Amount”. An issuer can mark the offering indefinite instead of naming a ceiling.",
    source,
    field: "Item 13(a) — total offering amount",
    asOf,
    value: doc.offering_indefinite ? "Indefinite" : usd(doc.total_offering),
    caveats: [
      "The offering amount is a ceiling, not money raised; compare it with amount sold.",
      "Indefinite offerings have no fixed ceiling and cannot be shown as a percentage complete.",
    ],
    href: edgarFiling(doc.issuer_cik, doc.accession_number),
    hrefLabel: "Open on EDGAR",
  };
  const investorsMetric: MetricDefinition = {
    label: "Investors so far",
    definition:
      "The number of investors the issuer reports having already invested in the offering.",
    formula:
      "Form D Item 14: total number of investors already invested, and how many are non-accredited.",
    source,
    field: "Item 14 — investors",
    asOf,
    value: count(doc.investor_count),
    caveats: [
      "Investor counts are self-reported and cumulative across amendments.",
      "The count does not show commitment size or whether capital was called.",
    ],
    href: edgarFiling(doc.issuer_cik, doc.accession_number),
    hrefLabel: "Open on EDGAR",
  };
  const minimumMetric: MetricDefinition = {
    label: "Minimum investment",
    definition:
      "The smallest amount the issuer says it will accept from an outside investor.",
    formula:
      "Form D Item 11, “Minimum Investment Amount”. Commissions and finders' fees are Item 15 and are separate.",
    source,
    field: "Item 11 — minimum investment",
    asOf,
    value: usd(doc.minimum_investment),
    caveats: [
      "The minimum is the issuer's stated threshold, not the amount a particular investor committed.",
      "Commissions and finders' fees are disclosed separately and are not part of the minimum.",
    ],
    href: edgarFiling(doc.issuer_cik, doc.accession_number),
    hrefLabel: "Open on EDGAR",
  };

  return (
    <div className="workspace-page wide">
      <PageHeader
        back={{ href: `/raises?kind=${doc.is_fund ? "fund" : "company"}`, label: "All private raises" }}
        eyebrow={`Form ${doc.submission_type} · ${doc.fund_type ?? doc.industry_group ?? "Regulation D"}`}
        title={doc.issuer_name}
        description={
          <>
            {[doc.city, doc.state_description].filter(Boolean).join(", ")} · {doc.entity_type ?? "Entity type not given"}
            {doc.jurisdiction ? ` · incorporated in ${doc.jurisdiction}` : ""}
            {doc.year_of_incorporation ? ` (${doc.year_of_incorporation})` : ""}
          </>
        }
        actions={
          <Button variant="outline" size="sm" asChild>
            <a href={edgarFiling(doc.issuer_cik, doc.accession_number)} target="_blank" rel="noreferrer">Filing on EDGAR <ExternalLink /></a>
          </Button>
        }
      />
      <div className="mb-6 flex flex-wrap items-center gap-2">
        <Badge variant={doc.is_amendment ? "caution" : "positive"}>{doc.is_amendment ? "Amendment (D/A)" : "New notice"}</Badge>
        {doc.fund_type && <Badge variant="accent">{doc.fund_type}</Badge>}
        {doc.industry_group && <Badge variant="outline">{doc.industry_group}</Badge>}
        <span className="text-xs text-muted-foreground">Filed {asOf}</span>
      </div>
      <MetricGrid>
        <MetricCard metric={soldMetric} value={usd(doc.total_sold)}
          footnote={progress !== null ? `${progress.toFixed(0)}% of the offering · filed ${asOf}` : `filed ${asOf}`} />
        <MetricCard metric={offeringMetric} value={doc.offering_indefinite ? "Indefinite" : usd(doc.total_offering)}
          footnote={`remaining ${doc.total_remaining === null ? "indefinite" : usd(doc.total_remaining)}`} />
        <MetricCard metric={investorsMetric} value={count(doc.investor_count)}
          footnote={`${count(doc.non_accredited_count)} non-accredited`} />
        <MetricCard metric={minimumMetric} value={usd(doc.minimum_investment)}
          footnote={`commissions ${usd(doc.sales_commission)} · finders ${usd(doc.finders_fee)}`} />
      </MetricGrid>
      <p className="workspace-note mt-3">
        A Form D notice is filed within 15 days of the first sale. Amounts are
        cumulative and self-reported
        {doc.is_amendment ? `; this amendment restates ${doc.previous_accession_number ?? "an earlier filing"}.` : "; later amendments may restate them."}
      </p>

      {progress !== null && (
        <div className="surface mt-6 px-5 py-4">
          <div className="mb-2 flex items-baseline justify-between gap-4">
            <span className="text-xs font-semibold tracking-wide uppercase text-muted-foreground">Offering progress</span>
            <span className="text-xs tabular-nums text-muted-foreground">{progress.toFixed(0)}% of stated offering</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[var(--fill)]">
            <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: `${Math.min(100, Math.max(0, progress))}%` }} />
          </div>
        </div>
      )}

      <div className="split-main mt-8">
        <div className="grid min-w-0 gap-6">
          <Card className="gap-0 overflow-hidden py-0 shadow-none">
            <CardHeader className="border-b px-5 py-4">
              <CardTitle className="text-sm font-medium">Related persons</CardTitle>
              <CardDescription className="text-xs">{doc.people.length} named on the notice</CardDescription>
            </CardHeader>
            <Table>
              <TableHeader><TableRow><TableHead className="pl-5">Name</TableHead><TableHead>Role</TableHead><TableHead className="pr-5">Location</TableHead></TableRow></TableHeader>
              <TableBody>
                {doc.people.map((person, index) => (
                  <TableRow key={`${person.name}-${index}`}>
                    <TableCell className="pl-5 whitespace-normal">
                      <Link className="font-medium hover:text-primary hover:underline" href={`/raises?q=${encodeURIComponent(person.name)}&days=`}>{person.name}</Link>
                      {person.clarification && <div className="text-xs text-muted-foreground">{person.clarification}</div>}
                    </TableCell>
                    <TableCell><div className="flex flex-wrap gap-1">{person.relationships.map((role) => <Badge key={role} variant="neutral">{role}</Badge>)}</div></TableCell>
                    <TableCell className="pr-5 text-muted-foreground">{[person.city, person.state].filter(Boolean).join(", ") || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
          {doc.recipients.length > 0 && (
            <Card className="gap-0 overflow-hidden py-0 shadow-none">
              <CardHeader className="border-b px-5 py-4">
                <CardTitle className="text-sm font-medium">Sales compensation recipients</CardTitle>
                <CardDescription className="text-xs">Brokers and placement agents paid to sell the offering</CardDescription>
              </CardHeader>
              <Table>
                <TableHeader><TableRow><TableHead className="pl-5">Recipient</TableHead><TableHead>Broker-dealer</TableHead><TableHead className="pr-5">States solicited</TableHead></TableRow></TableHeader>
                <TableBody>
                  {doc.recipients.map((recipient, index) => (
                    <TableRow key={`${recipient.name}-${index}`}>
                      <TableCell className="pl-5 font-medium whitespace-normal">{recipient.name}{recipient.crd_number && <div className="text-xs font-normal text-muted-foreground">CRD {recipient.crd_number}</div>}</TableCell>
                      <TableCell className="whitespace-normal">{recipient.broker_dealer_name ?? "—"}{recipient.broker_dealer_crd ? <span className="text-muted-foreground"> · CRD {recipient.broker_dealer_crd}</span> : null}</TableCell>
                      <TableCell className="pr-5 whitespace-normal text-muted-foreground">{recipient.states.join(", ") || (recipient.foreign_solicitation ? "Foreign" : "—")}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          )}
        </div>
        <aside>
          <section className="aside-card">
            <div className="aside-card-head"><h2>Offering record</h2></div>
            <div className="aside-card-body">
              <CardContent className="px-0">
                <dl className="divide-y">
                  <Detail label="Exemptions claimed">
                    <div className="flex flex-wrap gap-1">{doc.exemptions.map((code) => <Badge key={code} variant="outline" className="max-w-full whitespace-normal text-left">{EXEMPTIONS[code] ?? code}</Badge>)}</div>
                  </Detail>
                  <Detail label="Issuer size">{doc.nav_range ?? doc.revenue_range ?? "—"}</Detail>
                  <Detail label="First sale">{doc.first_sale_yet_to_occur ? "Yet to occur" : day(doc.first_sale_date)}{doc.more_than_one_year ? " · runs more than a year" : ""}</Detail>
                  <Detail label="1940 Act">{doc.is_40_act === null ? "—" : doc.is_40_act ? "Registered investment company" : "Not registered"}</Detail>
                  <Detail label="Co-issuers">{doc.co_issuer_count}</Detail>
                  <Detail label="Issuer CIK">{doc.issuer_cik}</Detail>
                  <Detail label="Accession">{doc.accession_number}</Detail>
                </dl>
              </CardContent>
            </div>
          </section>
          <section className="aside-card">
            <div className="aside-card-head"><h2>Read across</h2></div>
            <div className="aside-card-body">
              <p className="py-2 text-xs leading-relaxed text-muted-foreground">
                The issuer is named on the notice; it is not yet resolved to a
                GLEIF legal entity. Use the research agent to connect it to a
                register or to the people behind it.
              </p>
              <Link className="workspace-text-link" href="/entities">
                Search the registers
              </Link>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
