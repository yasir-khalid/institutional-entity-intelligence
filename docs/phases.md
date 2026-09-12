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

Real run against 10,672 unique 13F filers (one quarterly bulk file, 2026-Q1):
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
same phase to make experiment 003 measurable) surfaced an adjacent, more
concerning finding on the existing GLEIF benchmark: the `fund_number` confusable-
pair slice has **0% AUTO_MATCH precision** in the 6,000-row sample (37 confident
AUTO_MATCHes, all wrong) - a bigger dangerous-failure source than the
master/feeder case this phase fixed, and a clear next target. See
[`experiments/003`](../experiments/003-fix-master-feeder-conflict-false-positive.md)
for the full numbers.
