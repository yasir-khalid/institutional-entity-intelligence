# Institutional Entity Intelligence

Lean entity-resolution platform anchored on GLEIF LEI data. OpenSearch is used only
for candidate retrieval, never as the system of record — canonical data lives in
Parquet.

## What it does

Given a messy, real-world name for a fund or manager, identify the correct legal
entity and return every other identifier system that refers to the same entity —
with a confidence score and an explanation, never a silent black box.

```
  WHAT GOES IN (messy, inconsistent, real-world records)
  ───────────────────────────────────────────────────────
    "Acme Global Opportunities Fund II, L.P."     (from a SEC filing)
    "ACME GLOBAL OPP FUND 2 LP"                    (from a fund admin)
    "Acme Global Opportunities Feeder Fund II"     (a different entity!)
    "Acme Capital Management"                      (the manager, not the fund)

         │  every source spells names differently, uses different
         │  identifiers, and sometimes refers to a DIFFERENT but
         │  similar-looking entity (master vs feeder, fund II vs III)
         ▼

  ┌───────────────────────────────────────────────────────────┐
  │                                                           │
  │ WHAT THE PLATFORM DOES                                    │
  │                                                           │
  │ ┌─────────────┐     ┌─────────────┐     ┌─────────────┐   │
  │ │   RETRIEVE  │ ──▶ │    SCORE    │ ──▶ │    DECIDE   │   │
  │ │  "which 20  │     │  "does this │     │ auto-match /│   │
  │ │   entities  │     │  candidate  │     │  send to a  │   │
  │ │  could this │     │   actually  │     │   human /   │   │
  │ │     be?"    │     │   match?"   │     │  no match"  │   │
  │ └─────────────┘     └─────────────┘     └─────────────┘   │
  │                                                           │
  │ OpenSearch        explainable       confidence +          │
  │ candidate         feature scoring   full evidence         │
  │ search            (name/addr/       trail, never a        │
  │ over GLEIF        fund-number/      silent black box      │
  │ (3.4M entities)   master-feeder                           │
  │                   conflicts)                              │
  │                                                           │
  └───────────────────────────────────────────────────────────┘

         ▼
  WHAT COMES OUT
  ───────────────────────────────────────────────────────
    ER000000123  ◀── one internal canonical entity, holding:
         │
         ├── LEI            549300ABC123...
         ├── SEC CRD         123456              ┐
         ├── FCA FRN         918273              ├─ crosswalk of every
         ├── Companies House 08765432            │  external ID system
         │                                       ┘  pointing at the SAME
         │                                          real-world entity
         ├── decision: AUTO_MATCH (score 177, gap 68)
         ├── evidence: name 96% · jurisdiction ✓ · fund II ✓ · postcode ✓
         │
         └── relationships (from GLEIF):
                ER000000123 ──IS_FEEDER_TO──▶ ER000000055 (master fund)
                ER000000123 ──MANAGED_BY────▶ ER000000091 (Acme Capital Mgmt)
```

Only the `RETRIEVE` box (GLEIF ingestion + OpenSearch candidate search) is built so
far — see "Phase 1" below and "Out of scope" at the bottom for the rest of the
roadmap (`SCORE`, `DECIDE`, external sources, canonical entity/crosswalk tables).

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
