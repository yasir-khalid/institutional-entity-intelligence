"use client";

import { useState, type FormEvent } from "react";
import type { SearchType } from "@/lib/api";

const TOGGLES: { value: SearchType; label: string }[] = [
  { value: "name", label: "Name" },
  { value: "lei", label: "LEI" },
  { value: "cusip", label: "Security ID (CUSIP)" },
];

export default function SearchBar({
  onSearch,
  loading,
}: {
  onSearch: (query: string, searchType: SearchType) => void;
  loading: boolean;
}) {
  const [query, setQuery] = useState("");
  const [searchType, setSearchType] = useState<SearchType>("name");

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (query.trim()) onSearch(query.trim(), searchType);
  }

  return (
    <form onSubmit={handleSubmit} className="flex w-full flex-col gap-3">
      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={
            searchType === "name"
              ? "Search by entity name, e.g. Point72"
              : searchType === "lei"
                ? "Enter a 20-character LEI"
                : "Enter a 9-character CUSIP"
          }
          className="flex-1 rounded-lg border border-slate-300 px-4 py-2.5 text-sm outline-none focus:border-blue-500"
        />
        <button
          type="submit"
          disabled={loading || !query.trim()}
          className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-40"
        >
          {loading ? "Searching..." : "Search"}
        </button>
      </div>
      <div className="flex gap-1">
        {TOGGLES.map((t) => (
          <button
            key={t.value}
            type="button"
            onClick={() => setSearchType(t.value)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              searchType === t.value ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
    </form>
  );
}
