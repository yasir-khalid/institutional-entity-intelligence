"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { LoadError, Loading, NoData } from "@/components/WorkspaceStates";
import { PageHeader } from "@/components/PageHeader";
import { ChartCard, RankedBarChart } from "@/components/charts";
import type { MetricDefinition } from "@/components/metrics";
import AskAgent from "@/components/explore/AskAgent";
import { useResource } from "@/hooks/use-resource";
import type { OfferingSummary } from "@/lib/api";
import { count, day, usd } from "@/lib/format";

const FUND_TYPES = ["Hedge Fund", "Private Equity Fund", "Venture Capital Fund", "Other Investment Fund"];
const INDUSTRIES = [
  "Other Technology", "Biotechnology", "Other Health Care", "Pharmaceuticals", "Other Real Estate", "Commercial",
  "Residential", "REITS and Finance", "Investing", "Other Banking and Financial Services", "Insurance", "Oil and Gas",
  "Other Energy", "Manufacturing", "Business Services", "Computers", "Retailing", "Restaurants", "Other",
];
const WINDOWS = [["7", "Last week"], ["30", "Last month"], ["92", "Last quarter"], ["all", "All filings"]];
const ALL = "all";
const PAGE = 50;

const SOLD_METRIC: MetricDefinition = {
  label: "Amount sold",
  definition:
    "The cumulative amount an issuer reports having sold in a Form D offering as of the filing.",
  formula:
    "Form D Item 13(b), “Total Amount Sold”. An amendment (D/A) restates the running total rather than reporting only new sales in the window.",
  source: "SEC Form D notices",
  field: "Item 13(b)",
  caveats: [
    "Amounts are self-reported and cumulative; a D/A includes earlier sales.",
    "A filing is a notice, not evidence that the offering closed or that capital was called.",
  ],
};

type Feed = { items: OfferingSummary[]; window: { from?: string; to?: string }; next_offset: number | null };

export default function OfferingFeed({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const router = useRouter();
  const params = new URLSearchParams(searchParams);
  const kind = params.get("kind") === "company" ? "company" : "fund";
  const days = params.get("days") || (params.has("days") ? ALL : "7");
  const type = params.get("type") || ALL;
  const newOnly = params.get("new_only") === "true";
  const sort = params.get("sort") === "largest" ? "largest" : "newest";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [state, setState] = useState(params.get("state") ?? "");
  const api = new URLSearchParams({ kind });
  if (days !== ALL) api.set("days", days);
  if (type !== ALL) api.set(kind === "fund" ? "fund_type" : "industry", type);
  for (const key of ["q", "state"]) if (params.get(key)) api.set(key, params.get(key)!);
  if (newOnly) api.set("new_only", "true");
  const feed = useResource<Feed>(`/api/offerings?${api.toString()}${sort === "largest" ? "&sort=largest" : ""}&offset=${offset}&limit=${PAGE}`);
  const top = useResource<Feed>(days !== ALL ? `/api/offerings?${api.toString()}&sort=largest&limit=10` : null);
  function go(changes: Record<string, string>, page = 0) {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (key === "days") next.set("days", value === ALL ? "" : value);
      else if (value && value !== ALL) next.set(key, value);
      else next.delete(key);
    }
    if (page) next.set("offset", String(page));
    else next.delete("offset");
    router.push(`/raises?${next.toString()}`);
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    go({ q: query.trim(), state: state.trim().toUpperCase() });
  }
  const data = feed.data;
  const label = kind === "fund" ? (type === ALL ? "private funds" : type.toLowerCase().replace(/ fund$/, " funds")) : (type === ALL ? "companies" : `${type} companies`);
  const leaders = (top.data?.items ?? []).filter((item) => item.total_sold);
  return (
    <div className="workspace-page wide">
      <PageHeader
        eyebrow="Form D · Regulation D"
        title="Private raises"
        description="Notices of exempt offerings. Amounts sold are cumulative and self-reported; an amendment restates the running total, and a filing is not evidence that the offering closed."
        actions={
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={kind}
            onValueChange={(value) => value && go({ kind: value, type: ALL })}
            aria-label="Raise type"
          >
            <ToggleGroupItem value="fund">Fund raises</ToggleGroupItem>
            <ToggleGroupItem value="company">Startup &amp; company raises</ToggleGroupItem>
          </ToggleGroup>
        }
      />
      <div className="toolbar-surface mb-6">
          <form className="flex w-full flex-wrap items-end gap-2.5" onSubmit={submit}>
            <Field className="min-w-56 flex-1">
              <FieldLabel htmlFor="raise-q">Issuer or person</FieldLabel>
              <Input id="raise-q" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. Sequoia" />
            </Field>
            <Field className="w-20">
              <FieldLabel htmlFor="raise-state">State</FieldLabel>
              <Input id="raise-state" value={state} onChange={(event) => setState(event.target.value)} maxLength={2} placeholder="CA" />
            </Field>
            <Field className="w-36">
              <FieldLabel>Filed</FieldLabel>
              <Select value={days} onValueChange={(value) => go({ days: value })}>
                <SelectTrigger aria-label="Filed" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{WINDOWS.map(([value, text]) => <SelectItem key={value} value={value}>{text}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field className="w-44">
              <FieldLabel>{kind === "fund" ? "Fund type" : "Industry"}</FieldLabel>
              <Select value={type} onValueChange={(value) => go({ type: value })}>
                <SelectTrigger aria-label={kind === "fund" ? "Fund type" : "Industry"} className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>All</SelectItem>
                  {(kind === "fund" ? FUND_TYPES : INDUSTRIES).map((item) => <SelectItem key={item} value={item}>{item}</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Field className="w-40">
              <FieldLabel>Order</FieldLabel>
              <Select value={sort} onValueChange={(value) => go({ sort: value === "largest" ? "largest" : "" })}>
                <SelectTrigger aria-label="Order" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="newest">Newest first</SelectItem>
                  <SelectItem value="largest">Largest raised first</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <div className="flex h-9 items-center gap-2">
              <Checkbox id="raise-new" checked={newOnly} onCheckedChange={(checked) => go({ new_only: checked === true ? "true" : "" })} />
              <Label htmlFor="raise-new" className="text-sm font-normal">New notices only</Label>
            </div>
            <Button type="submit"><Search /> Search</Button>
          </form>
      </div>
      {feed.error ? (
        <LoadError error={feed.error} retry={feed.refresh} />
      ) : !data ? (
        <Loading />
      ) : !data.items.length ? (
        <div className="mt-6"><NoData title="No filings match" description="Widen the date range or clear a filter." /></div>
      ) : (
        <div className="mt-6 grid gap-6">
          {leaders.length > 1 && offset === 0 && (
            <ChartCard
              title={`Largest raises · ${label}`}
              description={`Amount sold as reported, filed ${day(data.window.from)} to ${day(data.window.to)} - counted back from the newest filing SEC has published`}
              action={<AskAgent label="Ask about these" question={`Which ${label} raised the most in Form D filings${days !== ALL ? ` in the last ${days} days of filings` : ""}${params.get("state") ? ` in ${params.get("state")}` : ""}? Show the largest as a chart.`} />}
              explain={SOLD_METRIC}
            >
              <RankedBarChart format="usd" label="Amount sold"
                data={leaders.map((item) => ({ label: `${item.issuer_name}${item.is_amendment ? " (D/A)" : ""}`, value: item.total_sold ?? 0 }))} />
            </ChartCard>
          )}
          <Card className="gap-0 overflow-hidden py-0 shadow-none">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50">
                  <TableHead>Filed</TableHead>
                  <TableHead>{kind === "fund" ? "Fund" : "Company"}</TableHead>
                  <TableHead>{kind === "fund" ? "Fund type" : "Industry"}</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead className="text-right">Sold</TableHead>
                  <TableHead className="text-right">Offering</TableHead>
                  <TableHead className="text-right">Investors</TableHead>
                  <TableHead className="text-right">Minimum</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((item) => (
                  <TableRow key={item.accession_number}>
                    <TableCell className="text-muted-foreground">{day(item.filing_date)}</TableCell>
                    <TableCell className="min-w-56 max-w-80 whitespace-normal">
                      <Link className="font-medium hover:text-primary hover:underline" href={`/raises/${item.accession_number}`}>{item.issuer_name}</Link>
                      <div className="mt-0.5">
                        <Badge variant={item.is_amendment ? "neutral" : "positive"}>{item.is_amendment ? "Amendment" : "New notice"}</Badge>
                      </div>
                    </TableCell>
                    <TableCell>{(kind === "fund" ? item.fund_type : item.industry_group) ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground">{item.state ?? "—"}</TableCell>
                    <TableCell className="text-right font-medium tabular-nums">{usd(item.total_sold)}</TableCell>
                    <TableCell className="text-right tabular-nums">{item.offering_indefinite ? <span className="text-muted-foreground">Indefinite</span> : usd(item.total_offering)}</TableCell>
                    <TableCell className="text-right tabular-nums">{count(item.investor_count)}</TableCell>
                    <TableCell className="text-right tabular-nums">{usd(item.minimum_investment)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Showing {offset + 1}–{offset + data.items.length}{sort === "largest" ? " by amount sold" : ", newest first"}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => go({}, Math.max(0, offset - PAGE))}><ChevronLeft /> Previous</Button>
              <Button variant="outline" size="sm" disabled={data.next_offset === null} onClick={() => go({}, data.next_offset!)}>Next <ChevronRight /></Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
