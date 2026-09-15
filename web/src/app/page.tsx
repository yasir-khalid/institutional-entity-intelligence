"use client";

import { useCallback, useState } from "react";
import { AlertCircle, Building2, Network, Waypoints } from "lucide-react";
import SearchBar from "@/components/SearchBar";
import ResultsList from "@/components/ResultsList";
import EntityTreeView from "@/components/EntityTreeView";
import DetailsPanel from "@/components/DetailsPanel";
import HowItWorks from "@/components/HowItWorks";
import WhyItMatters from "@/components/WhyItMatters";
import ScrollPane from "@/components/ScrollPane";
import { ResultsSkeleton, TreeSkeleton } from "@/components/Skeletons";
import { SectionLabel } from "@/components/ui";
import {
  search,
  getEntityTree,
  getEntityDetail,
  type SearchResult,
  type SearchType,
  type TreeNode,
  type EntityDetail,
} from "@/lib/api";

const TREE_DEPTH = 2;

function Wordmark({ size = "default" }: { size?: "default" | "hero" }) {
  const hero = size === "hero";
  return (
    <div className="flex items-center gap-2.5">
      <span
        className={`bg-ink flex items-center justify-center rounded-lg text-white ${
          hero ? "h-9 w-9" : "h-7 w-7"
        }`}
      >
        <Waypoints className={hero ? "h-[18px] w-[18px]" : "h-3.5 w-3.5"} strokeWidth={1.75} />
      </span>
      <span
        className={`text-ink font-semibold tracking-[-0.015em] ${hero ? "text-[19px]" : "text-[14px]"}`}
      >
        Institutional Entity Intelligence
      </span>
    </div>
  );
}

export default function Home() {
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  // Distinct from `results !== null`: flips true the moment a search fires and
  // never resets, so the page commits to the workspace layout even while the
  // first search is still in flight rather than snapping back to the landing.
  const [hasSearched, setHasSearched] = useState(false);

  const [rootEntityId, setRootEntityId] = useState<string | null>(null);
  const [treeData, setTreeData] = useState<TreeNode | null>(null);
  const [treeLoading, setTreeLoading] = useState(false);
  const [treeError, setTreeError] = useState<string | null>(null);

  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const loadEntity = useCallback(async (entityId: string) => {
    setSelectedEntityId(entityId);
    setDetailLoading(true);
    setDetailError(null);
    try {
      setDetail(await getEntityDetail(entityId));
    } catch (e) {
      setDetailError(e instanceof Error ? e.message : "Failed to load entity");
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const loadTree = useCallback(
    async (entityId: string) => {
      setRootEntityId(entityId);
      setTreeLoading(true);
      setTreeError(null);
      try {
        setTreeData(await getEntityTree(entityId, TREE_DEPTH));
      } catch (e) {
        setTreeError(e instanceof Error ? e.message : "Failed to load relationship tree");
        setTreeData(null);
      } finally {
        setTreeLoading(false);
      }
      await loadEntity(entityId);
    },
    [loadEntity],
  );

  async function handleSearch(query: string, searchType: SearchType) {
    setHasSearched(true);
    setSearching(true);
    setSearchError(null);
    setResults(null);
    try {
      const resp = await search(query, searchType);
      setResults(resp.results);
      setSearching(false);
      // A single unambiguous result (or a confident AUTO_MATCH) goes straight
      // to the tree - fired after `searching` clears so the results skeleton
      // and the tree skeleton never show at the same time.
      const autoMatch = resp.results.find((r) => r.decision === "AUTO_MATCH");
      if (resp.results.length === 1) void loadTree(resp.results[0].entity_id);
      else if (autoMatch) void loadTree(autoMatch.entity_id);
    } catch (e) {
      setSearchError(e instanceof Error ? e.message : "Search failed");
      setSearching(false);
    }
  }

  const showResultsPicker = results !== null && results.length > 1;
  // Until an entity is picked there is nothing to put in the tree or details
  // panes, so the results take the whole stage rather than sitting in a thin
  // strip above two empty cards.
  const workspaceActive = Boolean(rootEntityId || treeLoading);

  if (!hasSearched) {
    return (
      <div className="scroll-thin bg-surface flex min-h-screen flex-col overflow-y-auto">
        <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center gap-12 px-6 py-20">
          <div className="flex w-full flex-col items-center gap-7">
            <div className="animate-fade-in-up flex flex-col items-center gap-3 text-center">
              <Wordmark size="hero" />
              <p className="text-ink-muted max-w-md text-[13.5px] leading-relaxed">
                Resolve a fund or manager to its legal entity, then explore its ownership structure and SEC filing
                activity.
              </p>
            </div>

            <div className="animate-fade-in-up w-full" style={{ animationDelay: "100ms" }}>
              <SearchBar onSearch={handleSearch} loading={searching} size="hero" />
              {searchError && (
                <p className="mt-3 flex items-center justify-center gap-1.5 text-[12.5px] text-rose-600">
                  <AlertCircle className="h-3.5 w-3.5" strokeWidth={2} />
                  {searchError}
                </p>
              )}
            </div>
          </div>

          <div className="animate-fade-in-up w-full" style={{ animationDelay: "200ms" }}>
            <HowItWorks />
          </div>
        </div>

        {/* "How it works" answers what the product does; this answers why any
            of it is worth doing. Landing page only - once you're working, the
            data itself makes the argument. */}
        <WhyItMatters />
      </div>
    );
  }

  return (
    <div className="bg-canvas flex h-screen w-screen flex-col overflow-hidden">
      {/* Three equal-weight columns so the search bar is optically centred in
          the viewport regardless of how wide the wordmark renders. */}
      <header className="border-line bg-surface z-10 grid shrink-0 grid-cols-[1fr_auto_1fr] items-center gap-6 border-b px-5 py-3">
        <button
          type="button"
          onClick={() => setHasSearched(false)}
          className="justify-self-start outline-none transition-opacity hover:opacity-70"
          aria-label="Back to start"
        >
          <Wordmark />
        </button>
        <div className="w-[min(44rem,64vw)]">
          <SearchBar onSearch={handleSearch} loading={searching} />
        </div>
        <div aria-hidden />
      </header>

      {searchError && (
        <div className="flex shrink-0 items-center gap-1.5 border-b border-rose-100 bg-rose-50 px-5 py-2 text-[12.5px] text-rose-700">
          <AlertCircle className="h-3.5 w-3.5" strokeWidth={2} />
          {searchError}
        </div>
      )}

      {!workspaceActive && (searching || results !== null) && (
        <main className="scroll-thin bg-surface min-h-0 flex-1 overflow-y-auto px-5 pt-4 pb-6">
          <div className="mb-2.5">
            <SectionLabel>{searching ? "Searching" : `${results?.length ?? 0} results`}</SectionLabel>
          </div>
          {searching ? <ResultsSkeleton /> : results && <ResultsList results={results} onSelect={loadTree} />}
        </main>
      )}

      {workspaceActive && (searching || showResultsPicker) && (
        // Once the workspace is live the picker collapses to a strip. The
        // height cap is load-bearing, not cosmetic: an uncapped list (a brand
        // name can return 10+ legal entities) grows until it squeezes the
        // workspace below it to zero height, making the tree and details
        // invisible even though they rendered.
        <ScrollPane
          className="border-line bg-surface shrink-0 border-b"
          contentClassName="max-h-[13.5rem] px-5 pt-3.5 pb-5"
        >
          <div>
            <div className="mb-2.5">
              <SectionLabel>{searching ? "Searching" : `${results?.length ?? 0} results`}</SectionLabel>
            </div>
            {searching ? <ResultsSkeleton /> : results && <ResultsList results={results} onSelect={loadTree} />}
          </div>
        </ScrollPane>
      )}

      {/* Both panes are cards with an identical 44px titled header bar, so
          their frames, headers and content areas start on the same baseline. */}
      <main className={`min-h-0 flex-1 gap-4 p-4 ${workspaceActive ? "flex" : "hidden"}`}>
        <section className="border-line bg-surface flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl shadow-[0_1px_2px_rgba(15,23,42,0.04)] ring-1 ring-transparent">
          <div className="border-line-soft flex h-11 shrink-0 items-center justify-between gap-3 border-b px-4">
            <SectionLabel icon={<Network className="h-3 w-3" strokeWidth={2} />}>
              Relationship tree · depth {TREE_DEPTH}
            </SectionLabel>
            {rootEntityId && !treeLoading && (
              <div className="text-ink-subtle flex items-center gap-3.5 text-[11px]">
                <span className="flex items-center gap-1.5">
                  <span className="bg-upward h-1.5 w-1.5 rounded-full" />
                  Parent
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="bg-downward h-1.5 w-1.5 rounded-full" />
                  Subsidiary / fund
                </span>
              </div>
            )}
          </div>

          {treeError && (
            <p className="flex shrink-0 items-center gap-1.5 border-b border-rose-100 bg-rose-50 px-4 py-2 text-[12.5px] text-rose-700">
              <AlertCircle className="h-3.5 w-3.5" strokeWidth={2} />
              {treeError}
            </p>
          )}

          <div className="min-h-0 flex-1">
            {treeLoading ? (
              <TreeSkeleton />
            ) : treeData && rootEntityId ? (
              <EntityTreeView
                key={rootEntityId}
                data={treeData}
                selectedEntityId={selectedEntityId}
                onSelect={loadEntity}
              />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2.5">
                <span className="bg-canvas text-ink-subtle flex h-10 w-10 items-center justify-center rounded-xl">
                  <Network className="h-5 w-5" strokeWidth={1.5} />
                </span>
                <p className="text-ink-subtle text-[12.5px]">Select a result to load its relationship tree.</p>
              </div>
            )}
          </div>
        </section>

        <aside className="border-line bg-surface flex w-[clamp(25rem,30vw,34rem)] shrink-0 flex-col overflow-hidden rounded-xl shadow-[0_1px_2px_rgba(15,23,42,0.04)]">
          <div className="border-line-soft flex h-11 shrink-0 items-center border-b px-4">
            <SectionLabel icon={<Building2 className="h-3 w-3" strokeWidth={2} />}>Entity</SectionLabel>
          </div>
          <div className="min-h-0 flex-1">
            {/* treeLoading counts as loading here: loadTree fetches the tree
                and then immediately loads the root entity, so without this the
                panel flashes "select an entity" for the whole tree fetch. */}
            <DetailsPanel detail={detail} loading={detailLoading || treeLoading} error={detailError} />
          </div>
        </aside>
      </main>
    </div>
  );
}
