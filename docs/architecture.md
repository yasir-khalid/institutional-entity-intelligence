# Architecture

## What goes in, what comes out

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
  │ RETRIEVE          SCORE                DECIDE             │
  │ "which 20         "does this           auto-match /       │
  │  entities         candidate            send to a          │
  │  could this       actually             human /            │
  │  be?"             match?"              no match"          │
  │                                                            │
  │ OpenSearch        explainable          confidence +       │
  │ candidate         feature scoring      full evidence      │
  │ search over       (name/addr/          trail, never a     │
  │ GLEIF (3.4M       fund-number/         silent black box   │
  │ entities)         master-feeder                           │
  │                   conflicts)                               │
  └───────────────────────────────────────────────────────────┘

         ▼
  WHAT COMES OUT
  ───────────────────────────────────────────────────────
    ER000000123  ◀── one internal canonical entity, holding:
         │
         ├── LEI            549300ABC123...
         ├── SEC CRD         123456              ┐
         ├── SEC 13F filer   CIK 0001566307      ├─ crosswalk of every
         │                                       ┘  external ID system
         │                                          pointing at the SAME
         │                                          real-world entity
         ├── decision: AUTO_MATCH (score 177, gap 68)
         ├── evidence: name 96% · jurisdiction ✓ · fund II ✓ · postcode ✓
         │
         └── relationships (from GLEIF):
                ER000000123 ──IS_FEEDER_TO──▶ ER000000055 (master fund)
                ER000000123 ──MANAGED_BY────▶ ER000000091 (Acme Capital Mgmt)
```

## Retrieve / score / decide, in code

- **Retrieve** (`src/er/retrieval/`): builds an OpenSearch query over the
  candidate index (`src/er/indexing/opensearch_index.py`), boosting on name
  variants (full, core, compact/no-space) and soft-boosting on country without
  ever hard-excluding a candidate (a wrong-but-close country field on real
  messy data is common — see `docs/phases.md` Phase 5).
- **Score** (`src/er/matching/features.py` + `scoring.py`): one pure function per
  comparison signal (name similarity, jurisdiction, postcode, fund-number/
  master-feeder conflicts, registration ID), summed via config-driven weights
  in `config/dev.yaml` — every point in a score is traceable to a named
  contribution, never a black-box model.
- **Decide** (`src/er/matching/decisions.py`): score plus gap-to-runner-up
  determines `AUTO_MATCH` / `REVIEW` / `UNMATCHED`. A lone high score is
  trustworthy; two close high scores mean the query doesn't contain enough
  information to distinguish them, so the system says so explicitly rather
  than guessing (`reason`, `missing_evidence`, `competing_candidates` on
  `MatchResult`).

## Two different questions, two different operations

`er.cli.match` answers "which ONE legal entity is this?" and correctly abstains when
the query is a brand name that maps to many entities (e.g. "Point72"). `er.cli.family`
answers a genuinely different question — "which SET of legal entities make up
this institution?" — and never forces a single winner; it groups results by
confidence (HIGH/POSSIBLE) and role, using brand-core extraction plus GLEIF
relationship edges as confirming (not discovering) evidence. See
`src/er/family/brand.py` and `docs/phases.md` Phase 7.

## Canonical entity layer

`er.cli.match`, `er.cli.hierarchy`, and `er.cli.family` all answer questions about GLEIF
data specifically. `src/er/entity/` sits one level above that: it's the layer
where GLEIF and every other onboarded source (currently SEC 13F) become facts
about *one* canonical entity rather than two parallel systems joined by hand.

```
entities.parquet             one row per canonical entity (seeded 1:1 from
                              GLEIF today; entity_id is a distinct column from
                              GLEIF's own `lei` so a future source that
                              introduces entities GLEIF doesn't know about has
                              somewhere to attach without a schema change)

entity_identifiers.parquet   every identifier any registered source has
                              attached to an entity: (entity_id, identifier_type,
                              identifier_value, confidence, source)
```

`src/er/entity/sources.py` is a registry of small SQL-returning functions, one
per source, each reading that source's own crosswalk/processed table and
UNIONed together by `er.entity.build` - adding a new source's identifiers to
every entity profile going forward is exactly one function + one line in that
registry (see [`AGENTS.md`](../AGENTS.md)'s "Adding a new data source").

`er.cli.entity --name "..."` (or `--lei`) is the resulting single "tell me about
this institution" view: canonical identity, every attached identifier, the
GLEIF relationship neighborhood, and - when the entity has been resolved as a
SEC 13F filer via the crosswalk - its most recently reported holdings (always
labeled "latest SEC 13F reported holdings," never "holdings" or "portfolio"
unqualified, since 13F excludes shorts, derivatives, non-US securities, private
investments, and sub-threshold positions).

## Data sources and crosswalks

Each source under `src/er/datasources/<source>/` owns its own raw-file parsing,
schema, and quirks end to end — a problem in one source's ETL can never leak
into another's. All sources feed the same principle: raw fields go through a
pydantic model (the enforced raw→cleaned boundary) before ever reaching Parquet.

A **crosswalk** (`src/er/crosswalk/`) resolves another source's records to a
GLEIF LEI by reusing `er.matching.matcher.match()` unchanged — a SEC 13F filer
name is exactly the same "which single legal entity is this?" question the
matcher already answers for any name. This is the intended pattern for any
future source (SEC Form ADV, FCA, Companies House, ...): ingest independently,
then crosswalk through the existing matcher rather than writing new matching
logic per source.

## CLI separation

Every CLI (`python -m er.cli.<name>`) lives under `src/er/cli/` and only does
argument parsing and terminal rendering - no core package it calls
(`er.matching`, `er.entity`, `er.family`, `er.graph`, `er.datasources`, ...)
imports `argparse` or `rich`. This keeps every core package usable by a future
non-terminal consumer (an API, a notebook) and keeps each testable without a
live service or a captured terminal. See [`AGENTS.md`](../AGENTS.md)'s "CLI
separation" section for the exact pattern to follow when adding a new command.

## Evaluation

`src/er/benchmark/generate.py` auto-generates a large, adversarial-aware
evaluation set with no manual labeling: entities independently confirmed via the
ISIN↔LEI bridge (a trustworthy positive label that didn't come from our own
normalization logic) plus intra-GLEIF "confusable" pairs (same core name,
different fund number or master/feeder flag).

`src/er/evaluation/` runs the matcher against every pair and reports Recall@K,
MRR, AUTO_MATCH precision/coverage, `dangerous_failure_rate_confusable_pairs`
(a wrong entity picked confidently — the single worst failure mode this project
optimizes against), and a `failure_breakdown` that categorizes every row into
`success` / `wrong_auto_match` / `retrieval_miss` / `under_confident_top1` /
`correctly_deferred` — so a retrieval bug and a scoring-threshold problem are
never conflated. See [`experiments/README.md`](../experiments/README.md) for the
ongoing, proof-backed log of techniques tried against this benchmark.
