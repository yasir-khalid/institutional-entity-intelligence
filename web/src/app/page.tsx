"use client";

import { useCallback, useState } from "react";
import SearchBar from "@/components/SearchBar";
import ResultsList from "@/components/ResultsList";
import EntityTreeView from "@/components/EntityTreeView";
import DetailsPanel from "@/components/DetailsPanel";
import HowItWorks from "@/components/HowItWorks";
import { ResultsSkeleton, TreeSkeleton } from "@/components/Skeletons";
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

export default function Home() {
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [results, setResults] = useState<SearchResult[] | null>(null);
  // Distinct from `results !== null`: this flips to true the moment a search
  // is fired and never resets, so the page commits to the results/tree
  // layout even while the very first search is still in flight (showing its
  // skeleton) rather than snapping back to the landing page in between.
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
      const d = await getEntityDetail(entityId);
      setDetail(d);
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
        const tree = await getEntityTree(entityId, TREE_DEPTH);
        setTreeData(tree);
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
      // A single unambiguous result (or a confident AUTO_MATCH) jumps
      // straight to the tree - fired after `searching` clears so the
      // results skeleton and the tree skeleton never both show at once.
      const autoMatch = resp.results.find((r) => r.decision === "AUTO_MATCH");
      if (resp.results.length === 1) {
        void loadTree(resp.results[0].entity_id);
      } else if (autoMatch) {
        void loadTree(autoMatch.entity_id);
      }
    } catch (e) {
      setSearchError(e instanceof Error ? e.message : "Search failed");
      setSearching(false);
    }
  }

  const showResultsPicker = results && results.length > 1;

  if (!hasSearched) {
    // Search-first landing page, like a search engine homepage - no
    // results/tree/details chrome until the user has actually searched for
    // something. min-h-screen + overflow-y-auto (rather than a fixed
    // h-screen) so the "How it works" section never gets clipped on a
    // shorter viewport - it scrolls instead of being cut off.
    return (
      <div className="flex min-h-screen w-screen flex-col items-center gap-10 overflow-y-auto bg-white px-6 py-16">
        <div className="flex w-full max-w-xl flex-col items-center gap-6">
          <div className="animate-fade-in-up text-center">
            <h1 className="text-3xl font-bold text-slate-900">Institutional Entity Intelligence</h1>
            <p className="mt-2 text-sm text-slate-500">
              Search a name, LEI, or security ID (CUSIP) to explore the GLEIF relationship tree and SEC 13F
              activity.
            </p>
          </div>
          <div className="animate-fade-in-up w-full" style={{ animationDelay: "120ms" }}>
            <SearchBar onSearch={handleSearch} loading={searching} />
            {searchError && <p className="mt-2 text-sm text-red-600">{searchError}</p>}
          </div>
        </div>

        <div className="animate-fade-in-up" style={{ animationDelay: "240ms" }}>
          <HowItWorks />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-white">
      <header className="shrink-0 border-b border-slate-200 px-6 py-3">
        <div className="mx-auto flex max-w-2xl flex-col gap-1">
          <SearchBar onSearch={handleSearch} loading={searching} />
          {searchError && <p className="text-sm text-red-600">{searchError}</p>}
        </div>
      </header>

      {searching && (
        <div className="max-h-56 shrink-0 overflow-y-auto border-b border-slate-200 px-6 py-3">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Searching...</h2>
          <ResultsSkeleton />
        </div>
      )}

      {!searching && showResultsPicker && (
        // max-h + overflow-y-auto is load-bearing, not cosmetic: without a
        // cap, a result set with many rows (e.g. a brand name like "Point72"
        // returning 10+ legal entities) grows unbounded and can squeeze the
        // flex-1 tree/details area below it down to zero height on a normal
        // laptop screen - clicks would still fire and fetch data (network
        // tab shows it), but the newly-rendered tree/details section would
        // be invisible at 0px tall. Confirmed live: this was exactly that bug.
        <div className="max-h-56 shrink-0 overflow-y-auto border-b border-slate-200 px-6 py-3">
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Results - pick one to explore</h2>
          <ResultsList results={results} onSelect={loadTree} />
        </div>
      )}

      <main className="flex min-h-0 flex-1 gap-4 p-4">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {rootEntityId ? (
            <>
              <h2 className="mb-2 shrink-0 text-sm font-semibold text-slate-700">
                Relationship tree (depth {TREE_DEPTH}) - click a card for details, use the ▾/▸ toggle to
                expand or collapse a branch.
              </h2>
              {treeError && <p className="text-sm text-red-600">{treeError}</p>}
              {treeLoading ? (
                <TreeSkeleton />
              ) : (
                treeData && (
                  <div className="min-h-0 flex-1">
                    <EntityTreeView
                      key={rootEntityId}
                      data={treeData}
                      selectedEntityId={selectedEntityId}
                      onSelect={loadEntity}
                    />
                  </div>
                )
              )}
            </>
          ) : (
            <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-slate-200 text-sm text-slate-400">
              Pick a result above to explore its relationship tree.
            </div>
          )}
        </div>

        <aside className="w-[380px] shrink-0 overflow-y-auto rounded-lg border border-slate-200">
          <DetailsPanel detail={detail} loading={detailLoading} error={detailError} />
        </aside>
      </main>
    </div>
  );
}
