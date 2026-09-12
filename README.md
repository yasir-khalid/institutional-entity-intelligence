# Institutional Entity Intelligence

Lean entity-resolution platform anchored on GLEIF LEI data. OpenSearch is used only
for candidate retrieval, never as the system of record — canonical data lives in
Parquet.

## Phase 1 (current): GLEIF ingestion + candidate search

```
GLEIF XML (entities/relationships/exceptions)
  -> streaming parse (lxml, bounded memory)
  -> normalize (names, addresses)
  -> Parquet (data/processed/)
  -> bulk index into OpenSearch (entities only)
  -> CLI candidate search
```

### Setup

```bash
uv sync
cp .env.example .env   # fill in OPENSEARCH_URL
```

### Run

```bash
# 1. Parse GLEIF XML -> Parquet (takes a while; 3.4M entity records)
uv run python -m er.ingestion.gleif

# 2. Create the OpenSearch index and bulk-load entities
uv run python -m er.indexing.opensearch_index

# 3. Search
uv run python -m er.search --name "Albacore Partners I Master Fund" --country IE
```

### Tests

```bash
uv run pytest
```

Out of scope for this phase: match scoring/decisions, gold dataset, external
sources (SEC/FCA/Companies House), relationship-graph resolution. See the project
plan for the full roadmap.
