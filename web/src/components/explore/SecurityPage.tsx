"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadError, Loading, NoData } from "@/components/WorkspaceStates";
import { PageHeader } from "@/components/PageHeader";
import { ChartCard, ColumnChart, RankedBarChart, TrendChart } from "@/components/charts";
import AskAgent from "@/components/explore/AskAgent";
import { MetricCard, MetricGrid, type MetricDefinition } from "@/components/metrics";
import { useResource } from "@/hooks/use-resource";
import type { SecurityView } from "@/lib/api";
import { count, day, percent, shortCount, tick, usd } from "@/lib/format";

function change(current: number | null | undefined, previous: number | null | undefined) {
  return current && previous ? ((current - previous) / previous) * 100 : null;
}

export default function SecurityPage({ identifier }: { identifier: string }) {
  const resource = useResource<SecurityView>(`/api/securities/${encodeURIComponent(identifier)}?holders=50&days=30`);
  const doc = resource.data;
  if (!doc)
    return <div className="workspace-page">{resource.error ? <LoadError error={resource.error} retry={resource.refresh} /> : <Loading />}</div>;
  const own = doc.ownership;
  const periods = own?.periods ?? [];
  const latest = periods.at(-1);
  const previous = periods.at(-2);
  const name = own?.issuer_name ?? doc.fails?.description ?? doc.symbol ?? identifier;
  const label = doc.symbol ?? doc.cusip ?? identifier;
  const movers = (own?.holders ?? [])
    .filter((holder) => holder.change)
    .sort((a, b) => Math.abs(b.change!) - Math.abs(a.change!))
    .slice(0, 12)
    .sort((a, b) => b.change! - a.change!);
  const shortDays = doc.short_volume;
  const averageShort = shortDays.length
    ? shortDays.reduce((sum, row) => sum + (row.short_ratio ?? 0), 0) / shortDays.length : null;
  const source13F = "SEC Form 13F information tables, reported quarterly";
  const latestPeriod = day(own?.latest_period);

  const filersMetric: MetricDefinition = {
    label: "13F filers holding",
    definition:
      "How many institutional filers reported a long position in this security on their latest Form 13F.",
    formula:
      "Count of distinct filer CIKs with a non-zero long position in the latest 13F period held for this CUSIP.",
    source: source13F,
    field: "Information table rows for the CUSIP, grouped by CIK",
    asOf: latestPeriod,
    value: count(latest?.holder_count),
    caveats: [
      "Form 13F covers only reportable US equity securities, and only managers above the filing threshold.",
      "A filer count is not an ownership percentage; holdings can be reported by several managers for the same beneficial owner.",
      "Positions are reported as of quarter end and filed up to 45 days later.",
    ],
  };
  const valueMetric: MetricDefinition = {
    label: "Reported value",
    definition:
      "The combined value every 13F filer reported for its long position in this security.",
    formula:
      "Sum of each filer's reported value at the latest period. Values filed before 3 January 2023 are reported in thousands and scaled on ingestion.",
    source: source13F,
    field: "Information table value column, summed by CUSIP",
    asOf: latestPeriod,
    value: usd(latest?.value_usd),
    caveats: [
      "Filers value positions using the filing's required valuation method, so the total is not a live market capitalisation.",
      "Long positions only: shorts, options and non-US securities are outside Form 13F.",
      "Values are not adjusted for double counting across related managers.",
    ],
  };
  const sharesMetric: MetricDefinition = {
    label: "Shares reported",
    definition:
      "The total shares reported across all 13F filers' long positions in the latest period.",
    formula:
      "Sum of the share quantity on every filer's information-table row for the CUSIP.",
    source: source13F,
    field: "Information table share quantity, summed by CUSIP",
    asOf: latestPeriod,
    value: shortCount(latest?.shares),
    caveats: [
      "Share classes are separate securities: a CUSIP identifies one class, not the whole issuer.",
      "Reported shares can exceed the class's free float when the same beneficially owned shares are reported by more than one manager.",
      "A quarter-over-quarter change can be a new filer, an exited filer, or a restatement.",
    ],
  };
  const shortMetric: MetricDefinition = {
    label: "Short share of volume",
    definition:
      "The average daily share of trading marked as short sale volume on FINRA-reported venues.",
    formula:
      "FINRA daily short volume ÷ total reported volume, averaged across the last N trading days (not a sum of daily balances).",
    source: "FINRA daily short sale volume files",
    asOf: shortDays.length ? `last ${shortDays.length} trading days` : undefined,
    value: averageShort !== null ? `${averageShort.toFixed(1)}%` : undefined,
    caveats: [
      "This is short sale volume, not short interest: it is the flow of trades marked short, not the open short position.",
      "Market-maker hedging puts much ordinary volume into the short column, so a high share is not by itself a bearish signal.",
      "Only FINRA-reported venues and trades are included.",
    ],
  };
  const historyMetric: MetricDefinition = {
    label: "Institutional holders by quarter",
    definition:
      "The number of 13F filers reporting a long position in this security in each quarter.",
    formula: "Distinct filer CIKs with a reported long position, per period of report.",
    source: source13F,
    field: "Information table, grouped by period of report",
    asOf: periods.length ? `through ${latestPeriod}` : undefined,
    caveats: [
      "Filers enter and leave the data set as their own filing obligations change.",
      "A missing quarter can mean no filing was ingested, not that every manager exited.",
    ],
  };
  const moversMetric: MetricDefinition = {
    label: "Biggest buyers and sellers",
    definition:
      "The largest share-count changes among filers that reported in both the latest and prior quarter.",
    formula:
      "Latest reported shares − prior-quarter reported shares, ranked by absolute change among the largest holders shown.",
    source: source13F,
    field: "Information table share quantity, latest vs prior period",
    asOf: `${latestPeriod} vs ${day(own?.previous_period)}`,
    caveats: [
      "Changes include splits, restatements and position transfers between related managers.",
      "A filer absent from the prior quarter is shown as new, not as a purchase of zero.",
      "Share counts are not adjusted for price changes.",
    ],
  };
  const shortHistoryMetric: MetricDefinition = {
    label: "Short share of daily volume",
    definition:
      "Each trading day's short volume as a share of total reported volume on FINRA venues.",
    formula: "Daily short volume ÷ daily total volume for the same venue set.",
    source: "FINRA daily short sale volume files",
    field: "Short volume and total volume, by trade date",
    asOf: shortDays.length ? `last ${shortDays.length} trading days` : undefined,
    caveats: [
      "The series is daily flow, not short interest.",
      "Venue mix and market-maker hedging move the ratio independently of conviction.",
    ],
  };
  const failsMetric: MetricDefinition = {
    label: "Fails to deliver",
    definition:
      "Outstanding CNS fail-to-deliver balances for this security on each settlement date.",
    formula:
      "SEC fails-to-deliver quantity for the settlement date, plotted as a balance rather than a daily flow.",
    source: "SEC fails-to-deliver data",
    field: "CNS fail balance by settlement date",
    asOf: doc.fails?.fails.length ? `through ${tick(doc.fails.fails.at(-1)!.settlement_date, "both")}` : undefined,
    caveats: [
      "These are outstanding balances, not new fails: consecutive days must not be added together.",
      "A fail can reflect a routine settlement delay and is not evidence of naked short selling.",
    ],
  };

  return (
    <div className="workspace-page wide">
      <PageHeader
        back={{ href: "/securities", label: "All securities" }}
        eyebrow="Security · 13F and market data"
        title={name}
        description={[doc.symbol && `Ticker ${doc.symbol}`, doc.cusip && `CUSIP ${doc.cusip}`, own?.title_of_class].filter(Boolean).join(" · ")}
        actions={
          <AskAgent question={`Who are the largest 13F holders of ${label} and how did their positions change last quarter? Also summarise its recent short sale volume, with charts.`} />
        }
      />
      <div className="mb-6 flex flex-wrap items-center gap-2">
        {own?.tickers.map((ticker) => <Badge key={ticker} variant="accent">{ticker}</Badge>)}
        {doc.cusip && <Badge variant="outline">{doc.cusip}</Badge>}
        {own && <Badge variant="neutral">13F · {latestPeriod}</Badge>}
        {shortDays.length > 0 && <Badge variant="neutral">FINRA · {shortDays.length} days</Badge>}
      </div>
      {own && latest ? (
        <>
          <MetricGrid>
            <MetricCard metric={filersMetric} value={count(latest.holder_count)}
              delta={change(latest.holder_count, previous?.holder_count)}
              deltaNote={`since ${day(previous?.period_of_report)}`}
              footnote={previous ? `${count(previous.holder_count)} at ${day(previous.period_of_report)}` : day(latest.period_of_report)} />
            <MetricCard metric={valueMetric} value={usd(latest.value_usd)} delta={change(latest.value_usd, previous?.value_usd)}
              deltaNote="quarter over quarter" footnote="long positions only" />
            <MetricCard metric={sharesMetric} value={shortCount(latest.shares)} delta={change(latest.shares, previous?.shares)}
              deltaNote="quarter over quarter" footnote={previous ? `${shortCount(previous.shares)} the period before` : ""} />
            {averageShort !== null && (
              <MetricCard metric={shortMetric} value={`${averageShort.toFixed(1)}%`}
                footnote={`average, last ${shortDays.length} trading days`} />
            )}
          </MetricGrid>
          <p className="workspace-note mt-3">
            Latest reported 13F holdings only. The filing excludes short
            positions, derivatives, non-US securities and sub-threshold
            positions. Each figure carries its own note.
          </p>

          <div className="split-main mt-8">
            <div className="grid min-w-0 gap-6">
              <div className="grid gap-6 lg:grid-cols-2">
                <ChartCard title="Institutional holders by quarter" description="13F filers reporting a long position" explain={historyMetric}>
                  <ColumnChart series={[{ key: "holders", label: "Filers" }]}
                    data={periods.map((period) => ({ label: tick(period.period_of_report), holders: period.holder_count }))} />
                </ChartCard>
                <ChartCard title="Reported 13F value by quarter" description="Sum of every filer's long position, as filed" explain={valueMetric}>
                  <TrendChart format="usd" series={[{ key: "value", label: "Reported value" }]}
                    data={periods.map((period) => ({ label: tick(period.period_of_report), value: period.value_usd }))} />
                </ChartCard>
              </div>
              {movers.length > 0 && (
                <ChartCard title={`Biggest buyers and sellers · ${latestPeriod}`}
                  description={`Change in shares since ${day(own.previous_period)} among the ${own.holders.length} largest holders`}
                  explain={moversMetric}>
                  <RankedBarChart signed label="Change in shares"
                    data={movers.map((holder) => ({ label: holder.filer_name ?? holder.cik, value: holder.change! }))} />
                </ChartCard>
              )}
              <Card className="gap-0 overflow-hidden py-0 shadow-none">
                <CardHeader className="border-b px-5 py-4">
                  <CardTitle className="text-sm font-medium">Largest holders · {latestPeriod}</CardTitle>
                  <CardDescription className="text-xs">
                    {own.holders.length} largest of {count(own.holder_count)} filers by reported value; change in shares since {day(own.previous_period)}
                  </CardDescription>
                </CardHeader>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-12 pl-5 text-right">#</TableHead>
                      <TableHead>Filer</TableHead>
                      <TableHead className="text-right">Value</TableHead>
                      <TableHead className="text-right">Shares</TableHead>
                      <TableHead className="text-right">Change</TableHead>
                      <TableHead className="pr-5 text-right">% change</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {own.holders.map((holder, index) => (
                      <TableRow key={holder.cik}>
                        <TableCell className="pl-5 text-right text-muted-foreground tabular-nums">{index + 1}</TableCell>
                        <TableCell className="min-w-56 whitespace-normal">
                          {holder.lei
                            ? <Link className="font-medium hover:text-primary hover:underline" href={`/entities/${holder.lei}?tab=holdings`}>{holder.filer_name}</Link>
                            : <span className="font-medium">{holder.filer_name}</span>}
                          <div className="text-xs text-muted-foreground">CIK {holder.cik}</div>
                        </TableCell>
                        <TableCell className="text-right font-medium tabular-nums">{usd(holder.value_usd)}</TableCell>
                        <TableCell className="text-right tabular-nums">{shortCount(holder.shares)}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {holder.new ? <Badge variant="positive">New</Badge>
                            : holder.change === null ? "—"
                            : <span className={holder.change > 0 ? "text-emerald-700" : holder.change < 0 ? "text-destructive" : ""}>{holder.change > 0 ? "+" : ""}{shortCount(holder.change)}</span>}
                        </TableCell>
                        <TableCell className="pr-5 text-right">
                          {holder.new || holder.percent_change === null ? <span className="text-muted-foreground">—</span>
                            : <Badge variant={holder.percent_change > 0 ? "positive" : holder.percent_change < 0 ? "critical" : "neutral"}>{percent(holder.percent_change)}</Badge>}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Card>
            </div>
            <aside>
              <section className="aside-card">
                <div className="aside-card-head"><h2>Security record</h2></div>
                <div className="aside-card-body">
                  <dl>
                    <div className="aside-row"><dt>CUSIP</dt><dd>{doc.cusip ?? "—"}</dd></div>
                    <div className="aside-row"><dt>Ticker</dt><dd>{doc.symbol ?? "—"}</dd></div>
                    <div className="aside-row"><dt>Class</dt><dd>{own.title_of_class ?? "—"}</dd></div>
                    <div className="aside-row"><dt>Latest 13F</dt><dd>{day(own.latest_period)}</dd></div>
                    <div className="aside-row"><dt>Prior 13F</dt><dd>{day(own.previous_period)}</dd></div>
                    <div className="aside-row"><dt>Filers</dt><dd>{count(own.holder_count)}</dd></div>
                    {doc.fails && <div className="aside-row"><dt>FTD feed</dt><dd>{doc.fails.symbol ?? doc.cusip}</dd></div>}
                  </dl>
                </div>
              </section>
              <section className="aside-card">
                <div className="aside-card-head"><h2>Reading the figures</h2></div>
                <div className="aside-card-body">
                  <p className="py-2 text-xs leading-relaxed text-muted-foreground">
                    Each metric opens a note with its filed field and caveats.
                    Form 13F is a quarterly, delayed snapshot of long US equity
                    positions — not a complete portfolio.
                  </p>
                  <Link className="workspace-text-link" href="/coverage">
                    See data coverage
                  </Link>
                </div>
              </section>
            </aside>
          </div>
        </>
      ) : null}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        {shortDays.length > 0 && (
          <ChartCard title="Short share of daily volume" description={`FINRA-reported venues · ${doc.symbol} · last ${shortDays.length} trading days`}
            explain={shortHistoryMetric}
            footer="Daily short sale volume, not short interest: market-maker hedging puts much of ordinary volume here.">
            <TrendChart format="percent" series={[{ key: "ratio", label: "Short share" }]}
              data={shortDays.map((row) => ({ label: tick(row.trade_date, "day"), ratio: row.short_ratio }))} />
          </ChartCard>
        )}
        {doc.fails && doc.fails.fails.length > 0 && (
          <ChartCard title="Fails to deliver" description={`Shares failed, by settlement date · ${doc.fails.symbol ?? doc.cusip}`}
            explain={failsMetric}
            footer="Outstanding CNS fail balances — balances, not new fails, so days must not be added up.">
            <ColumnChart series={[{ key: "fails", label: "Shares failed" }]}
              data={doc.fails.fails.slice(-30).map((row) => ({ label: tick(row.settlement_date, "day"), fails: row.quantity }))} />
          </ChartCard>
        )}
      </div>
      {!own && !shortDays.length && !doc.fails && <NoData title="No published data" description="No 13F, short volume or fails data for this security." />}
    </div>
  );
}
