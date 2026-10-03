# Build history (phase-by-phase)

Detailed narrative of how this project was built, in order, including every real bug
found, how it was diagnosed, and the before/after numbers. Kept out of the main README
so newcomers get a quick orientation there and dig in here only when they want the
full story or need to understand why something is built the way it is.

For the ongoing, proof-backed record of retrieval/scoring experiments (separate from
this build history), see [`experiments/`](../experiments/README.md).

## Phase 1: GLEIF ingestion + candidate search

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

Out of scope for this phase: match scoring/decisions, gold dataset, external
sources (SEC/FCA/Companies House), relationship-graph resolution.

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
better than regex would.

Validation and benchmark generation use **DuckDB** to query the Parquet files
directly — joins, self-joins, group-bys and stratified sampling as plain SQL over
files that don't fit comfortably in a single in-memory pass, rather than hand-rolled
Python loops or fighting pyarrow's join limitations (it refuses to join on
list-typed columns, which is why `positives.parquet` stores `sample_isin`/
`isin_count` rather than a full ISIN list).

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
dedicated penalty features regardless of `name_ratio`.

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
retrieval.

Out of scope for this phase: ML-based scoring, external sources
(SEC/FCA/Companies House), relationship-graph resolution, retrieval tuning to
address the medium-tier recall gap, and investigating the confusable-pair
dangerous-failure regression noted above (later addressed - see `experiments/`).

## Phase 4: relationship hierarchy

Resolving a name to one LEI answers "what is this," but the more interesting
question for hedge-fund/institutional data is "what is it *part of*" — who manages
it, what master fund it feeds into, what sits above its manager. GLEIF's
relationship data already has this: `IS_DIRECTLY_CONSOLIDATED_BY`,
`IS_ULTIMATELY_CONSOLIDATED_BY`, `IS_FUND-MANAGED_BY`, `IS_SUBFUND_OF`,
`IS_FEEDER_TO`, `IS_INTERNATIONAL_BRANCH_OF` — every edge points `start → end` as
child → parent, and every node is a real LEI already in our entities table.

```
src/er/graph/
├── models.py    # RelationshipEdge / RelationshipException / HierarchyResult
├── edges.py     # raw DuckDB lookups: relationships/exceptions/names for one LEI
└── build.py     # assembles a HierarchyResult - upward + downward edges,
                   filtering INACTIVE rows, and reporting "missing parent"
                   exceptions only when no active relationship already answers them

src/er/hierarchy.py   # CLI
```

`gleif_relationship_exceptions.parquet` explains *why* a parent relationship is
absent (`NATURAL_PERSONS`, `NON_CONSOLIDATING`, `NO_KNOWN_PERSON`, `NO_LEI`,
`NON_PUBLIC`) for exactly the cases where no row exists, and an exception is only
surfaced when it isn't already answered by an active relationship of the
corresponding type — "missing row ≠ confirmed no parent."

Real output for AlbaCore Partners I Master Fund: managed by ALBACORE CAPITAL
LIMITED, a sub-fund of AlbaCore Partners I ICAV, with direct/ultimate parent
explained as "entity does not prepare consolidated accounts" rather than silently
empty. Querying the manager entity itself surfaces its full managed-fund family —
34 funds — and its own ultimate parent chain up to Mitsubishi UFJ Financial Group.

## Phase 5: country semantics, retrieval/match score separation, better abstention

Two more real bugs found via manual probing (North Rock Capital, Point72), both
fixed, plus three UX/architecture improvements that came directly out of
diagnosing them.

**Bug: country was a hard filter, silently excluding the true entity.**
`--country IE` on the exact registered name of a GB entity returned `UNMATCHED` -
not because the matcher failed, but because `search_candidates()` used a `filter`
clause that removed the entity from the candidate pool before scoring ever started.
Fixed: country is now a `boosting` query - a strong boost for a match, a real (if
smaller) penalty for a mismatch - that can never exclude a candidate outright. An
explicit `--country-mode strict` still exists as an opt-in hard filter for callers
who trust the field completely.

**Bug: `--country UK` silently failed to narrow anything.** GLEIF stores ISO
3166-1 alpha-2 codes (`GB`), but real queries say "UK", "United Kingdom", "USA",
"Cayman Islands", etc. Added `COUNTRY_ALIASES` (`er/normalisation/countries.py`)
resolved once, at the query boundary, in *both* the retrieval layer and the
matcher's own scoring features - these two must stay in sync, since resolving the
alias only in retrieval while leaving the matcher's `country_exact`/
`jurisdiction_exact` features comparing the raw unaliased string caused
`--country UK` and `--country GB` to silently produce *different match scores*
for the identical entity.

**Retrieval score vs. match score, now separate and both shown.** `CandidateScore`
gained a `retrieval_score` field (OpenSearch's raw relevance score) alongside the
existing `score` (the deterministic ER evidence score), so a retrieval-layer
problem and a scoring-layer problem are never confused with each other.

**REVIEW/UNMATCHED now explain themselves.** `MatchResult` carries a `reason`,
`missing_evidence` (which query fields would actually help), and
`competing_candidates` when the failure is a genuine tie. Querying "North Rock
Capital" with no country now reports: *"5 entities share very similar evidence for
this query (within 5 points of each other: US-DE, AE-DU, GB, HK, SG) - the query
doesn't contain enough information to distinguish them,"* with all five shown.

**Hierarchy gained typed, directional traversal.** `er.hierarchy` now takes
`--direction parents|children|all` and shows each edge's raw GLEIF
`relationship_type` alongside its human label.

### Net effect on the benchmark

| | Phase 3 baseline | + country boosting fix | + alias/scoring-sync fix (final) |
|---|---|---|---|
| Recall@20 (overall) | 71.1% | 75.0% | 74.9% |
| Recall@20 (confusable pairs) | 77.5% | — | **98.1%** |
| AUTO_MATCH precision | 98.0% | 95.5% | 96.3% |
| Dangerous-failure rate (confusable pairs) | 2.7% | 6.3% | 6.1% |

The country fix is a clear net win for retrieval, but not free: broader, more
inclusive retrieval also means more opportunities for the scorer to confidently
pick the wrong twin among genuinely confusable pairs.

## Phase 6: multi-hop hierarchy traversal

`er.hierarchy` gained `--depth N` (default `1`, unchanged single-hop behavior for
anyone not passing the flag). `depth=2` also expands each immediate neighbor's
*own* relationships one more level; `depth=3` one further, etc.

Two safety properties, both regression-tested with synthetic fixtures:
- **Cycle protection** - a LEI is only ever expanded once per traversal, even if
  reachable via multiple paths. A revisited LEI is shown as a leaf
  (`expanded=False`), not re-expanded.
- **Node budget** (`max_nodes`, default 200) - hub entities can have large fan-out
  (Mitsubishi UFJ Financial Group has 96 direct subsidiaries at just one hop from
  AlbaCore Capital Limited); once the budget is spent, remaining nodes render as
  unexpanded leaves rather than the traversal running away.

## Phase 7: brand/family discovery (`er.family`)

`er.match` answers "which ONE legal entity is this?" — and correctly abstains when
a query is a brand rather than a legal name ("Point72" alone genuinely can't
resolve to one of Point72's 15+ legal entities). `er.family` answers the actually
different question: "which SET of legal entities make up this institution?"

```
src/er/family/
├── brand.py      # pure: extract_brand_core(), classify_tier(), guess_role()
├── models.py     # FamilyMember / RelationshipEvidence / FamilyResult
├── discover.py   # orchestrator - the only file touching OpenSearch/DuckDB
└── __main__.py   # CLI (python -m er.family)
```

**Brand-core extraction**, validated against real GLEIF data: strips legal-form
suffixes *and*, iteratively, generic business words (capital, management,
partners, fund, ...) and location qualifiers (uk, hk, singapore, hong, kong,
london, ...) from the tail — so "Point72 Hong Kong Limited," "Point72 Japan
Limited," and "Point72 Asset Management, L.P." all collapse to `"point72"`, while
real sub-brands that add a distinguishing word (Point72 Credit, Point72 Lending)
correctly do **not** collapse away, and near-miss lookalikes (North Park Rock,
North Wall Capital, Rolling Rock Capital) correctly never match "north rock" at
all — no fuzzy threshold needed, just an exact-or-prefix rule on the extracted
core.

One bug found and fixed before this shipped: the iterative strip could hollow a
brand name out to `""` when the brand's own name is entirely generic-sounding
words ("Capital Group" → `""`). Fixed with a guard that never strips the last
remaining token.

**Graph evidence confirms, it doesn't discover.** After the lexical pool is
retrieved and classified, `fetch_relationships_among()` checks for GLEIF
relationship edges *within* that pool only - never used to expand the search
itself, since that would pull in e.g. all 96 subsidiaries of a shared banking
parent under any brand whose manager happens to sit inside a large group.

Real output for Point72: 15 HIGH-confidence entities across 7 jurisdictions, 20
POSSIBLE sub-brands, many graph-confirmed, plus 20 concrete relationship edges
shown as evidence.

## Phase 8: `datasources/<source>/` restructuring + Makefile

Mechanical refactor, no new data or behavior change - purely so ingestion code is
isolated per source before a second source gets added.

```
src/er/datasources/
├── common/
│   └── parquet_writer.py   # BatchedParquetWriter - source-agnostic, shared
└── gleif/
    ├── schema.py           # GLEIF's own Parquet schemas
    ├── ingest.py           # entities/relationships/exceptions XML parsers
    └── isin_lei.py         # ISIN<->LEI CSV parser
```

The principle going forward: **a problem in one source's ETL can never be a
problem in another's** - each source owns its raw-file parsing, schema, and
quirks (dedup rules, snapshot-date extraction, ...) completely, and only the
generic `BatchedParquetWriter` is shared.

Added a root `Makefile` as the centralized trigger - one target per source, plus
source-agnostic shared steps (`index`, `validate`, `benchmark`), a `pipeline`
target chaining all of them, and `test` / `evaluate`.

## Phase 9: clear raw→cleaned models, extracted field helpers, configurable indexing

Three readability/architecture improvements to the GLEIF ingestion pipeline -
deliberately **not** a decorator-based field-mapping DSL (considered and
rejected: it would hide the actual field logic behind indirection and make
debugging a bad value harder).

**The raw→cleaned model boundary is now real, not decorative.** `GleifEntity` /
`GleifRelationship` / `GleifRelationshipException` / `IsinLei` used to be dead
code: `ingest.py` built a plain dict and wrote it straight to Parquet, never
validating through them. Every parser now does `GleifEntity(**fields).model_dump()`
before writing - a genuinely enforced contract.

**Field extraction is now named and grouped, not one long inline dict.** Split
into `er/datasources/gleif/fields.py`, one function per logical group. Pulled the
three truly source-agnostic helpers (`open_zip_member`, `clear_element`,
`element_text`) into `er/datasources/common/xml_utils.py`.

**OpenSearch bulk-load refresh interval is now configurable**
(`opensearch.refresh_interval_during_bulk` / `refresh_interval_after_bulk`).

Ran the full production pipeline end to end: every count identical to the
pre-refactor baseline (3,428,166 entities post-dedup, 668,828 relationships,
6,185,301 exceptions, 9,261,589 ISIN mappings), `make validate` passing clean.

## Phase 10: SEC Form 13F ingestion, crosswalk, and a proof-backed experiments log

Added a second data source under the Phase 8 convention
(`src/er/datasources/sec_13f/`), a crosswalk resolving 13F filers to GLEIF LEIs via
the existing matcher, and started `experiments/` - a directory of proof-backed
retrieval/scoring experiments, each explicitly marked VALIDATED or INVALIDATED
against a measured `make evaluate` result rather than left as an unverified idea.
See [`experiments/README.md`](../experiments/README.md) for the full, current list;
notable ones from this phase:

- **`legal_name_compact` retrieval field** - fixed a real zero-candidate retrieval
  failure for glued/no-space queries ("fnbbank") by adding a space-stripped exact-
  match field, diagnosed by direct `search_candidates()` calls before writing any
  fix.
- **Failure-analysis categorization** - every evaluation row now buckets into
  `success` / `wrong_auto_match` / `retrieval_miss` / `under_confident_top1` /
  `correctly_deferred`, so a retrieval bug and a scoring-threshold problem are
  never conflated in the aggregate numbers again.
- **Master/feeder conflict false-positive fix** - `master_conflict`/
  `feeder_conflict` were silently penalizing the correct master/feeder candidate
  whenever the query simply didn't mention "master"/"feeder" (e.g. an abbreviated
  query, or the benchmark's own `confusable_pair` rows) - fixed to require the
  query to positively assert a claim before checking for a contradiction.

SEC 13F ingestion (`src/er/datasources/sec_13f/{models,schema,ingest}.py`) parses
the SEC's quarterly bulk TSV-in-zip files (`SUBMISSION.tsv` + `COVERPAGE.tsv`
joined into a filings table, `INFOTABLE.tsv` into a holdings table) via DuckDB's
`read_csv` rather than a hand-rolled parser - these files are TSV, not XML, so
none of GLEIF's streaming-iterparse machinery applies. The crosswalk
(`src/er/crosswalk/sec_13f_to_gleif.py`) resolves each unique 13F filer to a
GLEIF LEI by calling `er.matching.matcher.match()` unchanged - a 13F filer name is
exactly the same "which single legal entity is this?" question the matcher
already answers for any source.

Real run against 10,672 unique 13F filers (one quarterly bulk file, 2026-Q1),
before the fixes below:
3,255 AUTO_MATCH, 845 REVIEW, 6,572 UNMATCHED - e.g. "ADVANCED MICRO DEVICES INC"
and "American Airlines Group Inc." both resolved correctly with wide score gaps
(151 and 134 points respectively). The large UNMATCHED share is expected and
correct, not a bug: most 13F filers are exactly the "brand vs. legal entity" and
"which of several near-identical funds" ambiguity this project is built to
recognize rather than paper over - most institutional names in this list have
no independently-confirming evidence (postcode, registration ID) in the query at
all, only a name and a US state/country, which real, thorough resolution
correctly treats with less confidence than a name+address+ID match would earn.

`er.evaluation.run_benchmark`'s new `by_conflict_type` breakdown (added in this
same phase to make experiment 003 measurable) surfaced an adjacent finding: the
`fund_number` confusable-pair slice showed 0% AUTO_MATCH precision. Direct
reproduction showed this was a **benchmark labeling artifact** (a stripped
adversarial query coincidentally exact-matched a real, unrelated third GLEIF
entity), not a matcher bug - fixed by adding a collision guard to
`generate_hard_negatives()` (experiment 004). A second, genuinely real bug
surfaced on the `master_feeder` slice instead: `name_core_exact` inherently
favors the master/plain-name variant over the feeder whenever the query omits
the qualifier, since the feeder's own name has an extra token that can never
exact-match. Fixed with `_fund_structure_ambiguous()` in
`er.matching.matcher` (experiment 005) - refuses AUTO_MATCH when the query
asserts no master/feeder claim and the top-2 candidates disagree on structure,
regardless of score gap. Net effect on `master_feeder`:
**dangerous-failure rate 26.1% -> 0.0%**, AUTO_MATCH precision **53.9% -> 100%**.
See [`experiments/004`](../experiments/004-benchmark-collision-artifact-not-a-matcher-bug.md)
and [`experiments/005`](../experiments/005-fund-structure-ambiguity-guard.md) for the full numbers.

## Phase 11: canonical entity layer (`er.entity`) and an extensible identifier-source registry

Until this phase, GLEIF-anchored entity resolution (`er.match`/`er.hierarchy`/
`er.family`) and SEC 13F data (ingestion + crosswalk) were two parallel systems
joined only by hand-written DuckDB SQL - a real gap, since the actual product
value is one canonical entity carrying facts from every source, not two
datasets a user has to join themselves.

```
src/er/entity/
├── models.py     # CanonicalEntity fields, EntityIdentifier, Sec13FActivity,
│                   EntityProfile - the one request-level view
├── sources.py    # THE extension point: one SQL-returning function per source,
│                   registered in IDENTIFIER_SOURCES - see below
├── build.py      # entities.parquet (seeded 1:1 from GLEIF) + entity_identifiers.parquet
│                   (every registered source's identifiers, UNIONed via DuckDB)
├── profile.py    # get_entity_profile(): identity + identifiers + GLEIF
│                   relationships (reuses er.graph.build.build_hierarchy
│                   unchanged) + SEC 13F activity summary
└── __main__.py   # CLI (python -m er.entity --name "..." / --lei ...)
```

**Extensibility was the explicit design goal, not an afterthought.** Adding a
new source's identifiers to every entity profile going forward means writing
ONE function in `er/entity/sources.py` - a SQL SELECT over that source's own
crosswalk output, aliased to five fixed columns - and appending it to
`IDENTIFIER_SOURCES`. No source function loads rows into Python; `build.py`
UNIONs every query and writes the result in one DuckDB `COPY`, so a
future-onboarded source with millions of rows costs nothing extra to wire in.
A source function returns `None` when its upstream data doesn't exist yet
(e.g. a fresh checkout that hasn't run a crosswalk), so the entity layer
degrades gracefully rather than failing. Two sources are wired in from day
one to prove the pattern: GLEIF's own ISIN↔LEI bridge (9.27M rows, sitting
unused since Phase 2) and the SEC 13F crosswalk.

**`er.entity`'s output is deliberately careful about what SEC 13F data means.**
It always labels holdings "latest SEC 13F reported holdings," never "holdings"
or "portfolio" unqualified - 13F excludes shorts, derivatives, non-US
securities, private investments, and sub-threshold positions, and showing it
unqualified would misrepresent a partial disclosure as a complete picture.

### Run

```bash
make build-entities
uv run python -m er.entity --name "Fred Alger Management" --country US
uv run python -m er.entity --lei R2I72C950HOYXII45366   # AMD - files 13F on its own treasury holdings
```

Real output for AMD's own LEI: identity + 912 ISINs (collapsed to a sample in
the CLI table) + a resolved SEC CIK + its GLEIF subsidiary/parent relationships
(AMD India, Xilinx Holding entities) + its own latest 13F filing (period
2026-Q1, 4 securities reported, largest being Sanmina Corp) - one profile
spanning both sources, exactly the fork-in-the-road integration this phase
targeted rather than a separate, disconnected `er.holdings` command.

Out of scope still, per explicit design discussion: historical/multi-quarter
13F ingestion (only one quarter is loaded, so no quarter-over-quarter position
change analysis is possible yet), a dedicated crosswalk-precision evaluation
harness (distinct from the general GLEIF benchmark), and Form ADV/FCA/Companies
House as additional sources (the registry pattern above is what makes each of
those a small, additive change whenever undertaken).

## Phase 12: strict CLI/core-logic separation (`er.cli`)

Every CLI in the project - `er.match`, `er.search`, `er.hierarchy`,
`er.family`, `er.entity`, plus the previously argparse-less `main()` functions
in `er.datasources.gleif.ingest`, `er.datasources.sec_13f.ingest`,
`er.indexing.opensearch_index`, `er.validation`, `er.benchmark.generate`,
`er.evaluation.run_benchmark`, `er.crosswalk.sec_13f_to_gleif`, and
`er.entity.build` - moved into one package: `src/er/cli/`, invoked as
`python -m er.cli.<name>`. This was a deliberate architectural line, not a
cosmetic move: no package outside `er.cli` may import `argparse` or `rich`.

Each moved core module now exposes a plain `run_all(cfg) -> dict` (or
equivalent) instead of a `main()` - no logging setup, no `sys.exit()`, no
argument parsing. The corresponding `er/cli/<name>.py` does that wiring and
adds a `console.status(...)` spinner around the work plus a `Fetched in
{elapsed:.2f}s` summary line at the end, so a multi-second live-service call
never leaves a blank terminal. `er.entity`'s rendering, already split into its
own `render.py` in the prior phase, moved to `er/cli/entity_render.py`
alongside the other CLI code, and that render function was fixed to group and
collapse high-fan-out relationship edges (a manager with 45 funds was
flooding the table one row per edge) the same way high-cardinality
identifiers were already collapsed.

All `Makefile` targets and documented `uv run python -m er.X` commands were
updated to the new `er.cli.X` paths - `make help`, `README.md`, `AGENTS.md`,
and `docs/architecture.md` are the sources of truth for current invocations;
this file's earlier phases keep their original `python -m er.X` examples
as-written, since they're a historical record of what was true when each
phase shipped, not a living reference.

### Verify

```bash
make test                                          # 142 unit tests, unaffected
grep -rl "import argparse\|import rich\|from rich" src/er/ --include="*.py" | grep -v "^src/er/cli/"
                                                    # -> prints nothing
uv run python -m er.cli.match --name "Sampo Oyj" --country FI
uv run python -m er.cli.entity --lei R2I72C950HOYXII45366
```

## Phase 13: web UI (`web/` + `src/er/api/`)

A Next.js frontend giving the same capability as `er.cli.entity` a visual,
clickable form: search a name/LEI/CUSIP, see a depth-2 relationship tree, click
any node for its full profile.

```
src/er/api/           # FastAPI backend - HTTP wiring + JSON shaping only
├── app.py            # /api/search, /api/entity/{id}, /api/entity/{id}/tree
└── schemas.py         # response models, separate from the internal domain
                        # models (er.matching.models/er.graph.models/
                        # er.entity.models) - this module's only job is
                        # shaping data for the frontend.

web/                   # Next.js (App Router, TypeScript, Tailwind)
├── src/lib/api.ts      # typed fetch client, mirrors schemas.py exactly
├── src/components/     # SearchBar, ResultsList, TreeExplorer (collapsible
│                         indented tree list), DetailsPanel
└── src/app/page.tsx    # wires them together - the only route
```

Same principle as `er.cli`: the API is a thin translation layer, not a second
implementation of matching/hierarchy logic. `/api/search` calls
`er.matching.matcher.match()` for name search (plus lightweight DuckDB lookups
for direct LEI or CUSIP-based search - the latter joins
`sec_13f_holdings.parquet` -> `sec_13f_filings.parquet` -> the crosswalk to
resolve a CUSIP to the GLEIF entities that reported holding it).
`/api/entity/{id}/tree` calls `er.graph.build.build_hierarchy_tree()`
unchanged and converts its `HierarchyNode` tree into a frontend-friendly JSON
shape. `/api/entity/{id}` calls `er.entity.profile.get_entity_profile()`
unchanged.

Tree rendering went through two iterations before landing on a plain
collapsible list: first `react-d3-tree` (SVG tree layout - abandoned when
cycle-protected duplicate nodes produced overlapping, badly-fonted labels),
then `react-force-graph-2d` (canvas-based, force-directed/DAG graph, same
library the referenced `lattice` repo uses - abandoned in turn once a real
entity with 40+ funds made a canvas layout unwieldy to keep readable, and
`dagMode` turned out to reject perfectly valid GLEIF data as an "invalid DAG"
whenever a relationship got independently rediscovered from both ends).
`TreeExplorer.tsx` is a plain indented, collapsible list instead - no
extra dependency, scales to a large fan-out by simple scrolling/collapsing,
and explicitly highlights both the originally-searched root (a blue `QUERY`
badge) and whichever row is currently selected (blue shading), which a
force-directed layout made harder to keep visually stable.

### Run

```bash
make api                 # backend on :8000
cd web && npm run dev    # frontend - picks 3000 or the next free port
```

### Verify

```bash
curl "http://localhost:8000/api/search?query=Sampo+Oyj&search_type=name&country=FI"
curl "http://localhost:8000/api/entity/549300TITGLG7BXCGB39/tree?depth=2"
cd web && npx tsc --noEmit && npm run build   # TypeScript + production build both clean
```

Confirmed live: search resolves correctly across all three modes (name via the
matcher, direct LEI lookup, CUSIP-to-filer join), the tree endpoint returns a
correctly nested parent/subsidiary structure for a real entity (Fred Alger
Management, 2 parents + 45 funds), and the frontend's CORS/fetch wiring works
end to end against the live backend.

Out of scope still: no automated frontend tests (manual verification only,
given the size of this addition, using a headless Chrome instance driven
directly rather than guessing from screenshots), and no authentication on the
API (loopback-only CORS is the only safeguard - do not deploy this API to a
non-localhost address without adding auth first).

## Phase 14: org-chart tree layout, skeleton loading, and a real data-scale bug

Researched how real corporate-structure tools present ownership hierarchies
(Moody's Orbis "corporate trees", React Flow's expand-collapse org-chart
pattern) before rebuilding the tree a second time: a hierarchical top-down
layout with rounded-corner card nodes (`@xyflow/react` + `dagre` for layout),
each with its own independent expand/collapse toggle, replacing the plain
collapsible list from Phase 13. `EntityNode.tsx` renders the card (green top
border for parents, purple for subsidiaries/funds, a blue **Query** badge on
the root, a blue ring on the selected entity); `TreeGraph.tsx` flattens the
API's nested tree, runs dagre, and tracks per-node collapse state.

Two real bugs found while testing against a real large entity (Fred Alger
Management, a sizeable asset manager):

1. **Collapse hid unrelated siblings.** The flatten step kept every
   relationship edge, including cross-links where a sibling's own upward
   listing pointed at another sibling already reached directly from root.
   Collapsing one fund then transitively hid ~35 of ~47 unrelated top-level
   entities, since the collapse logic couldn't distinguish "this node's real
   children" from "an unrelated node reachable via a back-reference." Fixed
   by building a proper spanning tree instead - one parent edge per entity,
   first-discovery wins, subtree explored exactly once. Verified live:
   expanding one fund now reveals only its own umbrella + sub-funds while all
   11 other top-level siblings stay untouched.

2. **A hub-heavy entity's tree exploded to 1,111 nodes.** `/api/entity/{id}/tree`
   inherited `build_hierarchy_tree`'s CLI-tuned `max_nodes=200` default, but
   that budget counts *expansions*, not total tree size - each expansion can
   list many un-expanded leaf children, and the relationship between the two
   is highly non-linear for hub-heavy entities: measured live on the same
   real entity, `max_nodes=35` produced 48 total nodes, `max_nodes=40`
   produced 434, and `max_nodes=55` produced 1,111 - one extra hub expansion
   unlocking a cascade. This wasn't fixable on the frontend alone (a
   force-directed canvas, a plain list, or an org chart all still have to
   receive, parse, and lay out however many nodes the API sends before any of
   them can visually hide something). Fixed with a dedicated, much lower
   `max_nodes` default (30) on the web endpoint specifically, chosen to sit
   safely below where the cascade started - `build_hierarchy_tree`'s own CLI
   default is untouched.

Also added `Skeletons.tsx` (a shared `Bar` primitive plus `ResultsSkeleton`/
`TreeSkeleton`) and wired a loading skeleton into every async boundary: the
results list while searching, the tree area while it loads, and the details
panel while an entity loads.

### Verify

```bash
uv run pytest                                 # unaffected, still 147 passing
cd web && npx tsc --noEmit && npm run build   # clean
curl "http://localhost:8000/api/entity/549300TITGLG7BXCGB39/tree?depth=2" | \
  python3 -c "import json,sys; print(len(json.load(sys.stdin)))"  # bounded, not 1,111
```

Confirmed live with a real headless Chrome driven through the actual search
-> expand -> collapse flow (not just TypeScript/build checks), including the
specific expand/collapse scenario that exposed the spanning-tree bug.

## Phase 15: search-first landing page, plain indented tree (drop the graph library)

Two changes, both simplifications:

1. **Landing page is search-first.** `page.tsx` now renders a minimal,
   centered search bar (title + subtitle + input, nothing else) until the
   user actually searches for something - like a search engine homepage -
   rather than the full results/tree/details chrome being visible (empty)
   from the first load.
2. **Dropped the graph-diagram library entirely.** `@xyflow/react` + `dagre`
   (Phase 14's org chart) is gone, replaced by `EntityTreeView.tsx`: a plain
   indented list with vertical guide lines, rounded chip cards, and a
   ▾/▸ toggle per branch - no canvas, no pan/zoom/drag, no auto-layout
   engine. The product's tree is always fundamentally a tree, not a general
   graph, and a plain list needs no extra dependency and cannot suffer a
   diagramming library's own layout/DAG-validity concerns (see Phase 14's
   `dagMode` bug for a concrete example of that risk). The same
   spanning-tree fix from Phase 14 (one parent edge per entity,
   first-discovery wins) carried over unchanged into the new component.

### Verify

```bash
cd web && npx tsc --noEmit && npm run build   # clean
```

Confirmed live with a real headless Chrome: the landing page shows only the
centered search bar before any search, a name/LEI/CUSIP search transitions to
the results+tree+details layout, and expanding one branch of the tree
(screenshotted at `/tmp/tree.png` during verification) reveals only that
branch's own children while all sibling cards stay untouched.

## Phase 16: surface lineage and provenance in the UI

GLEIF's own identity timeline for an entity (`entity_creation_date`,
`initial_registration_date`, `last_update_date`, `next_renewal_date`,
`registration_status`) has been sitting in `gleif_entities.parquet` since
Phase 2, and every identifier's provenance (`source_file`, `snapshot_date`,
`ingested_at`) has been on every source table since it was first written via
`BatchedParquetWriter` - but neither ever reached the canonical entity layer,
the API, or any CLI/web consumer. "Entity identity, lineage, provenance" is
durable, foundational data; capturing it at ingestion time and never
surfacing it anywhere was a real gap, not a missing nice-to-have.

Threaded through the full stack, each layer additive and backward compatible:

- `er.entity.build.build_entities()`: `entities.parquet` now also carries the
  five GLEIF lineage columns plus the ingestion snapshot date.
- `er.entity.sources`: every identifier source's SQL now selects
  `source_file, snapshot_date, ingested_at` alongside the existing five
  columns - the contract every future source function follows is now eight
  columns, not five.
- `er.entity.models`: new `EntityLineage` model; `EntityIdentifier` gains the
  three provenance fields.
- `er.entity.profile.get_entity_profile()`: loads and returns both.
- `er.api.schemas`/`app.py`: `EntityLineageOut`, extended `EntityIdentifierOut`,
  `EntityDetail.lineage` - the web API now returns all of it.
- `er.cli.entity_render`: one new dim line ("Lineage [ISSUED]: created ... ·
  registered ... · last updated ... · renewal due ...") - the CLI benefits
  from the same backend change with a two-line addition.
- `web/src/components/LineageTimeline.tsx`: a small four-point timeline
  (Created → Registered → Last updated → Renewal due) with a registration-
  status badge, rendered in a bordered card in the details panel.
- `web/src/components/DetailsPanel.tsx`: each identifier row is now
  expandable (▸/▾, click to toggle) to reveal its own provenance - source
  file, snapshot date, ingestion timestamp, confidence - without cluttering
  the compact table when collapsed.

### Verify

```bash
uv run pytest                                        # 147 passing (fixtures updated for the new columns)
make build-entities                                   # rebuild entities.parquet + entity_identifiers.parquet
uv run python -m er.cli.entity --lei 549300TITGLG7BXCGB39   # shows the new Lineage line
curl "http://localhost:8000/api/entity/549300TITGLG7BXCGB39" | python3 -m json.tool | head -20
```

Confirmed live with real screenshots: the details panel shows a lineage
timeline with real dates (Created 1 Oct 2019, Registered 22 Jan 2020, Last
updated 23 Jul 2026, Renewal due 12 Aug 2027, status ISSUED) and clicking the
CIK identifier row expands to show its source file
(`sec_13f_filings.parquet`), snapshot date, ingestion timestamp, and
confidence (`AUTO_MATCH`).

---

## Phase 17: design pass - one type scale, one colour system, no emoji

The UI worked but looked assembled rather than designed: three font stacks in
play (a hardcoded `Arial` on `body` was silently overriding the loaded Inter),
emoji used as icons, ad-hoc badge colours per component, and panels whose
frames began at different y-positions.

### What changed

- **Type**: `Inter` + `JetBrains_Mono` loaded via `next/font/google` as CSS
  variables and mapped through Tailwind v4 `@theme`. Mono is reserved for
  identifiers. A `.tabular` utility (`font-variant-numeric: tabular-nums`)
  applies to every figure read down a column - dates, counts, dollar amounts,
  LEIs.
- **Colour**: one accent (indigo), two *semantic* hues - emerald for upward /
  parent, violet for downward / subsidiary / fund - slate for structure, amber
  and rose for caveats and errors.
- **Icons**: `lucide-react` replaces every emoji in the UI.
- **`components/ui.tsx`** (new): `SectionLabel`, `Badge` (seven named
  variants), `Mono`, `Field`/`FieldGrid`. Each component previously spelled
  these out inline with slightly different sizes and colours; they are now
  declared once.

### Alignment fixes found by screenshotting, not by reading code

Each of these was invisible in the source and obvious in a real 1440x900
render (headless Chrome driving the running dev server):

- The tree label sat *outside* its card while the details title sat *inside*,
  so the two panes started on different baselines. Both are now cards with an
  identical `h-11` titled header bar.
- The header search bar was centred within its flex slot, not within the
  viewport. Fixed with `grid-cols-[1fr_auto_1fr]`.
- The search-type segmented control stacked *under* the compact field, making
  the app header two bars tall. It now sits inline beside the field at a
  matching 40px height, and only stacks in the landing page's hero size.
- Results rows were two-line blocks with a lone chevron ~1,800px to the right.
  They are now 44px rows with aligned name / jurisdiction / LEI columns, which
  is what makes ten near-identical Point72 entities comparable at a glance.
- The raw retrieval score ("40", identical on every row) was removed: an
  unnormalised BM25 value means nothing to a reader and the list is already
  sorted by it.
- With results on screen but nothing selected, two empty panes filled most of
  the viewport. The results now take the full stage until an entity is picked,
  then collapse to the capped strip.
- The lineage card duplicated the section heading and floated its status badge
  alone on its own row; the heading was dropped and the badge moved into the
  section header via a widened `hint?: React.ReactNode` slot.

### Verify

```bash
cd web && npx tsc --noEmit && npm run build   # both clean
make api && cd web && npm run dev             # then compare against the screens above
```

---

## Phase 18: colour tokens, readable contrast, and a "why this matters" drawer

Phase 17 fixed alignment and typography but left the palette thin: labels were
`slate-400` and identifiers `slate-300`, which measure ~2.5:1 and ~1.9:1 on
white. The UI read as dim on a laptop screen, and the fixed 400px details pane
stranded a lot of whitespace on a 1920 display.

### Named tokens instead of per-component slates

`globals.css` now declares the palette once, as Tailwind v4 `@theme` tokens,
and every component references the role rather than a shade:

- Text is a four-step ramp - `ink` (16.8:1, names and values), `ink-muted`
  (10.9:1, body), `ink-subtle` (6.0:1, labels/captions/identifiers),
  `ink-faint` (2.6:1, **decoration only** - rules, inactive dots, never text).
- Ground: `canvas`, `surface`, `line`, `line-soft`.
- Meaning: `accent`/`accent-strong`/`accent-soft`, plus `upward` (parent) and
  `downward` (subsidiary/fund), deepened from 500 to 700-weight hues so they
  hold up against white.

Badge variants moved to 700/800 text on a 50 fill with a 300 ring - the old
600-on-50 combination was legible in isolation and washed out in a row of
them. A `grep` for `slate-300|slate-400` in `web/src` now returns one
deliberate hit (the neutral badge).

### Layout

- The details pane is fluid: `w-[clamp(25rem,30vw,34rem)]` instead of a fixed
  `400px`, so a wide screen gives it real room instead of leaving the tree
  pane mostly empty.

### "Why this matters" drawer (`WhyItMatters.tsx`)

A floating trigger on the landing page opens a right-hand drawer arguing the
product's actual thesis - an agent is only as reliable as the entity layer
underneath it - across five topics: entity resolution, identifiers, hierarchy,
lineage, provenance. Each carries a concrete example, and the two that make
quantitative claims cite measured results from `experiments/` (Recall@20
74.9% -> 88.35%; master/feeder dangerous-failure 26.1% -> 0.0%, precision
53.9% -> 100%) rather than adjectives. Escape and backdrop-click close it, body
scroll is locked while open, and focus returns to the trigger.

### Verify

```bash
cd web && npx tsc --noEmit && npm run build   # both clean
```

---

## Phase 19: column alignment, a scroll affordance, and non-generic loading

Four defects, all reported from screenshots of the running app.

### Columns that only looked aligned

`ResultsList` rendered the decision badge conditionally. Because the name cell
is `flex-1` and absorbs the slack, the trailing cells are laid out from the
right - so a single row carrying an `AUTO MATCH` badge pushed *its own*
jurisdiction and LEI left by the badge's width while every other row's stayed
put. The table lined up everywhere except the one row a reader looks at first.

Fixed by giving each trailing cell a fixed width declared once at the top of
the file (`COL_JURISDICTION`, `COL_IDENTIFIER`, `COL_DECISION`) and rendering
every cell on every row - the decision cell is simply empty when there is no
decision. Unresolved CIK rows now fill the same two cells rather than
substituting one wide span.

### A clipped list that looked like a bug

The capped results strip had only a gradient fade, which does not actually
tell you there is more below. New `ScrollPane` component: caps the height,
tracks scroll position with a `ResizeObserver` (content height changes without
firing a scroll event when results arrive), and shows a control straddling the
pane's bottom edge - out of the rows' way - that scrolls a page and disappears
at the end.

### Loading states that looked machine-generated

The previous skeletons were the default treatment: randomly-sized grey bars
pulsing in unison. Replaced with two rules:

1. **Motion lives in one place** - a 2px indeterminate line at the top of the
   pane (`.progress-line`). Placeholders never animate.
2. **Placeholders reproduce the real geometry** - the same 44px rows, the same
   column widths as `ResultsList`, the same tree indent depths *with the indent
   guides actually drawn*, and a details skeleton that mirrors its own panel
   (header block, six-row field grid, four-point lineage card, identifier
   rows). Widths are a fixed pattern, not randomised: randomised widths are
   what read as a shimmer rather than as a table.

### Typography

Inter + JetBrains Mono replaced with **IBM Plex Sans + IBM Plex Mono** - one
superfamily drawn together with shared vertical metrics, designed for dense
technical interfaces, rather than two independently-chosen defaults.

### Also fixed

The details pane showed its "select an entity" empty state for the whole
duration of the tree fetch, even though `loadTree` loads the root entity
immediately afterwards. It now treats `treeLoading` as loading too.

### Verify

```bash
cd web && npx tsc --noEmit && npm run build   # both clean
```

## Phase 20: addressed facts, a validated 13F, and a typed multi-source graph

Prompted by a teardown of Kepler (a financial-research agent built on "the
model never emits a number") and an outside review of this agent against it.
The review said citations were reconstructed after writing. That was not quite
right: every tool already returned an `Evidence` record at retrieval time. The
real gap was that a receipt covered a whole lookup, not an individual value or
a place in a source.

### Facts and the submission gate

Tools now return `Fact`s alongside `Evidence`: a value, unit and as-of date
plus an address (source, document, locator, field). The model writes
`{{f:fact_id}}` instead of a number, and `er.agent.facts.render_answer`
rejects any literal number left in the prose, any unknown fact id, and any
fact whose evidence wasn't cited. Before rendering, the orchestrator re-runs
the tool call behind every used fact and rejects the answer if the fact no
longer resolves or its value changed. Fact ids hash the address and value,
not the evidence id, so the re-run is comparable.

Computed values come from `er.knowledge.formulas` (`sum`, `difference`,
`percent_change`). `get_position_history` returns a manager's long position in
a CUSIP per 13F period, each total derived from the information-table rows and
each change derived from two totals. A `Derivation` records the formula and
input fact ids, and the evidence card labels it a calculation and lists the
formulas.

### 13F, validated before it is stored

The summary page was in the bulk archive but never read. It is now. Of 9,846
filings, 402 fail reconciliation (174 row-count, 293 value-total mismatches)
and go to `sec_13f_quarantine.parquet` instead of the holdings. Amendments
follow SEC semantics: 293 restatements replace their original, 104 "new
holdings" amendments append to it. 3,822,885 raw rows become 3,499,768
effective holdings. Value scale follows the filing date, not the period, and
put/call rows are kept out of positions and top holdings, which now group by
CUSIP rather than issuer name.

Filers still reporting in thousands after the 2023 switch are flagged, not
rescaled: 299 of 8,477 comparable filings (experiments/007).

### Sources and the graph

Codex added SEC submissions, Series/Class, Forms 3/4/5, N-PORT, OpenFIGI,
GLEIF BIC/MIC/OpenCorporates mappings, Form ADV brochures (page-addressed PDF
text, served by `/api/sources/sec-adv/{file}` so a citation opens the page)
and Companies House/PSC. This phase added:

- **Schedule 13D/G** (`er.datasources.sec_13dg`): structured XML from EDGAR,
  one row per reporting person. 13G cover pages name people without CIKs, so
  a CIK is inferred only when the filing has a single reporting person. Fetches
  run on six threads under one shared rate limit (8 req/s), retry on
  connection resets, and cache every document, so a stopped run resumes
  cheaply. The first version waited the full interval and then the request
  latency, managing about 2 filings a second. 2026 Q2: 9,348 filings, 21,709
  reporting-person rows (8,226 with a CIK), 7,057 beneficial-owner edges and
  4,529 CUSIP-to-issuer edges.
- **FFIEC NIC** (`er.datasources.ffiec_nic`): RSSD institutions, control
  relationships and transformations. The site refuses scripted downloads, so
  it reads zips dropped into `data/raw/ffiec_nic`.
- **GLEIF successor LEIs**: 34,685 entities now point at the LEI that replaced
  them.

`er.knowledge.build` unions them into typed nodes, edges, identifiers and
facts: 3.58M nodes, 2.83M edges, 3.48M identifiers and 3.83M facts, built in
about 4 seconds. Relationship types stay distinct: a GLEIF accounting parent, NIC bank
control, a 13D/G beneficial owner, PSC significant control and a 13F holding
are different claims, and the agent prompt now says so.

### Match decisions are citable

The crosswalk now keeps each decision's runner-up, per-feature contributions
and matching config fingerprint (`config_fingerprint`), and the graph turns
them into facts. Human reviews in `data/reviews/match_reviews.csv` are
separate dated records: the latest outcome per pair adds or removes the link,
and the automated decision is never edited.

Re-running the crosswalk changed 8 of 10,672 decisions, all AUTO_MATCH to
REVIEW with the same LEI. The previous file predated experiment 005's
fund-structure guard. Their reason text is misleading, though: it says the
score missed the auto-match threshold when the guard fired.

### Hard-path agent evaluation

`make evaluate-agent` runs `config/agent_eval_cases.yaml` through the live
agent and checks that each answer submitted, every citation resolves, every
used fact is cited, the expected facts and sources were used, and (with
`--baseline`) no value moved since an earlier run. Jev's verdict sits next to
it, and disagreements are flagged in the JUnit output.

Its first runs found three real problems, none of which the unit tests could:

- The top-holdings query, regrouped by CUSIP in this phase, used a bare
  `value` alias that DuckDB rejects in that position. `get_entity_profile`
  failed for every 13F filer.
- The gate rejected grounded text: a CIK, the CUSIP from the question, and
  report dates like `31-MAR-2026`, whose digits the number scan picked out.
  An identifier or date copied whole (at least 4 characters) from a cited
  fact's value or as-of date, or a token echoed from the question, is now
  stripped before the scan. Anything else numeric still needs a placeholder.
  Models also dropped the `f_` prefix from fact ids, which is now restored
  when it names exactly one fact.
- A model wrote `{{f:f_...}}`, which matched neither the placeholder pattern
  nor the number scan, so it reached the user verbatim. Malformed
  placeholders are now a rejection.

After these fixes, four cases pass 25 of 25 hard checks (including baseline
consistency) and Jev verifies all four.

### In the web UI

The first pass stopped at the API and agent. A check of the running app showed
how little reached a person: `page.tsx` had been restyled to a four-field
profile card, and the richer `DetailsPanel` was no longer mounted. The entity
profile (`web/src/components/EntityProfile.tsx`) now carries identifiers and
linked records, each link decision with its features, runner-up, config and
reviews (with a Confirm / Reject form), ownership and control grouped by kind
of claim, and 13F holdings with quarantine and scale warnings and a per-holding
position history whose formulas unfold to the filed rows. `EntityDetail` gained
`connections` and `match_decisions` (`er.entity.connections`,
`er.entity.resolution`), plus `GET /api/positions/{cik}/{cusip}` and
`POST /api/reviews`.

Agent answers now return the facts they used, plus the derivations and inputs
behind any computed fact. Each source card lists its values with their
addresses. Running it showed raw numbers in answers ("1209344041", a
percentage without "%"): the gate substituted `str(value)`, and the model is
not allowed to format numbers itself. Placeholders now render with their unit
("$1,209,344,041", "0.35%"), absorbing a `$` or `%` the model wrote next to
one.

### Not done

Bitemporal snapshots (facts carry a snapshot date, but older snapshots are not
kept), a split-pane source viewer, rendering the original EDGAR or GLEIF view
of a record, the N-PORT coverage study, Exhibit 21, Wikidata, and per-entity
fan-out. The tree view, details panel and Ask drawer are still unmounted.

## Phase 21: the API reads OpenSearch, not Parquet

The deployment target is a remote API with no local data, but every runtime
read except name search went to Parquet through DuckDB: profiles, GLEIF
hierarchy, 13F activity, connections, decisions, positions, 13D/G, and the
review CSV. Only GLEIF names had ever been in OpenSearch.

Parquet stays the build-time system of record. A new `make publish`
(`er.serving.publish`) shapes it into serving indexes, each built under a
dated name and swapped in behind an alias only once loaded. Runtime code reads
them through `er.serving.store.Store`. That contract is deliberately small
(get, multi-get, exact-match find with an OR group, missing fields, sort,
collapse, put), so the `MemoryStore` the tests use is an honest stand-in for
`OpenSearchStore`.

Documents are shaped per read, not per table. One entity document carries
identity, lineage, identifiers, GLEIF exceptions, match decisions and
cross-source connections, so a profile is two document reads plus the
hierarchy. The knowledge graph's facts, nodes and identifiers tables (about
600 MB of Parquet) aren't published: connections are precomputed per LEI at
publish time.

Two limits found along the way. One issuer carries 656,902 identifiers
(ISINs), too large for one document and already unusable in the UI, so
documents keep 200 per type plus the true total. OpenSearch caps a query at
10,000 hits, and the largest relationship fan-out is 5,497 (positions 1,739
rows), so plain queries are enough.

Reviews are the one thing the API writes, so OpenSearch is their system of
record. The index is created on first write with strings mapped as keywords:
dynamic mapping would make the LEI an analysed text field, and exact lookups
would silently miss. `make pull-reviews` copies reviews down for
`build-knowledge-graph`.

Still local: Form ADV brochure search (no data loaded yet; PDFs belong in
object storage, not OpenSearch).

Checked live after the full publish (3.4M entity documents, 3.5M holdings,
666k relationships, 2.2 GB of the cluster's 19.5 GB). Search answers in about
0.2s, a profile in 1.4s, positions in 0.2s. The default tree (depth 2, 30
expansions) was 25% slower than the Parquet version: each expansion read the
same entity document twice, once for its name and once for its exceptions.
One read now covers both, bringing the tree back to about 2.4s, level with
DuckDB.

The agent runs also surfaced two problems with the fact gate, neither caused
by the store. The gate rejected a holding's CUSIP as a bare number because only
the holding's value was a fact. The profile tool now emits the CUSIP as a fact
at the same address. And a model still calling tools on its last turn ran out
the budget with evidence in hand. In one run it spent three calls on the empty
ADV index. The last turn now forces `submit_answer`.

## Phase 22: loading the remaining sources, and N-PORT on fund profiles

Six sources had ingest code and unit tests but no data: nobody had downloaded
their raw files, so their Parquet, graph edges and serving documents didn't
exist and the agent could not see them. Loading them for real found two
ingests that could never have worked on the files the publishers ship.

Form ADV looked for `*mapping*.csv` beside the brochure zips. SEC puts the
mapping inside each monthly zip and names it `ADV_Brochure_Mapping_...csv`,
capital M, which a case-sensitive glob misses; it also read only the newest
mapping, so a second month's PDFs would have been skipped. Mappings are now
read from inside every zip, case-insensitively, deduplicated by PDF name.

Companies House globbed `*psc*` for the PSC snapshot, which matches the
multi-part `psc-snapshot-..._1of32.zip` files but not the single
`persons-with-significant-control-snapshot-....zip`. With no match it wrote
zero significant-control rows and reported success. Both names are accepted
now, and a missing snapshot is an error.

N-PORT reports are keyed by the fund's own series LEI (13,537 of 13,548 are in
GLEIF), so a fund's profile now carries its latest report the way a manager's
carries 13F: net assets, holding count and the ten largest holdings by USD
value, published as `er_nport_funds` and emitted by the profile tool as
addressed facts. An amendment replaces its original for the same report date.
`CURRENCY_VALUE` in the SEC data set is the USD value: it equals percent of
net assets times net assets to the cent, including for EUR, JPY and INR
holdings.

Loaded: SEC submissions (993k CIKs), N-PORT 2026 Q2 (14.4k fund reports, 5.3M
holdings), GLEIF mappings (768k OpenCorporates, 39k BIC, 1k MIC), Form ADV
December 2024 (996 brochures, 28.6k pages, no extraction errors) and Companies
House (5.7M companies, 16.0M PSC records). The graph gained 16.0M
significant-control edges and 101.8k UK companies linked to an LEI by
registration number; N-PORT's own registrant and series LEIs add 14.9k CIK and
series links, four times what the 13F crosswalk resolves, so more 13D/G and
insider records reach a profile. OpenFIGI runs at 10 CUSIPs a request without
an API key (about 3 hours for 33.7k CUSIPs, cached per batch). FFIEC NIC puts a
CAPTCHA in front of its downloads, so it still needs a manual download.

Live agent runs on the new data surfaced three more gaps. The ADV search tool
is an exact-phrase match - so a citation can point at exact characters - but
its description didn't say so, and the model sent keyword lists that never
matched; when it did hit a "Fees and Compensation" heading, the snippet ended
220 characters later, before the fees. The description now asks for a literal
phrase, and a snippet carries 900 characters after the match. A brochure's
CRD number, brochure ID and page were not facts, so the gate rejected them like
the CUSIP before; they are now. And a model that researched through its last
turn, then had its forced submission rejected, failed with evidence in hand:
one extra turn now exists, used only to resubmit after a rejection.

The graph's other relationships - PSC significant control, FFIEC bank
control, insider roles, successions, and the records linked to an LEI - were on
the web profile but out of the agent's reach: no tool read them. A
`get_entity_connections` tool now returns them one group per kind of claim,
with start and end dates and control percentages as facts, so a ceased
controller can be cited as ceased. Publish lists current connections before
ended ones within each capped group (25 per group), so a capped list that
already reaches an ended entry holds every current one, and the tool says so:
AHL Partners LLP has 45 PSC records, of which the 13 current all fit.
