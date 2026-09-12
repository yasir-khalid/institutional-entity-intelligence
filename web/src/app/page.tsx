"use client";

import { useCallback, useState } from "react";
import SearchBar from "@/components/SearchBar";
import ResultsList from "@/components/ResultsList";
import TreeExplorer from "@/components/TreeExplorer";
import DetailsPanel from "@/components/DetailsPanel";
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
    setSearching(true);
    setSearchError(null);
    setResults(null);
    try {
      const resp = await search(query, searchType);
      setResults(resp.results);
      const autoMatch = resp.results.find((r) => r.decision === "AUTO_MATCH");
      if (resp.results.length === 1) {
        await loadTree(resp.results[0].entity_id);
      } else if (autoMatch) {
        await loadTree(autoMatch.entity_id);
      }
    } catch (e) {
      setSearchError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  const showResultsPicker = results && results.length > 1;

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-white">
      <header className="shrink-0 border-b border-slate-200 px-6 py-4">
        <h1 className="text-xl font-bold text-slate-900">Institutional Entity Intelligence</h1>
        <p className="mb-3 text-xs text-slate-500">
          Search a name, LEI, or security ID (CUSIP) to explore the GLEIF relationship tree and SEC 13F activity.
        </p>
        <SearchBar onSearch={handleSearch} loading={searching} />
        {searchError && <p className="mt-2 text-sm text-red-600">{searchError}</p>}
      </header>

      {showResultsPicker && (
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
                Relationship tree (depth {TREE_DEPTH}) - click any entity for details. The searched entity is
                marked <span className="rounded bg-blue-600 px-1 py-0.5 text-[10px] font-semibold text-white">QUERY</span>;
                the selected one is highlighted.
              </h2>
              {treeLoading && <p className="text-sm text-slate-400">Loading tree...</p>}
              {treeError && <p className="text-sm text-red-600">{treeError}</p>}
              {treeData && (
                <div className="min-h-0 flex-1">
                  <TreeExplorer data={treeData} selectedEntityId={selectedEntityId} onSelect={loadEntity} />
                </div>
              )}
            </>
          ) : (
            <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-slate-200 text-sm text-slate-400">
              Search above to get started.
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
