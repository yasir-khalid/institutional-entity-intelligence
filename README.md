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

**Day-to-day usage** — four CLIs, from simplest to richest. The first three accept
`--country` (ISO alpha-2 *or* a common alias: `UK`, `United Kingdom`, `USA`,
`Cayman Islands`, ... — see `COUNTRY_ALIASES` in
`er/normalisation/countries.py`) and `--country-mode soft|strict`
(`soft`, the default, is a strong ranking signal that never excludes a candidate;
`strict` hard-filters to that country only — use it when you're certain the field
is correct):

```bash
# 1. Raw candidate search - "what does OpenSearch think this could be"
uv run python -m er.search --name "Sampo Oyj" --country FI

# 2. Full resolution - retrieve + score + decide, with evidence, retrieval score
#    vs. match score shown separately, and (for REVIEW/UNMATCHED) a plain-English
#    reason plus which competing entities are tied
uv run python -m er.match --name "North Rock Capital" --country GB

# 3. Relationship hierarchy - resolve a name (or pass --lei directly), then show
#    who manages it / what it's a sub-fund of / what it manages.
#    --direction parents|children|all (default all) filters which side to show.
#    --depth N (default 1) walks that many hops - depth=2 also expands each
#    neighbor's own relationships (e.g. shows the "grandparent" too).
uv run python -m er.hierarchy --name "Albacore Partners I Master Fund" --country IE
uv run python -m er.hierarchy --lei 635400Z5LRZZSML7CV16 --direction parents --depth 2

# 4. Brand/family discovery - a DIFFERENT question from er.match. Not "which one
#    entity?" but "which SET of legal entities make up this institution?" Never
#    forces a single winner - groups results by confidence and role instead.
uv run python -m er.family --name "Point72"
```

**Testing** — two levels, run both after any change to retrieval/scoring/decision logic:

```bash
uv run pytest                                    # 94 unit tests, no live services, ~5s
uv run python -m er.evaluation.run_benchmark      # scores er.match against the full
                                                   # 6,000-row benchmark (~7 min, needs
                                                   # live OpenSearch) -> evaluation_report.json
```
`pytest` covers every pure function (normalization, country aliases, matcher
features/scoring/decisions/reason-building, query construction, benchmark
generation, graph traversal) in isolation. `run_benchmark` is the integration-level
check that has actually caught every real bug found in this project so far (see
Phase 3/5 below) — a `pytest` pass alone does not mean the live system behaves
correctly, since the unit tests use synthetic fixtures, not the real index.

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

Out of scope still: SEC/FCA/Companies House enrichment (multi-hop traversal is now
built - see Phase 6 below) and resolving natural-person parents (GLEIF
deliberately excludes these from LEI data).

## Phase 5: country semantics, retrieval/match score separation, better abstention

Two more real bugs found via manual probing (North Rock Capital, Point72), both
fixed, plus three UX/architecture improvements that came directly out of
diagnosing them.

**Bug: country was a hard filter, silently excluding the true entity.**
`--country IE` on the exact registered name of a GB entity returned `UNMATCHED` -
not because the matcher failed, but because `search_candidates()` used a `filter`
clause that removed the entity from the candidate pool before scoring ever started.
Real messy source data routinely has wrong/uncertain country fields, so this was a
real risk, not a contrived edge case. Fixed: country is now a `boosting` query - a
strong boost for a match, a real (if smaller) penalty for a mismatch - that can
never exclude a candidate outright. An explicit `--country-mode strict` still
exists as an opt-in hard filter for callers who trust the field completely.

**Bug: `--country UK` silently failed to narrow anything.** GLEIF stores ISO
3166-1 alpha-2 codes (`GB`), but real queries say "UK", "United Kingdom", "USA",
"Cayman Islands", etc. Without alias resolution, `--country UK` built a retrieval
query for a country code that doesn't exist in the index. Added
`COUNTRY_ALIASES` (`er/normalisation/countries.py`) resolved once, at the query
boundary, in *both* the retrieval layer and the matcher's own scoring features -
these two must stay in sync, since resolving the alias only in retrieval while
leaving the matcher's `country_exact`/`jurisdiction_exact` features comparing the
raw unaliased string caused `--country UK` and `--country GB` to silently produce
*different match scores* for the identical entity (found and fixed within this
same change, before it shipped).

**Retrieval score vs. match score, now separate and both shown.** `CandidateScore`
gained a `retrieval_score` field (OpenSearch's raw relevance score - "how useful is
this as a candidate") alongside the existing `score` (the deterministic ER
evidence score - "how much evidence says these are the same entity"). `er.match`'s
candidate table shows both columns side by side, so a retrieval-layer problem and a
scoring-layer problem are never confused with each other again.

**REVIEW/UNMATCHED now explain themselves.** Previously: "No confident candidate,"
full stop. Now, `MatchResult` carries a `reason`, `missing_evidence` (which query
fields - country, postcode, registration ID - are absent and would actually help),
and `competing_candidates` when the failure is a genuine tie. Querying "North Rock
Capital" with no country now reports: *"5 entities share very similar evidence for
this query (within 5 points of each other: US-DE, AE-DU, GB, HK, SG) - the query
doesn't contain enough information to distinguish them,"* with all five shown in a
table. This is deliberately not "forced" into a single winner - a bare brand-style
name genuinely doesn't disambiguate between five real, unrelated international
entities all called "North Rock Capital Management," and the system says so instead
of guessing.

**Hierarchy gained typed, directional traversal.** `er.hierarchy` now takes
`--direction parents|children|all` and shows each edge's raw GLEIF
`relationship_type` (`IS_FUND-MANAGED_BY`, `IS_ULTIMATELY_CONSOLIDATED_BY`, etc.)
alongside its human label, not just the label alone.

### Net effect on the benchmark

Re-ran `er.evaluation.run_benchmark` after each fix (cumulative from the Phase 3
baseline: Recall@20 71.1%, AUTO_MATCH precision 98.0%, dangerous-failure rate 2.7%):

| | Phase 3 baseline | + country boosting fix | + alias/scoring-sync fix (final) |
|---|---|---|---|
| Recall@20 (overall) | 71.1% | 75.0% | 74.9% |
| Recall@20 (confusable pairs) | 77.5% | — | **98.1%** |
| AUTO_MATCH precision | 98.0% | 95.5% | 96.3% |
| Dangerous-failure rate (confusable pairs) | 2.7% | 6.3% | 6.1% |

The country fix is a clear net win for retrieval — confusable-pair Recall@20 jumped
from 77.5% to 98.1%, since the old hard filter was silently dropping the true
entity in some of those adversarial cases too, not just the two hand-picked
examples that surfaced the bug. But it's not free: broader, more inclusive
retrieval also means more opportunities for the scorer to confidently pick the
wrong twin among genuinely confusable pairs, and the dangerous-failure rate reflects
that honestly rather than hiding it. **This is now the clearest concrete target for
the next scoring-side improvement** - the retrieval layer is finding the right
answer far more often; the remaining gap is in the scorer's confidence calibration
on confusable pairs specifically.

### Still open (not built)

From the broader roadmap this phase's findings pointed toward:
- **Brand/family vs. legal-entity resolution as a first-class distinction** - a
  bare brand name like "Point72" arguably shouldn't resolve to one LEI at all; it
  should trigger a *"here are the N legal entities under this brand"* response
  instead of a single-entity match/abstain. Not yet a separate code path -
  currently just falls out of REVIEW/UNMATCHED's tie-detection as a side effect.
- **Adversarial hedge-fund-specific cases in the auto-generated benchmark** (Point72
  Asset Management LP vs. Point72 Europe LLP; brand-vs-legal-entity pairs
  specifically, as opposed to the fund-number/master-feeder pairs already covered).
- **Failure-analysis categorization** in the evaluation report (wrong legal entity /
  correct entity missing from candidates / country conflict / fund-manager
  confusion), beyond the current aggregate precision/recall numbers.
- External sources (SEC/FCA/Companies House) - still last, per the original design.

## Phase 6: multi-hop hierarchy traversal

`er.hierarchy` gained `--depth N` (default `1`, exactly today's original
single-hop behavior - unchanged for anyone not passing the flag). `depth=2` also
expands each immediate neighbor's *own* relationships one more level; `depth=3`
one further, etc.

```
src/er/graph/models.py   # + HierarchyNode: a recursive node (lei, name, the
                            edge type/label/status connecting it to its parent,
                            upward/downward lists of more HierarchyNodes, and
                            `expanded: bool` - False means this branch stopped
                            here, either because depth ran out or the node was
                            already visited elsewhere in this traversal)
src/er/graph/build.py    # + build_hierarchy_tree(): reuses the existing
                            single-hop build_hierarchy() at each node it expands
src/er/hierarchy.py      # recursive Tree renderer replaces the old flat one
```

Two safety properties, both regression-tested with synthetic fixtures
(`tests/test_graph.py`):
- **Cycle protection** - a LEI is only ever expanded once per traversal, even if
  reachable via multiple paths (GLEIF data can have cycles - e.g. two entities
  that are each other's parent under different accounting relationship types). A
  revisited LEI is shown as a leaf (`expanded=False`), not re-expanded.
- **Node budget** (`max_nodes`, default 200) - hub entities can have large fan-out
  (Mitsubishi UFJ Financial Group has 96 direct subsidiaries at just one hop from
  AlbaCore Capital Limited); once the budget is spent, remaining nodes render as
  unexpanded leaves rather than the traversal running away.

### Run

```bash
uv run python -m er.hierarchy --lei 635400Z5LRZZSML7CV16 --direction parents --depth 1
# -> shows Mitsubishi UFJ Financial Group as ultimate parent, unexpanded

uv run python -m er.hierarchy --lei 635400Z5LRZZSML7CV16 --direction parents --depth 2
# -> same, but now also shows Mitsubishi UFJ's OWN upward relationships/exceptions
#    (in this real case: no known parent at either direct or ultimate level)
```

Before this, getting the "grandparent" required a second, separate CLI call with
the parent's own LEI - depth now does that automatically, with real production
data confirming both the cycle guard and the node budget matter (Mitsubishi UFJ's
96-subsidiary fan-out is exactly the kind of hub node the budget exists for).

## Phase 7: brand/family discovery (`er.family`)

`er.match` answers "which ONE legal entity is this?" — and correctly abstains when
a query is a brand rather than a legal name ("Point72" alone genuinely can't
resolve to one of Point72's 15+ legal entities). `er.family` answers the actually
different question: "which SET of legal entities make up this institution?" It's a
separate operation, not a fuzzier version of matching - it never forces a single
winner.

```
src/er/family/
├── brand.py      # pure: extract_brand_core(), classify_tier(), guess_role()
├── models.py     # FamilyMember / RelationshipEvidence / FamilyResult
├── discover.py   # orchestrator - the only file touching OpenSearch/DuckDB
└── __main__.py   # CLI (python -m er.family)
```

**Brand-core extraction**, validated against real GLEIF data before being written:
strips legal-form suffixes (reusing `strip_legal_suffix`) *and*, iteratively,
generic business words (capital, management, partners, fund, ...) and location
qualifiers (uk, hk, singapore, hong, kong, london, ...) from the tail — so
"Point72 Hong Kong Limited," "Point72 Japan Limited," and "Point72 Asset
Management, L.P." all collapse to `"point72"`, while real sub-brands that add a
distinguishing word (Point72 Credit, Point72 Lending) correctly do **not** collapse
away, and near-miss lookalikes (North Park Rock, North Wall Capital, Rolling Rock
Capital) correctly never match "north rock" at all — no fuzzy threshold needed,
just an exact-or-prefix rule on the extracted core.

One real bug found and fixed **before** this shipped: the iterative strip could
hollow a brand name out to `""` when the brand's own name is entirely
generic-sounding words ("Capital Group" → `""`, unusable). Fixed with a guard that
never strips the last remaining token — `"Capital Group"` now correctly extracts
to `"capital"` rather than nothing.

**On library research** (asked directly whether an existing library should replace
this): evaluated `cleanco` (legal-suffix stripping - functionally overlaps with
`strip_legal_suffix`, already built and tested across the whole pipeline) and
`CleanCorp` (attempts brand-root extraction, but unproven and not something to let
"dictate final brand IDs," by the same reasoning that led to writing this from
scratch). Neither solves the actual hard part - deciding that "capital management"
is noise while "credit" is a meaningful sub-brand is a domain judgment call, not
string cleanup, and the GLEIF-relationship-evidence layer (below) has no equivalent
in any generic library at all. Kept the custom parser.

**Graph evidence confirms, it doesn't discover.** After the lexical pool is
retrieved and classified, a new `fetch_relationships_among()`
(`er/graph/edges.py`) checks for GLEIF relationship edges *within* that pool only
- never used to expand the search itself, since that would pull in e.g. all 96
subsidiaries of a shared banking parent (seen in Phase 6) under any brand whose
manager happens to sit inside a large group.

### Run

```bash
uv run python -m er.family --name "Point72"
uv run python -m er.family --name "North Rock Capital"
```

Real output for Point72: 15 HIGH-confidence entities across 7 jurisdictions (US,
GB, HK, KY, AE, SG + more), 20 POSSIBLE sub-brands (Credit, Lending, Ventures,
Strategies, Global Macro, ...), many graph-confirmed, plus 20 concrete relationship
edges shown as evidence (e.g. Point72 Credit is directly/ultimately consolidated by
Point72 Lending Corp). For North Rock Capital: all 5 "NORTH ROCK CAPITAL
MANAGEMENT (...)" variants + the fund vehicle grouped HIGH; SPC/GP/digital-strategy
entities grouped POSSIBLE; North Park Rock, North Wall Capital, Rolling Rock
Capital, and Cedar Rock Capital - the deliberately-similar-but-unrelated
distractors - correctly absent from both.

Out of scope still: a richer structured name parser (separate `legal_form`/
`geography`/`role_terms`/`brand_tokens` fields rather than one collapsed
`brand_core` string) would handle more edge cases correctly, but the flat-string
approach already passes every real example tested, including the adversarial ones
- revisit only if a concrete new example actually breaks it. Also still open: the
`datasources/<source>/` restructuring and SEC Form ADV ingestion the user requested
alongside this feature - separate, larger efforts, sequenced next.
