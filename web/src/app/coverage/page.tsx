"use client";

import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { LoadError, Loading, NoData } from "@/components/WorkspaceStates";
import { useResource } from "@/hooks/use-resource";
import type { Coverage } from "@/lib/api";

export default function CoveragePage() {
  const resource = useResource<Coverage>("/api/coverage");
  const doc = resource.data;
  return (
    <div className="workspace-page">
      <div className="workspace-heading compact">
        <p>Published data inventory</p>
        <h1>Data coverage</h1>
        <span>
          Measured at publish time—not inferred from source logos or live
          filesystem reads.
        </span>
      </div>
      <Button variant="outline" size="sm" onClick={resource.refresh}>
        <RefreshCw />
        Refresh inventory
      </Button>
      {resource.error ? (
        <LoadError error={resource.error} retry={resource.refresh} />
      ) : !doc ? (
        <Loading />
      ) : !doc.generation ? (
        <NoData
          title="No published inventory yet"
          description={
            doc.warning ||
            "Run make publish to create a source inventory alongside the serving indexes."
          }
        />
      ) : (
        <>
          {doc.partial && (
            <Alert className="mt-6">
              <AlertTitle>Partial publication</AlertTitle>
              <AlertDescription>
                Only selected serving indexes were replaced. This is not a
                consistent full-generation snapshot. Run make publish without
                --only to publish the complete dataset.
              </AlertDescription>
            </Alert>
          )}
          <section className="workspace-section">
            <h2>Serving generation</h2>
            <dl className="coverage-generation">
              <dt>Generation</dt>
              <dd>{doc.generation}</dd>
              <dt>Published</dt>
              <dd>
                {doc.published_at
                  ? new Date(doc.published_at).toLocaleString()
                  : "—"}
              </dd>
              <dt>Previous retained generation</dt>
              <dd>{doc.previous_generation || "None recorded"}</dd>
            </dl>
            <p className="workspace-note">
              Full publications stage and validate every index, then switch
              their aliases in one transaction. Retained complete generations
              can be restored with{" "}
              <code>uv run python -m er.cli.publish --rollback GENERATION</code>
              . Reviews and investigations are not replaced.
            </p>
            <div className="coverage-counts">
              {Object.entries(doc.indexes)
                .filter(([name]) => name !== "coverage")
                .map(([name, entry]) => (
                  <div key={name}>
                    <small>{name.replace(/_/g, " ")}</small>
                    <strong>{entry.count.toLocaleString()}</strong>
                  </div>
                ))}
            </div>
          </section>
          <section className="workspace-section">
            <h2>Imported source tables</h2>
            <p className="workspace-note">
              Table presence describes build inputs, not complete entity
              coverage. Dates are latest observed source dates, not a guarantee
              of freshness. Missing dates and sources remain explicit.
            </p>
            <div className="coverage-sources">
              {doc.sources.map((source) => (
                <article key={source.source}>
                  <header>
                    <h3>{source.label}</h3>
                    <Badge variant={source.available ? "secondary" : "outline"}>
                      {source.available ? "Imported" : "Not available"}
                    </Badge>
                  </header>
                  <p>{source.caveat}</p>
                  <div className="workspace-actions">
                    <small>
                      Latest observation: {source.as_of || "Not recorded"}
                    </small>
                    {source.quarantined > 0 && (
                      <Badge variant="destructive">
                        {source.quarantined.toLocaleString()} quarantined
                        filings
                      </Badge>
                    )}
                    {source.schema_changed && (
                      <Badge variant="outline">
                        Schema changed since previous generation
                      </Badge>
                    )}
                  </div>
                  {source.tables.map((table) => (
                    <details key={table.name}>
                      <summary>
                        {table.name} · {table.record_count.toLocaleString()}{" "}
                        rows · {table.as_of || "Date not recorded"}
                      </summary>
                      <div className="workspace-table-scroll">
                        <table className="workspace-table">
                          <caption className="sr-only">
                            {table.name} published input schema
                          </caption>
                          <thead>
                            <tr>
                              <th>Column</th>
                              <th>Type</th>
                            </tr>
                          </thead>
                          <tbody>
                            {table.schema.map((field) => (
                              <tr key={field.name}>
                                <td>{field.name}</td>
                                <td>{field.type}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </details>
                  ))}
                </article>
              ))}
            </div>
          </section>
          <section className="workspace-section">
            <h2>Crosswalk outcomes</h2>
            <div className="coverage-counts">
              {Object.entries(doc.decisions).map(([decision, count]) => (
                <div key={decision}>
                  <small>{decision.replace(/_/g, " ")}</small>
                  <strong>{count.toLocaleString()}</strong>
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
