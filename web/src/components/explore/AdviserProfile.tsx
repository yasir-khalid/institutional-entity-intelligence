"use client";

import Link from "next/link";
import { ExternalLink, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadError, Loading } from "@/components/WorkspaceStates";
import { PageHeader } from "@/components/PageHeader";
import { ChartCard, RankedBarChart, TrendChart } from "@/components/charts";
import AskAgent from "@/components/explore/AskAgent";
import { MetricCard, MetricGrid, MetricInfo, type MetricDefinition } from "@/components/metrics";
import { useResource } from "@/hooks/use-resource";
import type { Adviser } from "@/lib/api";
import { count, day, tick, usd } from "@/lib/format";

const FUND_COUNTS: [keyof Adviser, string][] = [
  ["hedge_fund_count", "Hedge"], ["pe_fund_count", "Private equity"], ["vc_fund_count", "Venture capital"],
  ["real_estate_fund_count", "Real estate"], ["securitized_fund_count", "Securitized"],
  ["liquidity_fund_count", "Liquidity"], ["other_fund_count", "Other"],
];

function RecordRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="aside-row">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

export default function AdviserProfile({ crd }: { crd: string }) {
  const resource = useResource<Adviser>(`/api/advisers/${encodeURIComponent(crd)}`);
  const firm = resource.data;
  if (!firm)
    return (
      <div className="workspace-page">
        {resource.error ? <LoadError error={resource.error} retry={resource.refresh} /> : <Loading />}
      </div>
    );
  const history = firm.history.filter((point) => point.raum !== null);
  const first = history[0]?.raum ?? null;
  const change = first && firm.raum ? ((firm.raum - first) / first) * 100 : null;
  const clients = firm.client_types;
  const clientTotal = clients.reduce((sum, client) => sum + (client.raum ?? 0), 0);
  const funds = FUND_COUNTS.filter(([key]) => Number(firm[key]) > 0);
  const website = firm.website ? (firm.website.startsWith("http") ? firm.website : `https://${firm.website}`).toLowerCase() : null;
  const brand = firm.business_name.split(/[ ,]/)[0];
  const iapd = `https://adviserinfo.sec.gov/firm/summary/${firm.crd_number}`;
  const source = "SEC Form ADV Part 1A, monthly investment adviser extracts";
  const asOf = day(firm.snapshot_date);

  const raumMetric: MetricDefinition = {
    label: "Regulatory AUM",
    definition:
      "The gross value of assets the adviser manages, as reported on its latest Form ADV Part 1A.",
    formula:
      "Item 5.F(2)(c): the total regulatory assets under management the adviser reports across every client type, before deducting leverage, uncalled commitments or non-fee-paying assets.",
    source,
    field: "Item 5.F(2)(c) — total regulatory assets under management",
    asOf,
    value: usd(firm.raum),
    caveats: [
      "Regulatory AUM is gross, so it is usually larger than the client-facing AUM a manager quotes.",
      "The figure changes when the adviser files an amendment, not continuously.",
      "Each monthly extract is a point-in-time snapshot; an amended filing restates earlier figures.",
    ],
    href: iapd,
    hrefLabel: "Open IAPD",
  };
  const discretionaryMetric: MetricDefinition = {
    label: "Discretionary",
    definition:
      "The part of regulatory AUM the adviser reports managing with discretionary authority.",
    formula:
      "Item 5.F(2)(a): regulatory AUM reported as discretionary. The remainder is non-discretionary.",
    source,
    field: "Item 5.F(2)(a) — discretionary regulatory AUM",
    asOf,
    value: usd(firm.raum_discretionary),
    caveats: [
      "Discretionary and non-discretionary amounts are self-classified by the adviser on the filing.",
      "Non-US client assets are reported separately under Item 5.F(3); do not add that line to the Item 5.F(2) totals.",
    ],
    href: iapd,
    hrefLabel: "Open IAPD",
  };
  const accountsMetric: MetricDefinition = {
    label: "Accounts",
    definition:
      "The number of accounts the adviser reports, alongside its reported headcount.",
    formula:
      "Item 5.F(2)(f) total accounts. Employees are Item 5.A; advisory employees are Item 5.B(1).",
    source,
    field: "Item 5.F(2)(f), Item 5.A and Item 5.B(1)",
    asOf,
    value: count(firm.accounts),
    caveats: [
      "Accounts are not clients: one client may hold several accounts.",
      "Headcount is self-reported and can include part-time and affiliated staff as the adviser classifies them.",
    ],
    href: iapd,
    hrefLabel: "Open IAPD",
  };
  const fundsMetric: MetricDefinition = {
    label: "Private funds",
    definition:
      "The number of private funds the adviser reports advising, and their combined gross assets.",
    formula:
      "Item 7.B(1) count of private funds, with total gross assets of those funds reported alongside it.",
    source,
    field: "Item 7.B — private funds",
    asOf,
    value: count(firm.private_fund_count),
    caveats: [
      "Gross assets are fund-level assets, not the adviser's own AUM or fee base.",
      "Fund counts and strategy categories are self-reported by the adviser and are not audited by the SEC.",
    ],
    href: iapd,
    hrefLabel: "Open IAPD",
  };
  const historyMetric: MetricDefinition = {
    label: "Regulatory AUM over time",
    definition:
      "Every monthly Form ADV snapshot of regulatory AUM held for this adviser.",
    formula:
      "One point per ingestion snapshot, using Item 5.F(2)(c). A step down can be a restatement as well as a real change.",
    source,
    field: "Item 5.F(2)(c), one row per snapshot",
    asOf: `${history.length} snapshots through ${asOf}`,
    caveats: [
      "The series is not a performance return: flows, market moves and filing restatements all move the line.",
      "The value only changes when the adviser files an amendment.",
    ],
  };
  const clientMetric: MetricDefinition = {
    label: "Regulatory AUM by client type",
    definition:
      "How the adviser's reported regulatory AUM is distributed across the client categories in Item 5.D.",
    formula:
      "Item 5.D(3): regulatory AUM reported for each client type. Client counts and “fewer than 5” flags come from Item 5.D(1) and (2).",
    source,
    field: "Item 5.D — clients by type",
    asOf,
    caveats: [
      "Client types are self-reported and not mutually exclusive in every filing.",
      "A “fewer than 5” client count is a disclosure threshold, not a precise count.",
    ],
  };

  return (
    <div className="workspace-page wide">
      <PageHeader
        back={{ href: "/advisers", label: "All investment advisers" }}
        eyebrow="Form ADV · Part 1A"
        title={firm.business_name}
        description={
          <>
            {[firm.street1, firm.city, firm.state, firm.postal_code].filter(Boolean).join(", ")}
            {firm.phone ? ` · ${firm.phone}` : ""}
          </>
        }
        actions={
          <>
            <AskAgent entityId={firm.lei} question={`Summarise ${firm.business_name}'s Form ADV (CRD ${firm.crd_number}): regulatory AUM and how it changed, its clients and its private funds.`} />
            <Button variant="outline" size="sm" asChild>
              <a href={iapd} target="_blank" rel="noreferrer">IAPD <ExternalLink /></a>
            </Button>
            {website && (
              <Button variant="outline" size="sm" asChild>
                <a href={website} target="_blank" rel="noreferrer">Website <ExternalLink /></a>
              </Button>
            )}
          </>
        }
      />
      <div className="mb-6 flex flex-wrap items-center gap-2">
        <Badge variant={firm.firm_type === "ERA" ? "neutral" : "accent"}>
          {firm.firm_type === "ERA" ? "Exempt reporting adviser" : "SEC registered adviser"}
        </Badge>
        {firm.fund_types.map((type) => <Badge key={type} variant="outline">{type}</Badge>)}
        <span className="text-xs text-muted-foreground">Latest snapshot {asOf}</span>
      </div>
      <MetricGrid>
        <MetricCard metric={raumMetric} value={usd(firm.raum)} delta={change}
          deltaNote={history.length > 1 ? `since ${day(history[0].snapshot_date)}` : undefined}
          footnote={history.length > 1 ? `vs ${usd(first)} on ${day(history[0].snapshot_date)}` : `filed ${day(firm.latest_filing_date)}`} />
        <MetricCard metric={discretionaryMetric} value={usd(firm.raum_discretionary)}
          footnote={`${usd(firm.raum_non_us)} for non-US clients`} />
        <MetricCard metric={accountsMetric} value={count(firm.accounts)}
          footnote={`${count(firm.employees)} employees, ${count(firm.advisory_employees)} advisory`} />
        <MetricCard metric={fundsMetric} value={count(firm.private_fund_count)}
          footnote={`${usd(firm.private_fund_gross_assets)} gross assets`} />
      </MetricGrid>
      <p className="workspace-note mt-3">
        Open the note beside any figure for its definition, filed field and the
        caveats that change how it should be read.
      </p>

      <div className="split-main mt-8">
        <div className="grid min-w-0 gap-6">
          <ChartCard
            title="Regulatory AUM over time"
            description={`${history.length} monthly Form ADV snapshots; the value changes when an amendment is filed`}
            explain={historyMetric}
          >
            <TrendChart format="usd" stepped series={[{ key: "raum", label: "Regulatory AUM" }]}
              data={history.map((point) => ({ label: tick(point.snapshot_date, "both"), raum: point.raum }))} />
          </ChartCard>

          {funds.length > 0 && (
            <ChartCard title="Private funds by type" description="Item 7.B(2) counts by the adviser's reported strategy" explain={fundsMetric}>
              <RankedBarChart label="Funds"
                data={funds.map(([key, label]) => ({ label, value: Number(firm[key]) }))} />
            </ChartCard>
          )}

          {clients.length > 0 && (
            <Card className="gap-0 overflow-hidden py-0 shadow-none">
              <CardHeader className="gap-1 border-b px-5 py-4">
                <CardTitle className="flex items-center gap-1.5 text-sm font-medium">
                  Who the money is for
                  <MetricInfo metric={clientMetric} />
                </CardTitle>
                <CardDescription className="text-xs">Regulatory AUM by client type, Item 5.D</CardDescription>
              </CardHeader>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="pl-5">Client type</TableHead>
                    <TableHead className="text-right">Clients</TableHead>
                    <TableHead className="text-right">Regulatory AUM</TableHead>
                    <TableHead className="w-[28%] pr-5">Share</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {clients.map((client) => {
                    const share = clientTotal ? ((client.raum ?? 0) / clientTotal) * 100 : 0;
                    return (
                      <TableRow key={client.client_type}>
                        <TableCell className="pl-5 whitespace-normal">{client.client_type}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {client.fewer_than_five ? <Badge variant="neutral">fewer than 5</Badge> : count(client.client_count)}
                        </TableCell>
                        <TableCell className="text-right font-medium tabular-nums">{usd(client.raum)}</TableCell>
                        <TableCell className="pr-5">
                          <div className="flex items-center gap-2">
                            <div className="h-1.5 flex-1 rounded-full bg-muted">
                              <span className="block h-full rounded-full bg-chart-1" style={{ width: `${share}%` }} />
                            </div>
                            <span className="w-9 text-right text-xs tabular-nums text-muted-foreground">{Math.round(share)}%</span>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </Card>
          )}
        </div>

        <aside>
          <section className="aside-card">
            <div className="aside-card-head">
              <h2>Firm record</h2>
            </div>
            <div className="aside-card-body">
              <dl>
                <RecordRow label="CRD">{firm.crd_number}</RecordRow>
                <RecordRow label="SEC file">{firm.sec_number ?? "—"}</RecordRow>
                <RecordRow label="CIK">{firm.cik ?? "—"}</RecordRow>
                <RecordRow label="LEI (1.P)">
                  {firm.lei ? <Link className="text-primary hover:underline" href={`/entities/${firm.lei}`}>{firm.lei}</Link> : "Not reported"}
                </RecordRow>
                <RecordRow label="13F CIK">
                  {firm.thirteen_f_cik
                    ? <Link className="text-primary hover:underline" href={firm.lei ? `/entities/${firm.lei}?tab=holdings` : `/securities`}>{firm.thirteen_f_cik}</Link>
                    : "Not named on a 13F cover"}
                </RecordRow>
                <RecordRow label="Legal form">{firm.legal_form ?? "—"}</RecordRow>
                <RecordRow label="Filed">{day(firm.latest_filing_date)}</RecordRow>
                <RecordRow label="Source"><span className="text-xs">{firm.source_file}</span></RecordRow>
              </dl>
            </div>
          </section>
          <section className="aside-card">
            <div className="aside-card-head">
              <h2>Read across</h2>
            </div>
            <div className="aside-card-body">
              <Link className="flex items-start gap-2 border-b border-[var(--line-soft)] py-2.5 text-xs text-[var(--accent)] hover:underline" href={`/raises?q=${encodeURIComponent(brand)}&days=`}>
                <FileText className="mt-0.5 size-3.5 shrink-0" />
                <span>Form D offerings by issuers named “{brand}”</span>
              </Link>
              {firm.lei && (
                <Link className="flex items-start gap-2 border-b border-[var(--line-soft)] py-2.5 text-xs text-[var(--accent)] hover:underline" href={`/entities/${firm.lei}?tab=holdings`}>
                  <FileText className="mt-0.5 size-3.5 shrink-0" />
                  <span>Latest reported 13F holdings</span>
                </Link>
              )}
              <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
                Form ADV is filed by the adviser and is not audited by the SEC.
                Figures are reproduced as filed, with the field label attached.
              </p>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}
