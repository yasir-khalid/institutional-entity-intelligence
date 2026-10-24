"use client";

import { useState, type FormEvent } from "react";
import { useDefaultLayout } from "react-resizable-panels";
import Link from "next/link";
import { useSearchParams, useRouter } from "next/navigation";
import { ExternalLink, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Field, FieldLabel } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";
import EntityProfile from "@/components/EntityProfile";
import { useResource } from "@/hooks/use-resource";
import { useIsMobile } from "@/hooks/use-mobile";
import { Loading, LoadError, NoData } from "@/components/WorkspaceStates";
import type { EntityDetail, SearchResponse, SearchType } from "@/lib/api";

const panelIds = ["results", "inspector"];
const layoutStorage = {
  getItem(key: string) {
    try {
      return typeof window === "undefined" ? null : localStorage.getItem(key);
    } catch {
      return null;
    }
  },
  setItem(key: string, value: string) {
    try {
      localStorage.setItem(key, value);
    } catch {
      /* Optional preference storage. */
    }
  },
};

export default function EntityWorkspace() {
  const params = useSearchParams();
  const query = params.get("q") || "";
  const type = (
    ["name", "lei", "cusip"].includes(params.get("type") || "")
      ? params.get("type")
      : "name"
  ) as SearchType;
  const router = useRouter();
  const [selected, setSelected] = useState<{ query: string; id: string }>();
  const mobile = useIsMobile();
  const layout = useDefaultLayout({
    id: "er:entity-search:v1",
    panelIds,
    storage: layoutStorage,
    onlySaveAfterUserInteractions: true,
  });
  const searchParams = new URLSearchParams({ query, search_type: type });
  if (params.get("country"))
    searchParams.set("country", params.get("country")!);
  const results = useResource<SearchResponse>(
    query ? `/api/search?${searchParams}` : null,
  );
  const entityId =
    selected?.query === searchParams.toString()
      ? selected.id
      : results.data?.results[0]?.entity_id;
  const profile = useResource<EntityDetail>(
    entityId ? `/api/entity/${encodeURIComponent(entityId)}` : null,
  );
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = new URLSearchParams({
      q: String(form.get("query")).trim(),
      type: String(form.get("type")),
    });
    const country = String(form.get("country")).trim().toUpperCase();
    if (country) next.set("country", country);
    router.push(`/entities?${next}`);
  }
  const list = (
    <div className="search-list-pane p-1">
      <div className="workspace-section-heading">
        <h2>Results</h2>
        <span>{results.data?.results.length ?? 0} candidates</span>
      </div>
      <p className="workspace-note">
        Retrieval ranks candidates; a close tie remains a review, not a
        confident match.
      </p>
      {results.error ? (
        <LoadError error={results.error} retry={results.refresh} />
      ) : !results.data ? (
        <Loading />
      ) : results.data.results.length === 0 ? (
        <NoData
          title="No matching entities"
          description="Try a legal name, LEI or CUSIP. Country is a soft hint, not an exclusion."
        />
      ) : (
        <div className="workspace-table-scroll">
          <Table className="workspace-table">
            <TableCaption className="sr-only">
              Entity candidates. Select a name to inspect its profile.
            </TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Entity</TableHead>
                <TableHead>Country</TableHead>
                <TableHead>Decision</TableHead>
                <TableHead>Score</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {results.data.results.map((result) => (
                <TableRow
                  key={result.entity_id}
                  data-selected={result.entity_id === entityId}
                >
                  <TableCell>
                    <button
                      onClick={() =>
                        setSelected({
                          query: searchParams.toString(),
                          id: result.entity_id,
                        })
                      }
                      className="workspace-row-button"
                    >
                      {result.canonical_name}
                      <small>{result.entity_id}</small>
                    </button>
                  </TableCell>
                  <TableCell>{result.jurisdiction || result.legal_country || "—"}</TableCell>
                  <TableCell>
                    {result.decision?.replace(/_/g, " ") ||
                      result.matched_via.toUpperCase()}
                  </TableCell>
                  <TableCell>{result.score?.toFixed(1) ?? "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
  const inspector = (
    <div className="search-detail-pane p-1">
      {entityId && (
        <Link
          className="workspace-text-link"
          href={`/entities/${encodeURIComponent(entityId)}`}
        >
          <ExternalLink size={14} /> Open shareable entity profile
        </Link>
      )}
      {profile.error ? (
        <LoadError error={profile.error} retry={profile.refresh} />
      ) : (
        <EntityProfile
          key={entityId}
          detail={profile.data ?? null}
          loading={Boolean(entityId && !profile.data)}
          onOpenEntity={(id) =>
            router.push(`/entities/${encodeURIComponent(id)}`)
          }
        />
      )}
    </div>
  );
  return (
    <div className="workspace-page wide">
      <div className="workspace-heading compact">
        <p>Entity resolution</p>
        <h1>Search the registers</h1>
        <span>
          One deterministic matcher across every source. Inspect the evidence
          behind each link.
        </span>
      </div>
      <form
        key={params.toString()}
        className="entity-search-form"
        onSubmit={submit}
      >
        <Field>
          <FieldLabel htmlFor="entity-query">Name or identifier</FieldLabel>
          <Input
            id="entity-query"
            name="query"
            defaultValue={query}
            required
            maxLength={500}
            placeholder="Point72, an LEI, or a CUSIP"
          />
        </Field>
        <Field>
          <FieldLabel htmlFor="search-type">Search by</FieldLabel>
          <Select name="type" defaultValue={type}>
            <SelectTrigger id="search-type" className="w-full">
              <SelectValue placeholder="Search by" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="name">Legal name</SelectItem>
              <SelectItem value="lei">LEI</SelectItem>
              <SelectItem value="cusip">CUSIP</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field>
          <FieldLabel htmlFor="country">Country hint</FieldLabel>
          <Input
            id="country"
            name="country"
            defaultValue={params.get("country") || ""}
            maxLength={2}
            placeholder="e.g. GB"
            pattern="[A-Za-z]{2}"
          />
        </Field>
        <Button type="submit">
          <Search />
          Search
        </Button>
      </form>
      {query ? (
        mobile ? (
          <div className="grid gap-6">
            {list}
            {inspector}
          </div>
        ) : (
          <ResizablePanelGroup
            orientation="horizontal"
            className="entity-panels"
            id="entity-search-panels"
            defaultLayout={layout.defaultLayout}
            onLayoutChanged={layout.onLayoutChanged}
          >
            <ResizablePanel id="results" defaultSize="55%" minSize="30%">
              {list}
            </ResizablePanel>
            <ResizableHandle
              withHandle
              aria-label="Resize results and entity inspector"
            />
            <ResizablePanel id="inspector" defaultSize="45%" minSize="25%">
              {inspector}
            </ResizablePanel>
          </ResizablePanelGroup>
        )
      ) : (
        <NoData
          title="Start with an institution"
          description="Search by name, or use a known identifier for an exact lookup."
        />
      )}
    </div>
  );
}
