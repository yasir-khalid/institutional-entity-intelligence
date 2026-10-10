"use client";

import { ArrowUp, Bot, Loader2, Search } from "lucide-react";
import type { FormEvent } from "react";

export type ResearchMode = "search" | "agent";

export default function SearchBar({
  mode,
  query,
  loading,
  onModeChange,
  onQueryChange,
  onSubmit,
  variant = "landing",
}: {
  mode: ResearchMode;
  query: string;
  loading: boolean;
  onModeChange: (mode: ResearchMode) => void;
  onQueryChange: (query: string) => void;
  onSubmit: (query: string) => void;
  variant?: "landing" | "inline";
}) {
  function submit(event: FormEvent) {
    event.preventDefault();
    const value = query.trim();
    if (value && !loading) onSubmit(value);
  }

  return (
    <form onSubmit={submit} className={`prompt-input ${variant === "inline" ? "prompt-input-inline" : ""}`}>
      {variant === "inline" && <Search className="prompt-input-icon" aria-hidden="true" />}
      <input
        name="query"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        placeholder={mode === "agent" ? "Ask anything about an institution…" : "Search entities, funds, or managers…"}
        aria-label={mode === "agent" ? "Ask agent" : "Search entities"}
        autoComplete="off"
      />
      {variant === "landing" && <div className="prompt-input-footer">
        <div className="prompt-mode" role="tablist" aria-label="Research mode">
          <button type="button" role="tab" aria-selected={mode === "search"} onClick={() => onModeChange("search")}
            className={mode === "search" ? "is-active" : ""}><Search /> Search</button>
          <button type="button" role="tab" aria-selected={mode === "agent"} onClick={() => onModeChange("agent")}
            className={mode === "agent" ? "is-active" : ""}><Bot /> Agent</button>
        </div>
        <button type="submit" className="prompt-submit" disabled={loading || !query.trim()} aria-label={loading ? "Working" : "Submit"}>
          {loading ? <Loader2 className="animate-spin" /> : <ArrowUp />}
        </button>
      </div>}
      {variant === "inline" && <button type="submit" className="prompt-submit" disabled={loading || !query.trim()} aria-label={loading ? "Searching…" : "Search entities"}>
        {loading ? <Loader2 className="animate-spin" /> : <ArrowUp />}
      </button>}
    </form>
  );
}
