# Institutional Entity Intelligence

Lean entity-resolution platform anchored on GLEIF LEI data. OpenSearch is used only
for candidate retrieval, never as the system of record — canonical data lives in
Parquet.

## Quickstart

**Setup** (once):

```bash
brew install libpostal   # macOS; ships its own trained model data
CFLAGS="-I/opt/homebrew/include" LDFLAGS="-L/opt/homebrew/lib" uv sync
cp .env.example .env     # fill in OPENSEARCH_URL
```

**Data pipeline** (once, or after changing raw GLEIF files — see "Phase 1/2" below
for details; each step reads the previous step's output):

```bash
uv run python -m er.ingestion.gleif        # raw XML/CSV -> data/processed/*.parquet (~10-15 min)
uv run python -m er.indexing.opensearch_index  # entities -> OpenSearch (~20 min)
uv run python -m er.validation              # sanity-check the processed tables
uv run python -m er.benchmark.generate      # data/benchmark/*.parquet (~1 sec, DuckDB)
```

**Day-to-day usage** — three CLIs, from simplest to richest:

```bash
# 1. Raw candidate search - "what does OpenSearch think this could be"
uv run python -m er.search --name "Sampo Oyj" --country FI

# 2. Full resolution - retrieve + score + decide, with evidence
uv run python -m er.match --name "North Rock Capital" --country GB

# 3. Relationship hierarchy - resolve a name (or pass --lei directly), then show
#    who manages it / what it's a sub-fund of / what it manages
uv run python -m er.hierarchy --name "Albacore Partners I Master Fund" --country IE
uv run python -m er.hierarchy --lei 635400Z5LRZZSML7CV16
```

**Testing**:

```bash
uv run pytest                                    # 75 unit tests, no live services needed
uv run python -m er.evaluation.run_benchmark      # scores er.match against the full
                                                   # 6,000-row benchmark (~5 min, needs
                                                   # live OpenSearch) -> evaluation_report.json
```

`pytest` covers every pure function (normalization, features, scoring, decisions,
benchmark generation, graph traversal) against small synthetic fixtures — no
OpenSearch or real data required, runs in seconds. `run_benchmark` is the
integration-level check: it exercises the real retrieval index end-to-end and is
how every scoring change in this project has actually been validated (see the
`name_ratio` bug fix below, found this exact way).

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

### A real bug the evaluation harness caught: abbreviated names scored *worse* than wrong ones

`python -m er.search --name "North rock capital" --country GB` correctly ranked
**NORTH ROCK CAPITAL MANAGEMENT (UK) LLP** #1. But `er.match` on the exact same
query ranked it **#7**, behind five wrong entities, and returned `UNMATCHED`.

Root cause: `name_ratio` used `rapidfuzz.fuzz.ratio` — a Levenshtein-style ratio
that's heavily penalized by raw string-length difference. An abbreviated query
("north rock capital", 19 chars) against its own full legal name ("...management
uk llp", 37 chars) scored **66.7**, *worse* than an unrelated same-length distractor
("north moor capital ltd") at **75.0** — purely because the wrong candidate happened
to be closer in length. Switched to `fuzz.token_set_ratio` (compares token sets,
not raw character sequences), which scores the true match **100** vs. the best
distractor **83.9** — confirmed this doesn't change anything for the
master/feeder or fund-number conflict cases, which are caught by their own
dedicated penalty features regardless of `name_ratio`. Regression test added:
`tests/test_features.py::test_name_ratio_favors_true_match_over_same_length_distractor`.

Re-ran the full benchmark before/after this one-line fix:

| | easy | medium (stripped/compact) | hard (confusable pair) |
|---|---|---|---|
| AUTO_MATCH coverage (before → after) | 96.8% → 96.8% | 26.5% → **41.5%** | 10.2% → **18.9%** |
| AUTO_MATCH precision (before → after) | 100% → 100% | 99.3% → 99.6% | 53.9% → **63.5%** |

Net positive — but not free: **dangerous-failure rate on confusable pairs went from
2.7% to 4.2%**. A more forgiving name-similarity metric that correctly rewards
abbreviated true matches is, unsurprisingly, also slightly more willing to
confidently pick between two genuinely ambiguous twin entities. Recall@20 (71.1%
overall) is unchanged, as expected — `name_ratio` only affects the *scorer*, not
retrieval. Full breakdown in `data/benchmark/evaluation_report.json`.

This is exactly the failure mode the project's design treats as most dangerous
(wrong entity, high confidence), so it's the top thing to dig into next — likely
by checking whether the confusable pairs it now gets wrong are the
`other_same_core` kind (no fund-number/master-feeder signal exists at all to catch
them, e.g. two same-named trusts in different jurisdictions) versus genuine
scoring failures on cases the conflict features *should* have caught.

### CLI output

Both `er.search` and `er.match` now render with **rich** — colored decision panels
(green/yellow/red for AUTO_MATCH/REVIEW/UNMATCHED), an evidence table, and a
candidates table with the chosen entity marked.

Out of scope for this phase: ML-based scoring, external sources
(SEC/FCA/Companies House), relationship-graph resolution, retrieval tuning to
address the medium-tier recall gap, and investigating the confusable-pair
dangerous-failure regression noted above.

## Phase 4: relationship hierarchy

Resolving a name to one LEI answers "what is this," but the more interesting
question for hedge-fund/institutional data is "what is it *part of*" — who manages
it, what master fund it feeds into, what sits above its manager. GLEIF's
relationship data (`gleif_relationships.parquet`, ingested in Phase 2 but unused
until now) already has this: `IS_DIRECTLY_CONSOLIDATED_BY`,
`IS_ULTIMATELY_CONSOLIDATED_BY`, `IS_FUND-MANAGED_BY`, `IS_SUBFUND_OF`,
`IS_FEEDER_TO`, `IS_INTERNATIONAL_BRANCH_OF` — every edge points `start → end` as
child → parent, and every node is a real LEI already in our entities table (no
cross-referencing needed).

```
src/er/graph/
├── models.py    # RelationshipEdge / RelationshipException / HierarchyResult,
│                  plus the relationship-type -> display-label mapping
├── edges.py     # raw DuckDB lookups: relationships/exceptions/names for one LEI
└── build.py     # assembles a HierarchyResult - upward + downward edges,
                   filtering INACTIVE rows, and reporting "missing parent"
                   exceptions only when no active relationship already answers them

src/er/hierarchy.py   # CLI
```

The "missing row ≠ confirmed no parent" caution from Phase 2 is enforced directly
in `build_hierarchy()`: `gleif_relationship_exceptions.parquet` explains *why* a
parent relationship is absent (`NATURAL_PERSONS`, `NON_CONSOLIDATING`,
`NO_KNOWN_PERSON`, `NO_LEI`, `NON_PUBLIC`) for exactly the cases where no row
exists, and an exception is only surfaced when it isn't already answered by an
active relationship of the corresponding type.

### Run

```bash
# By LEI directly
uv run python -m er.hierarchy --lei 635400OCWIKPSEDOHY65

# Or resolve a messy name first (via er.match), then show its hierarchy
uv run python -m er.hierarchy --name "Albacore Partners I Master Fund" --country IE
```

Real output for AlbaCore Partners I Master Fund: managed by ALBACORE CAPITAL
LIMITED, a sub-fund of AlbaCore Partners I ICAV, with direct/ultimate parent
explained as "entity does not prepare consolidated accounts" rather than silently
empty. Querying the manager entity itself (`--lei 635400Z5LRZZSML7CV16`) surfaces
its full managed-fund family — 34 funds — and its own ultimate parent chain up to
Mitsubishi UFJ Financial Group. This is the "messy observation → canonical entity →
institutional graph" flow the project has been building toward, now working
end-to-end.

Out of scope still: SEC/FCA/Companies House enrichment, multi-hop traversal
(showing a fund's manager's *own* other managed entities beyond one hop), and
resolving natural-person parents (GLEIF deliberately excludes these from LEI data).
