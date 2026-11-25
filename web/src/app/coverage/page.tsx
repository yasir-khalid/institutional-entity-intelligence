"use client";

import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { LoadError, Loading, NoData } from "@/components/WorkspaceStates";
import { PageHeader } from "@/components/PageHeader";
import { MetricCard, MetricGrid } from "@/components/metrics";
import { useResource } from "@/hooks/use-resource";
import type { Coverage } from "@/lib/api";

const DECISIONS = [
  { key: "AUTO_MATCH", label: "Auto-matched", className: "bg-chart-1" },
  { key: "REVIEW", label: "Needs review", className: "bg-chart-2" },
  { key: "UNMATCHED", label: "Unmatched", className: "bg-chart-5" },
];

export default function CoveragePage() {
  const resource = useResource<Coverage>("/api/coverage");
  const doc = resource.data;
  return (
    <div className="workspace-page">
      <PageHeader
        eyebrow="Published data inventory"
        title="Data coverage"
        description="Measured at publish time — not inferred from source logos or live filesystem reads. Dates are latest observed source dates, not a guarantee of freshness."
        actions={
          <Button variant="outline" size="sm" onClick={resource.refresh}>
            <RefreshCw />
            Refresh
          </Button>
        }
      />
      {resource.error ? (
        <LoadError error={resource.error} retry={resource.refresh} />
      ) : !doc ? (
        <Loading />
      ) : !doc.generation ? (
        <NoData
          title="No published inventory yet"
          description={doc.warning || "Run make publish to create a source inventory alongside the serving indexes."}
        />
      ) : (
        <CoverageBody doc={doc} />
      )}
    </div>
  );
}

function CoverageBody({ doc }: { doc: Coverage }) {
  const imported = doc.sources.filter((source) => source.available).length;
  const published = doc.published_at ? new Date(doc.published_at).toLocaleString() : "—";
  const decisionTotal = DECISIONS.reduce((sum, item) => sum + (doc.decisions[item.key] ?? 0), 0);
  return (
    <>
      {doc.partial && (
        <Alert className="mb-6">
          <AlertTitle>Partial publication</AlertTitle>
          <AlertDescription>
            Only selected serving indexes were replaced. This is not a consistent full-generation snapshot. Run make
            publish without --only to publish the complete dataset.
          </AlertDescription>
        </Alert>
      )}

      <MetricGrid>
        <MetricCard
          metric={{
            label: "Sources imported",
            definition: "Sources whose build tables were present when this generation was published.",
            source: "Publication inventory",
            caveats: ["Presence describes build inputs, not complete entity coverage."],
          }}
          value={imported}
          unit={`of ${doc.sources.length}`}
        />
        <MetricCard
          metric={{
            label: "Entity documents",
            definition: "Canonical entities in the serving index, one per GLEIF LEI.",
            source: "er_entities serving index",
            asOf: published,
          }}
          value={(doc.indexes.entities?.count ?? 0).toLocaleString()}
        />
        <MetricCard
          metric={{
            label: "13F holding rows",
            definition: "Reportable long positions from accepted 13F information tables.",
            source: "er_13f_holdings serving index",
            asOf: published,
            caveats: ["Filings that fail reconciliation are quarantined, not counted."],
          }}
          value={(doc.indexes["13f_holdings"]?.count ?? 0).toLocaleString()}
        />
        <MetricCard
          metric={{
            label: "Crosswalk auto-matched",
            definition: "Source records resolved to a GLEIF LEI without a human review.",
            formula: "AUTO_MATCH ÷ all crosswalk decisions",
            source: "Crosswalk decisions",
            caveats: ["A close tie is held for review rather than matched; a low rate is deliberate."],
          }}
          value={decisionTotal ? `${(((doc.decisions.AUTO_MATCH ?? 0) / decisionTotal) * 100).toFixed(0)}%` : "—"}
          footnote={`${(doc.decisions.AUTO_MATCH ?? 0).toLocaleString()} of ${decisionTotal.toLocaleString()} records`}
        />
      </MetricGrid>

      <Card className="mt-6 gap-0 overflow-hidden py-0 shadow-none">
        <CardHeader className="gap-1 border-b px-5 py-4">
          <CardTitle className="text-sm font-medium">Sources</CardTitle>
          <CardDescription className="text-xs">
            Dates are the latest observation in each source. Expand a table to see its published schema.
          </CardDescription>
        </CardHeader>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-5">Source</TableHead>
              <TableHead>Latest observation</TableHead>
              <TableHead>Tables</TableHead>
              <TableHead className="pr-5 text-right">Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {doc.sources.map((source) => (
              <TableRow key={source.source} className="align-top">
                <TableCell className="max-w-[22rem] pl-5 whitespace-normal">
                  <div className="font-medium">{source.label}</div>
                  <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{source.caveat}</p>
                </TableCell>
                <TableCell className="tabular-nums">
                  {source.as_of ?? <span className="text-muted-foreground">Not recorded</span>}
                </TableCell>
                <TableCell className="whitespace-normal">
                  {source.tables.length === 0 && <span className="text-muted-foreground">—</span>}
                  {source.tables.map((table) => (
                    <details key={table.name} className="coverage-table">
                      <summary>
                        <code>{table.name}</code>
                        <span>{table.record_count.toLocaleString()} rows</span>
                      </summary>
                      <ul>
                        {table.schema.map((field) => (
                          <li key={field.name}>
                            <code>{field.name}</code>
                            <span>{field.type}</span>
                          </li>
                        ))}
                      </ul>
                    </details>
                  ))}
                </TableCell>
                <TableCell className="pr-5">
                  <div className="flex flex-col items-end gap-1">
                    <Badge variant={source.available ? "positive" : "outline"}>
                      {source.available ? "Imported" : "Not available"}
                    </Badge>
                    {source.quarantined > 0 && (
                      <Badge variant="caution">{source.quarantined.toLocaleString()} quarantined</Badge>
                    )}
                    {source.schema_changed && <Badge variant="outline">Schema changed</Badge>}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card className="gap-4 py-5 shadow-none">
          <CardHeader className="px-5">
            <CardTitle className="text-sm font-medium">Crosswalk outcomes</CardTitle>
            <CardDescription className="text-xs">How source records resolved to a GLEIF LEI</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 px-5">
            <div className="flex h-2 overflow-hidden rounded-full bg-muted">
              {DECISIONS.map((item) => (
                <span
                  key={item.key}
                  className={item.className}
                  style={{ width: `${decisionTotal ? ((doc.decisions[item.key] ?? 0) / decisionTotal) * 100 : 0}%` }}
                />
              ))}
            </div>
            <ul className="grid gap-2 text-sm">
              {DECISIONS.map((item) => (
                <li key={item.key} className="flex items-center gap-2">
                  <span className={`size-2.5 rounded-[3px] ${item.className}`} />
                  <span className="flex-1">{item.label}</span>
                  <span className="tabular-nums">{(doc.decisions[item.key] ?? 0).toLocaleString()}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card className="gap-4 py-5 shadow-none">
          <CardHeader className="px-5">
            <CardTitle className="text-sm font-medium">Publication</CardTitle>
            <CardDescription className="text-xs">
              Every index is staged and validated, then all aliases switch in one transaction.
            </CardDescription>
          </CardHeader>
          <CardContent className="px-5">
            <dl className="grid grid-cols-[9rem_minmax(0,1fr)] gap-x-4 gap-y-2 text-sm">
              <dt className="text-muted-foreground">Published</dt>
              <dd>{published}</dd>
              <dt className="text-muted-foreground">Generation</dt>
              <dd className="truncate font-mono text-xs leading-5" title={doc.generation ?? ""}>{doc.generation}</dd>
              <dt className="text-muted-foreground">Rollback target</dt>
              <dd className="truncate font-mono text-xs leading-5">{doc.previous_generation || "None retained"}</dd>
            </dl>
            <p className="mt-4 text-xs leading-relaxed text-muted-foreground">
              Restore with <code>uv run python -m er.cli.publish --rollback GENERATION</code>. Reviews and saved
              investigations are never replaced.
            </p>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
