"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadError, Loading, NoData } from "@/components/WorkspaceStates";
import { PageHeader } from "@/components/PageHeader";
import { RankedBarChart } from "@/components/charts";
import { MetricInfo, type MetricDefinition } from "@/components/metrics";
import { useResource } from "@/hooks/use-resource";
import type { SecuritySummary } from "@/lib/api";
import { count, day } from "@/lib/format";

const HOLDERS_METRIC: MetricDefinition = {
  label: "13F filers holding",
  definition:
    "The number of institutional filers that reported a long position in the security on their latest Form 13F.",
  formula:
    "Distinct filer CIKs with a non-zero long position for the CUSIP in the latest period of report.",
  source: "SEC Form 13F information tables",
  field: "Information table rows, grouped by CIK",
  caveats: [
    "Form 13F only covers reportable US equity securities and managers above the filing threshold.",
    "A filer count is not an ownership percentage and can double-count the same beneficial owner.",
  ],
};

export default function SecurityDirectory({
  searchParams,
}: {
  searchParams: Record<string, string>;
}) {
  const router = useRouter();
  const params = new URLSearchParams(searchParams);
  const q = params.get("q") ?? "";
  const [query, setQuery] = useState(q);
  const resource = useResource<{ items: SecuritySummary[] }>(`/api/securities?limit=50${q ? `&q=${encodeURIComponent(q)}` : ""}`);
  function submit(event: FormEvent) {
    event.preventDefault();
    router.push(`/securities${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`);
  }
  const items = resource.data?.items ?? [];
  return (
    <div className="workspace-page wide">
      <PageHeader
        eyebrow="13F · FINRA · fails to deliver"
        title="Securities"
        description="Institutional ownership from 13F filings, daily short sale volume and fails-to-deliver, by CUSIP or ticker. Form 13F covers reportable US long equity positions only."
      />
      <div className="toolbar-surface mb-6">
          <form className="flex w-full flex-wrap items-end gap-3" onSubmit={submit}>
            <Field className="min-w-64 flex-1">
              <FieldLabel htmlFor="security-q">Ticker, CUSIP or issuer name</FieldLabel>
              <Input id="security-q" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. NVDA, 037833100, Nvidia" />
            </Field>
            <Button type="submit"><Search /> Search</Button>
          </form>
      </div>
      {resource.error ? (
        <LoadError error={resource.error} retry={resource.refresh} />
      ) : !resource.data ? (
        <Loading />
      ) : !items.length ? (
        <div className="mt-6"><NoData title="No securities match" description="Issuer names match whole words as reported on 13F, e.g. “NVIDIA CORPORATION”." /></div>
      ) : (
        <div className="mt-6 grid gap-6">
          {!q && (
            <Card className="gap-4 py-5 shadow-none">
              <CardHeader className="px-5">
                <CardTitle className="flex items-center gap-1.5 text-sm font-medium">Most widely held <MetricInfo metric={HOLDERS_METRIC} /></CardTitle>
                <CardDescription className="text-xs">13F filers reporting a long position, latest quarter</CardDescription>
              </CardHeader>
              <CardContent className="px-3 sm:px-5">
                <RankedBarChart label="Filers"
                  data={items.slice(0, 10).map((item) => ({ label: `${item.issuer_name}${item.tickers[0] ? ` (${item.tickers[0]})` : ""}`, value: item.holder_count }))} />
              </CardContent>
            </Card>
          )}
          <Card className="gap-0 overflow-hidden py-0 shadow-none">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50">
                  <TableHead className="pl-5">Issuer</TableHead><TableHead>Class</TableHead><TableHead>Ticker</TableHead>
                  <TableHead>CUSIP</TableHead><TableHead className="text-right">13F holders</TableHead><TableHead className="pr-5">Period</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.cusip}>
                    <TableCell className="pl-5 whitespace-normal"><Link className="font-medium hover:text-primary hover:underline" href={`/securities/${item.cusip}`}>{item.issuer_name}</Link></TableCell>
                    <TableCell className="text-muted-foreground">{item.title_of_class ?? "—"}</TableCell>
                    <TableCell><div className="flex gap-1">{item.tickers.length ? item.tickers.map((ticker) => <Badge key={ticker} variant="accent">{ticker}</Badge>) : "—"}</div></TableCell>
                    <TableCell className="text-muted-foreground tabular-nums">{item.cusip}</TableCell>
                    <TableCell className="text-right font-medium tabular-nums">{count(item.holder_count)}</TableCell>
                    <TableCell className="pr-5 text-muted-foreground">{day(item.latest_period)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        </div>
      )}
    </div>
  );
}
