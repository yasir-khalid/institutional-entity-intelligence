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

**Status: verified end-to-end.** 3,428,431 entities / 668,828 relationships /
6,185,301 exceptions parsed (counts match the GLEIF file headers exactly);
3,428,166 entities indexed into OpenSearch (1.1GB, well under the 20GB budget);
`er.search` returns correctly ranked candidates, including on the master/feeder
and fund-number-conflict cases the normalization was built to handle (e.g.
"Albacore Partners I Master Fund" ranks the exact entity #1, with "...II Master
Fund" and "...I Feeder ICAV" correctly ranked lower as distinct entities).

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

## Phase 2: full processed schema, ISIN bridge, validation, auto-generated benchmark

Turns all four raw GLEIF files into a complete, provenance-tracked processed layer,
and uses the ISIN↔LEI mapping as a **deterministic identifier bridge** to
auto-generate ER benchmark data instead of hand-labeling records: any GLEIF entity
that also appears in the ISIN↔LEI file has an independently-known correct answer
(its LEI) that didn't come from our own name-normalization logic — a trustworthy
positive label. Combined with intra-GLEIF "confusable" entity groups (same core
name, different fund number / master-feeder flag), this produces a large,
adversarial-aware evaluation set for free.

```
data/
├── raw/            # immutable — never modified by any code path
│   ├── ...lei2...zip, ...rr...zip, ...repex...zip, isin-lei-...zip
│
├── processed/
│   ├── gleif_entities.parquet                 (raw + normalized fields, provenance)
│   ├── gleif_relationships.parquet
│   ├── gleif_relationship_exceptions.parquet  (renamed from gleif_exceptions.parquet)
│   ├── isin_lei.parquet                       (new: ISIN <-> LEI identifier bridge)
│   └── validation_report.json                 (row counts, null rates, coverage %)
│
└── benchmark/
    ├── positives.parquet         # every entity independently confirmed via ISIN
    ├── hard_negatives.parquet    # confusable entity pairs (fund II vs III, master/feeder)
    └── evaluation_pairs.parquet  # curated sample of both, ready for a future scoring harness
```

Entities gain raw/normalized *pairs* that were missing in Phase 1 —
`legal_form_code`/`legal_form_other`, `registration_id`/`registration_id_norm`,
`legal_address_line1`/`legal_address_norm` (and the `hq_` equivalents) — plus
`entity_creation_date` and provenance columns (`source_file`, `snapshot_date`,
`ingested_at`) on every processed table. Raw values are never overwritten.

Address normalization uses **libpostal** (`postal.parser.parse_address`) rather than
naive string concatenation — it's a statistical parser trained on real-world postal
data, so it handles word-order/punctuation/abbreviation variation across sources far
better than regex would. Requires the native library first (macOS/Homebrew; ships
its own ~2GB trained model data bundled in the bottle):

```bash
brew install libpostal
# the `postal` Python binding is a C extension with no prebuilt wheel - point it at
# Homebrew's headers/lib before syncing:
CFLAGS="-I/opt/homebrew/include" LDFLAGS="-L/opt/homebrew/lib" uv sync
```

Validation and benchmark generation use **DuckDB** to query the Parquet files
directly — joins, self-joins, group-bys and stratified sampling as plain SQL over
files that don't fit comfortably in a single in-memory pass, rather than hand-rolled
Python loops or fighting pyarrow's join limitations (it refuses to join on
list-typed columns, which is why `positives.parquet` stores `sample_isin`/
`isin_count` rather than a full ISIN list).

### Run

```bash
# 1. Parse all 4 raw GLEIF files -> Parquet (re-run after Phase 1: adds isin_lei
#    and the new entity fields; ~10-12 min end to end)
uv run python -m er.ingestion.gleif

# 2. Validate the processed tables (uniqueness, malformed IDs, coverage, null rates)
uv run python -m er.validation

# 3. Generate the auto-labeled benchmark from the ISIN bridge + confusable-name groups
uv run python -m er.benchmark.generate
```

Out of scope for this phase (still on the roadmap): actually scoring against
`evaluation_pairs.parquet`, deterministic/ML match decisions, external sources
(SEC/FCA/Companies House), relationship-graph resolution.

## Phase 3: deterministic matcher + evaluation harness

**Bug fixed first**: `hard_negatives` grouped entities by exact `legal_name_core`,
but fund-structure tokens and fund numbers are *embedded in* `legal_name_core`
(it only strips legal-form suffixes like LP/LLC) — so "...MASTER FUND II" and
"...FEEDER FUND II" have different `legal_name_core` strings and could never land
in the same group. The table's headline adversarial cases (fund II vs III, master
vs feeder) were silently absent — 100% of the 30,725 rows were generic
`other_same_core` duplicates. Fixed by grouping on a new `aggressive_core` (SQL
regex strips structure tokens + trailing fund number before grouping); regenerated
benchmark now has 71,070 pairs: 38,226 `other_same_core`, 30,084 `fund_number`,
2,760 `master_feeder`.

Adds a small, deliberately modular matcher — each concern is one file, and scoring
is entirely config-driven (`matching:` in `config/dev.yaml`) so retuning it is a
config edit, never a code change:

```
src/er/matching/
├── features.py    # one pure function per comparison signal (name/address/conflicts)
├── scoring.py      # weighted sum of features -> score, using config weights/penalties
├── decisions.py    # score + gap-to-runner-up -> AUTO_MATCH / REVIEW / UNMATCHED
├── models.py        # CandidateScore / MatchResult / Decision
└── matcher.py        # orchestrator - the only file that calls OpenSearch

src/er/evaluation/
├── metrics.py          # pure aggregation (Recall@K, MRR, AUTO_MATCH precision, ...)
└── run_benchmark.py    # runs the matcher over evaluation_pairs.parquet, writes a report
```

### Run

```bash
# Single query with full decision + evidence
uv run python -m er.match --name "Albacore Partners I Master Fund" --country IE

# Score the matcher against the whole benchmark (~6000 live OpenSearch queries, ~5 min)
uv run python -m er.evaluation.run_benchmark
```

### First baseline (this snapshot)

| | easy (raw name) | medium (stripped/compact name) | hard (confusable pair, ambiguous name) |
|---|---|---|---|
| Recall@20 | 99.9% | 54.6% | 77.5% |
| AUTO_MATCH coverage | 96.8% | 26.5% | 10.2% |
| AUTO_MATCH precision | 100% | 99.3% | 53.9% |

Overall: Recall@20 71.1%, AUTO_MATCH precision 98.0%, **dangerous-failure rate on
confusable pairs 2.7%** (confidently matched the *wrong* twin entity — the metric
this design treats as mattering most). Full breakdown in
`data/benchmark/evaluation_report.json`.

Reading this: the matcher is appropriately conservative on hard cases (low
AUTO_MATCH coverage rather than guessing), which is the right failure mode, but two
things stand out as real next-step targets — the "medium" tier's retrieval recall
is weak (the compact/no-space query variant likely doesn't tokenize well against
OpenSearch's standard analyzer), and the 2.7% dangerous-failure rate on genuinely
ambiguous confusable pairs, while small, is non-zero and worth tracking as the
matcher evolves.

Out of scope for this phase: ML-based scoring, external sources
(SEC/FCA/Companies House), relationship-graph resolution, retrieval tuning to
address the medium-tier recall gap above.
