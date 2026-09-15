"use client";

import { useState, type FormEvent } from "react";
import { Search, Loader2 } from "lucide-react";
import type { SearchType } from "@/lib/api";

const TOGGLES: { value: SearchType; label: string; placeholder: string }[] = [
  { value: "name", label: "Name", placeholder: "Search by entity name, e.g. Point72" },
  { value: "lei", label: "LEI", placeholder: "Enter a 20-character LEI" },
  { value: "cusip", label: "Security ID", placeholder: "Enter a 9-character CUSIP" },
];

export default function SearchBar({
  onSearch,
  loading,
  size = "default",
}: {
  onSearch: (query: string, searchType: SearchType) => void;
  loading: boolean;
  /** "hero" is the landing page's larger, more prominent treatment; "default"
   * is the compact one docked in the app header after a search. */
  size?: "default" | "hero";
}) {
  const [query, setQuery] = useState("");
  const [searchType, setSearchType] = useState<SearchType>("name");
  const active = TOGGLES.find((t) => t.value === searchType)!;
  const hero = size === "hero";

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (query.trim()) onSearch(query.trim(), searchType);
  }

  const field = (
      <div
        className={`group flex w-full min-w-0 items-center rounded-xl border border-slate-200 bg-white shadow-sm transition-all focus-within:border-indigo-400 focus-within:ring-4 focus-within:ring-indigo-50 ${
          hero ? "h-13 pl-4 pr-1.5" : "h-10 pl-3 pr-1"
        }`}
      >
        <Search className={`shrink-0 text-slate-400 ${hero ? "h-[18px] w-[18px]" : "h-4 w-4"}`} strokeWidth={2} />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={active.placeholder}
          aria-label={`Search by ${active.label}`}
          className={`min-w-0 flex-1 bg-transparent px-3 text-slate-900 outline-none placeholder:text-slate-400 ${
            hero ? "text-[15px]" : "text-[13px]"
          } ${searchType === "name" ? "" : "font-mono tracking-tight"}`}
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-indigo-600 font-medium text-white transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 ${
            hero ? "h-10 px-4 text-[13px]" : "h-8 px-3 text-[12px]"
          }`}
        >
          {loading && <Loader2 className="h-3.5 w-3.5 animate-spin" strokeWidth={2.5} />}
          {loading ? "Searching" : "Search"}
        </button>
      </div>
  );

  // Segmented control - one connected surface rather than three loose pills,
  // so it reads as a single "what kind of query is this" choice. Its outer
  // height matches the field exactly at both sizes, so the two sit on one
  // shared baseline when laid out side by side in the app header.
  const modes = (
    <div
      role="tablist"
      aria-label="Search type"
      className={`inline-flex shrink-0 items-center rounded-xl bg-slate-100 ${hero ? "h-9 p-1" : "h-10 p-1"}`}
    >
      {TOGGLES.map((t) => {
        const selected = searchType === t.value;
        return (
          <button
            key={t.value}
            type="button"
            role="tab"
            aria-selected={selected}
            onClick={() => setSearchType(t.value)}
            className={`flex h-full items-center rounded-lg px-3 text-[12px] font-medium transition-all ${
              selected ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-700"
            }`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );

  // Landing page stacks (field first, modes centred beneath); the app header
  // lays them out on a single row so the chrome stays one bar tall.
  return hero ? (
    <form onSubmit={handleSubmit} className="flex w-full flex-col items-center gap-3">
      {field}
      {modes}
    </form>
  ) : (
    <form onSubmit={handleSubmit} className="flex w-full items-center gap-2">
      {modes}
      {field}
    </form>
  );
}
