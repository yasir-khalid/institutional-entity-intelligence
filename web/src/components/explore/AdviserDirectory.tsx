"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadError, Loading, NoData } from "@/components/WorkspaceStates";
import { PageHeader } from "@/components/PageHeader";
import { RankedBarChart } from "@/components/charts";
import { MetricInfo, type MetricDefinition } from "@/components/metrics";
import { useResource } from "@/hooks/use-resource";
import type { AdviserSummary } from "@/lib/api";
import { count, day, usd } from "@/lib/format";

const FUND_TYPES = ["Hedge fund", "Private equity", "Venture capital", "Real estate", "Securitized asset", "Liquidity", "Other private fund"];
const ALL = "all";
const PAGE = 50;

const RAUM_METRIC: MetricDefinition = {
  label: "Regulatory AUM",
  definition:
    "The gross value of assets each adviser reports managing on its latest Form ADV Part 1A.",
  formula:
    "Item 5.F(2)(c): total regulatory assets under management across all client types, before deducting leverage, uncalled commitments or non-fee-paying assets.",
  source: "SEC Form ADV Part 1A, monthly investment adviser extracts",
  field: "Item 5.F(2)(c)",
  caveats: [
    "Regulatory AUM is gross, so it is not directly comparable to the AUM a manager quotes clients.",
    "Each row uses the adviser's latest ingested snapshot; different advisers can be on different filing dates.",
  ],
};

export default function AdviserDirectory({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const router = useRouter();
  const params = new URLSearchParams(searchParams);
  const [query, setQuery] = useState(params.get("q") ?? "");
  const [state, setState] = useState(params.get("state") ?? "");
  const firmType = params.get("firm_type") ?? ALL;
  const fundType = params.get("fund_type") ?? ALL;
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const search = new URLSearchParams();
  for (const key of ["q", "state", "firm_type", "fund_type"]) if (params.get(key)) search.set(key, params.get(key)!);
  const resource = useResource<{ items: AdviserSummary[]; next_offset: number | null }>(
    `/api/advisers?${search.toString()}&offset=${offset}&limit=${PAGE}`,
  );
  function go(changes: Record<string, string>, page = 0) {
    const next = new URLSearchParams(search);
    for (const [key, value] of Object.entries(changes)) {
      if (value && value !== ALL) next.set(key, value);
      else next.delete(key);
    }
    if (page) next.set("offset", String(page));
    router.push(`/advisers?${next.toString()}`);
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    go({ q: query.trim(), state: state.trim().toUpperCase() });
  }
  const items = resource.data?.items ?? [];
  return (
    <div className="workspace-page wide">
      <PageHeader
        eyebrow="Form ADV · Part 1A"
        title="Investment advisers"
        description="Every SEC-registered and exempt reporting adviser, ranked by the regulatory AUM on its latest filing. Regulatory AUM is gross: it counts leverage and uncalled commitments."
      />
      <div className="toolbar-surface mb-6">
          <form className="flex w-full flex-wrap items-end gap-3" onSubmit={submit}>
            <Field className="min-w-60 flex-1">
              <FieldLabel htmlFor="adviser-q">Firm name</FieldLabel>
              <Input id="adviser-q" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. AQR Capital" />
            </Field>
            <Field className="w-24">
              <FieldLabel htmlFor="adviser-state">State</FieldLabel>
              <Input id="adviser-state" value={state} onChange={(event) => setState(event.target.value)} maxLength={2} placeholder="NY" />
            </Field>
            <Field className="w-44">
              <FieldLabel>Registration</FieldLabel>
              <Select value={firmType} onValueChange={(value) => go({ firm_type: value })}>
                <SelectTrigger aria-label="Registration" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>All advisers</SelectItem>
                  <SelectItem value="Registered">SEC registered</SelectItem>
                  <SelectItem value="ERA">Exempt reporting</SelectItem>
                </SelectContent>
              </Select>
            </Field>
            <Field className="w-52">
              <FieldLabel>Advises</FieldLabel>
              <Select value={fundType} onValueChange={(value) => go({ fund_type: value })}>
                <SelectTrigger aria-label="Advises" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={ALL}>Any fund type</SelectItem>
                  {FUND_TYPES.map((type) => <SelectItem key={type} value={type}>{type} funds</SelectItem>)}
                </SelectContent>
              </Select>
            </Field>
            <Button type="submit"><Search /> Search</Button>
          </form>
      </div>
      {resource.error ? (
        <LoadError error={resource.error} retry={resource.refresh} />
      ) : !resource.data ? (
        <Loading />
      ) : !items.length ? (
        <div className="mt-6"><NoData title="No advisers match" description="Firm names match on whole words; try fewer words or clear a filter." /></div>
      ) : (
        <div className="mt-6 grid gap-6">
          {offset === 0 && (
            <Card className="gap-4 py-5 shadow-none">
              <CardHeader className="px-5">
                <CardTitle className="flex items-center gap-1.5 text-sm font-medium">Largest by regulatory AUM <MetricInfo metric={RAUM_METRIC} /></CardTitle>
                <CardDescription className="text-xs">Top {Math.min(10, items.length)} of this view, latest Form ADV filing each</CardDescription>
              </CardHeader>
              <CardContent className="px-3 sm:px-5">
                <RankedBarChart format="usd" label="Regulatory AUM"
                  data={items.slice(0, 10).map((firm) => ({ label: firm.business_name, value: firm.raum ?? 0 }))} />
              </CardContent>
            </Card>
          )}
          <Card className="gap-0 overflow-hidden py-0 shadow-none">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50">
                  <TableHead className="w-12 text-right">#</TableHead>
                  <TableHead>Firm</TableHead>
                  <TableHead>Location</TableHead>
                  <TableHead className="text-right">Regulatory AUM</TableHead>
                  <TableHead className="text-right">Accounts</TableHead>
                  <TableHead className="text-right">Employees</TableHead>
                  <TableHead className="text-right">Private funds</TableHead>
                  <TableHead>Advises</TableHead>
                  <TableHead>As of</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((firm, index) => (
                  <TableRow key={firm.crd_number}>
                    <TableCell className="text-right text-muted-foreground tabular-nums">{offset + index + 1}</TableCell>
                    <TableCell className="min-w-56 max-w-72 whitespace-normal">
                      <Link className="font-medium hover:text-primary hover:underline" href={`/advisers/${firm.crd_number}`}>
                        {firm.business_name}
                      </Link>
                      <div className="text-xs text-muted-foreground">
                        CRD {firm.crd_number}
                        {firm.firm_type === "ERA" && <Badge variant="neutral" className="ml-2">Exempt reporting</Badge>}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{[firm.city, firm.state].filter(Boolean).join(", ") || firm.country || "—"}</TableCell>
                    <TableCell className="text-right font-medium tabular-nums">{usd(firm.raum)}</TableCell>
                    <TableCell className="text-right tabular-nums">{count(firm.accounts)}</TableCell>
                    <TableCell className="text-right tabular-nums">{count(firm.employees)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {count(firm.private_fund_count)}
                      {firm.private_fund_gross_assets ? <div className="text-xs text-muted-foreground">{usd(firm.private_fund_gross_assets)} gross</div> : null}
                    </TableCell>
                    <TableCell className="whitespace-normal">
                      <div className="flex flex-wrap gap-1" title={firm.fund_types.join(", ")}>
                        {firm.fund_types.slice(0, 2).map((type) => <Badge key={type} variant="accent">{type}</Badge>)}
                        {firm.fund_types.length > 2 && <Badge variant="neutral">+{firm.fund_types.length - 2}</Badge>}
                        {!firm.fund_types.length && <span className="text-muted-foreground">—</span>}
                      </div>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{day(firm.snapshot_date)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Showing {offset + 1}–{offset + items.length}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => go({}, Math.max(0, offset - PAGE))}>
                <ChevronLeft /> Previous
              </Button>
              <Button variant="outline" size="sm" disabled={resource.data.next_offset === null} onClick={() => go({}, resource.data!.next_offset!)}>
                Next <ChevronRight />
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
