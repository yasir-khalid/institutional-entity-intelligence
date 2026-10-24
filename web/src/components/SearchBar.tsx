"use client";

import { ArrowUp, Bot, Search } from "lucide-react";
import type { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";

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
      <Input
        name="query"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        placeholder={mode === "agent" ? "Ask anything about an institution…" : "Search entities, funds, or managers…"}
        aria-label={mode === "agent" ? "Ask agent" : "Search entities"}
        autoComplete="off"
      />
      {variant === "landing" && <div className="prompt-input-footer">
        <ToggleGroup
          type="single"
          value={mode}
          onValueChange={(value) => value && onModeChange(value as ResearchMode)}
          className="prompt-mode"
          aria-label="Research mode"
        >
          <ToggleGroupItem value="search" className={mode === "search" ? "is-active" : ""} aria-label="Search">
            <Search /> Search
          </ToggleGroupItem>
          <ToggleGroupItem value="agent" className={mode === "agent" ? "is-active" : ""} aria-label="Agent">
            <Bot /> Agent
          </ToggleGroupItem>
        </ToggleGroup>
        <Button type="submit" size="icon" className="prompt-submit" disabled={loading || !query.trim()} aria-label={loading ? "Working" : "Submit"}>
          {loading ? <Spinner /> : <ArrowUp />}
        </Button>
      </div>}
      {variant === "inline" && <Button type="submit" size="icon" className="prompt-submit" disabled={loading || !query.trim()} aria-label={loading ? "Searching…" : "Search entities"}>
        {loading ? <Spinner /> : <ArrowUp />}
      </Button>}
    </form>
  );
}
