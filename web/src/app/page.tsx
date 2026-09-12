"use client";

import { useCallback, useState } from "react";
import SearchBar from "@/components/SearchBar";
import ResultsList from "@/components/ResultsList";
import EntityTree from "@/components/EntityTree";
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
      // A single unambiguous result (or the first AUTO_MATCH) jumps straight to
      // the tree, matching how the CLI resolves a name before showing anything.
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

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-6 px-6 py-8">
      <header>
        <h1 className="text-2xl font-bold text-slate-900">Institutional Entity Intelligence</h1>
        <p className="text-sm text-slate-500">
          Search a name, LEI, or security ID (CUSIP) to explore the GLEIF relationship tree and SEC 13F activity.
        </p>
      </header>

      <SearchBar onSearch={handleSearch} loading={searching} />
      {searchError && <p className="text-sm text-red-600">{searchError}</p>}

      {results && results.length > 1 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Results - pick one to explore</h2>
          <ResultsList results={results} onSelect={loadTree} />
        </div>
      )}

      {rootEntityId && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[2fr_1fr]">
          <div>
            <h2 className="mb-2 text-sm font-semibold text-slate-700">
              Relationship tree (depth {TREE_DEPTH}) - click any node for details
            </h2>
            {treeLoading && <p className="text-sm text-slate-400">Loading tree...</p>}
            {treeError && <p className="text-sm text-red-600">{treeError}</p>}
            {treeData && <EntityTree data={treeData} onNodeClick={loadEntity} />}
          </div>
          <div className="rounded-lg border border-slate-200 bg-white">
            <DetailsPanel detail={detail} loading={detailLoading} error={detailError} />
          </div>
        </div>
      )}

      {selectedEntityId === null && !rootEntityId && (
        <p className="text-sm text-slate-400">No entity selected yet - search above to get started.</p>
      )}
    </div>
  );
}
