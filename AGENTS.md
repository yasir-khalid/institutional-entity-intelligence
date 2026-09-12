# AGENTS.md

Guidance for any agent (or human) working in this repository. Read this before
making changes — it explains where things live and, more importantly, *why* the
codebase is shaped the way it is, so a "helpful" refactor doesn't undo a
deliberate decision.

## Repo map

```
src/er/
├── datasources/<source>/   # one folder per data source (gleif, sec_13f, ...) -
│                             owns its OWN raw-file parsing, pydantic models,
│                             pyarrow schema, and ingest.py end to end.
│   └── common/             # ONLY truly source-agnostic helpers
│                             (BatchedParquetWriter, xml_utils) - no source-
│                             specific field/schema knowledge belongs here.
├── normalisation/           # pure string/address/country normalization -
│                             names.py, addresses.py, countries.py. No I/O.
├── indexing/                 # OpenSearch index mapping + bulk load
│                             (opensearch_index.py) - candidate retrieval only,
│                             never the system of record.
├── retrieval/                # candidates.py - builds the OpenSearch query,
│                             search_candidates(). Retrieval-relevance score
│                             only, not a match decision.
├── matching/                  # er.match: features.py (pure comparison signals)
│                             -> scoring.py (config-driven weighted sum) ->
│                             decisions.py (score+gap -> AUTO_MATCH/REVIEW/
│                             UNMATCHED) -> matcher.py (the only file here that
│                             calls OpenSearch).
├── family/                    # er.family: brand/family discovery - a
│                             DIFFERENT operation from matching (a set of
│                             entities, not one winner). brand.py is pure.
├── graph/                     # er.hierarchy: relationship traversal over
│                             GLEIF's relationship/exception tables.
├── crosswalk/                  # resolve ANOTHER source's records to a GLEIF
│                             LEI, by calling er.matching.matcher.match()
│                             unchanged - never reimplement matching per source.
├── entity/                     # canonical entity layer - entities.parquet (one
│                             row per entity) + entity_identifiers.parquet (every
│                             identifier any source has attached). sources.py is
│                             THE file to touch when wiring a new source's
│                             identifiers in - see "Adding a new data source"
│                             below. profile.py assembles the single
│                             request-level EntityProfile (identity + IDs +
│                             GLEIF relationships + SEC 13F activity) that
│                             er.entity's CLI renders.
├── benchmark/                  # auto-generates evaluation_pairs.parquet from
│                             the ISIN<->LEI bridge + intra-GLEIF confusable
│                             pairs. No manual labeling.
├── evaluation/                 # runs the matcher against the benchmark,
│                             reports Recall@K/MRR/precision + failure_breakdown
│                             (metrics.py is pure; run_benchmark.py is the only
│                             file that hits live OpenSearch here).
└── config.py                   # every tunable (weights, penalties, thresholds,
                              batch sizes, index settings) lives in
                              config/dev.yaml, loaded through this - a retune
                              should be a config edit, not a code change.

experiments/   # proof-backed retrieval/scoring experiments - see below.
docs/          # architecture.md (request-flow detail), phases.md (full build
               # history, one section per phase, with real bugs and numbers).
tests/         # mirrors src/er/ - pure functions get synthetic-fixture unit
               # tests; nothing here touches live OpenSearch (see er.evaluation
               # for that).
```

## Adding a new data source, end to end

This is the full recipe for wiring a new source (SEC Form ADV, FCA, Companies
House, ...) into the product - every step is additive, nothing here requires
touching another source's code or the canonical entity layer's internals:

1. **Ingest** (`src/er/datasources/<source>/`): write `models.py` (pydantic
   raw->cleaned boundary), `schema.py` (pyarrow schema), `ingest.py` (parser ->
   `BatchedParquetWriter`). Copy the shape of `gleif/` (XML) or `sec_13f/`
   (TSV-in-zip) depending on the source's format. Add a `Config` class in
   `config.py` + a section in `config/dev.yaml` + a `make ingest-<source>`
   target.
2. **Crosswalk** (`src/er/crosswalk/<source>_to_gleif.py`): resolve each unique
   record from the new source to a GLEIF LEI by calling
   `er.matching.matcher.match()` unchanged - do not write new matching logic.
   Persist `source_record_id, resolved_lei, decision, score` (see
   `sec_13f_to_gleif.py` for the pattern). Add a `make crosswalk-<source>`
   target.
3. **Attach identifiers** (`src/er/entity/sources.py`): write ONE function
   returning a SQL SELECT over your crosswalk's output, aliased to
   `entity_id, identifier_type, identifier_value, confidence, source`, filtered
   to non-UNMATCHED rows. Append it to `IDENTIFIER_SOURCES`. That's the entire
   integration - `er.entity.build` and `er.entity`'s CLI need no other changes.
4. **(Optional) Attach richer activity data to `EntityProfile`**: if the source
   has its own "latest observation" concept worth showing on `er.entity`'s
   profile (like `Sec13FActivity`), add a model to `src/er/entity/models.py`
   and a loader function to `src/er/entity/profile.py` alongside
   `_load_sec_13f_activity` - guard it the same way (return `None` when the
   source's data isn't available for this entity, never raise).
5. `make build-entities` to rebuild the canonical layer, then
   `uv run python -m er.entity --lei ...` to see the new source's data appear.

## Design decisions (and why)

**Parquet is the system of record; OpenSearch is retrieval-only.** Never write
code that treats an OpenSearch document as authoritative, or that skips writing
something to Parquet because "it's already in the index." If OpenSearch is
dropped and rebuilt from Parquet, nothing should be lost.

**Each data source owns its ETL completely, in its own folder.** A source's
`models.py`/`schema.py`/`ingest.py` should never import another source's
internals. The only shared code is genuinely source-agnostic
(`datasources/common/`). When adding a new source, copy the shape of an
existing one (`gleif/` for an XML source, `sec_13f/` for a TSV-in-zip source)
rather than inventing a new pattern.

**Raw → cleaned is an enforced pydantic boundary, not decoration.** Every row
goes through its source's own pydantic model (`.model_dump()`) before being
written to Parquet. A malformed record should fail loudly here, not reach the
canonical store silently malformed. Do not bypass this by writing a plain dict
straight to a `BatchedParquetWriter`.

**Scoring is deterministic and config-driven, not ML.** Every point in a match
score is traceable to one named weight/penalty in `config/dev.yaml`
(`MatchingWeights`/`MatchingPenalties` in `config.py`). Retuning behavior should
be a config edit. If you're tempted to add a learned model here, that's a much
bigger architectural conversation, not a drop-in change to `scoring.py`.

**No decorator-based "magic."** A decorator DSL for field parsing/mapping was
explicitly proposed and rejected (see `docs/phases.md` Phase 9) — it hides the
actual field logic behind indirection and makes debugging a bad value harder.
Prefer plain, named, composable functions (see `datasources/gleif/fields.py` for
the pattern) even when a decorator would save a few lines.

**A `None` feature return means "no signal," not "false."** In
`matching/features.py`, most comparison functions return `None` when the query
lacks that field (e.g. no postcode given), distinct from `False` (compared and
didn't match). This distinction matters — conflate them and you silently
penalize candidates for information the query never provided. (This exact bug
existed for `master_conflict`/`feeder_conflict` — booleans, not nullable — until
experiment 003 fixed it; when adding a new boolean comparison feature, make sure
"no assertion" and "explicit false" are actually distinguishable before writing
a conflict check.)

**Country/name matching never hard-excludes by default.** `search_candidates`'s
soft country mode boosts/penalizes via `boosting`, never `filter` — a hard
filter silently drops the true entity whenever a source field is merely wrong,
which is the common case for real messy data. `--country-mode strict` exists as
an explicit opt-in for callers who trust the field completely; don't make hard
filtering the default anywhere else either.

**A tie is not a wrong answer — it's the correct answer.** `decide()`'s
gap-to-runner-up check exists because a lone high score is trustworthy but two
close high scores mean the query genuinely doesn't disambiguate. Don't "fix" a
low `AUTO_MATCH` coverage rate by shrinking the gap threshold without checking
`dangerous_failure_rate_confusable_pairs` and `failure_breakdown` in the same
`make evaluate` run — a wrong entity picked confidently is the single worst
failure mode this project optimizes against, worse than no match at all.

**A benchmark hard-negative must be checked for third-party collisions.** Any
strategy that mutates a real name into an adversarial query (stripping tokens,
abbreviating) can accidentally produce a string that is also the exact, correct
legal name of some unrelated third entity - in which case the matcher answering
"correctly" per the literal query text gets scored as a dangerous failure
against the wrong label (see `experiments/004` - this is exactly what looked
like a severe `fund_number` scoring bug until direct reproduction showed it was
a benchmark labeling artifact). Any new query-mutation strategy added to
`er.benchmark.generate` needs the same collision guard
(`generate_hard_negatives()`'s `NOT EXISTS` check) before its dangerous-failure
numbers can be trusted.

**SEC 13F is "latest reported holdings," never "holdings" or "portfolio"
unqualified.** Form 13F covers only certain reportable US equity securities as
of one quarterly date - it excludes shorts, derivatives, non-US securities,
private investments, and positions below reporting thresholds. Any UI/CLI text
showing 13F data (see `er.entity`'s renderer) must carry this caveat explicitly;
don't let it read like a complete picture of an institution's holdings.

## Working on retrieval/scoring: use `experiments/`

Any change to retrieval or scoring behavior (a new field, a reweighted feature,
a new conflict check) should be recorded as `experiments/NNN-slug.md`: a
hypothesis, what was actually changed, the exact `make evaluate` (or targeted
reproduction) command used to measure it, before/after numbers verbatim, and a
verdict (VALIDATED/INVALIDATED/INCONCLUSIVE). Diagnose with a direct, minimal
reproduction *before* writing a fix (e.g. call `search_candidates()` directly to
confirm a retrieval-layer miss before touching scoring code) — see
`experiments/001-compact-name-field-for-glued-queries.md` for the pattern. This
exists so a technique that didn't help isn't re-tried blind months later, and so
a change is never "it seemed like it should help" without a number attached.

## Testing expectations

- `make test` (`uv run pytest`) must pass with zero regressions before any
  change is considered done. It's fast (~5s) and needs no live services.
- Any change touching `matching/`, `retrieval/`, or `indexing/` should also be
  checked against `make evaluate` when a live OpenSearch index reflecting the
  change is available — unit tests alone don't catch a live-index-shape problem
  (e.g. a new mapping field needing `--recreate`).
- When adding a config field to `AppConfig` (`config.py`), update every test
  fixture that constructs `AppConfig` directly (currently `tests/test_graph.py`,
  `tests/test_benchmark.py`) or they'll fail with a pydantic "field required"
  error.

## Standing project conventions

- End-of-task: update `README.md`'s Quickstart if commands changed, and state
  the exact test commands in your final summary to the user.
- Never commit `.env` or credentials; `data/` and `.env` are gitignored.
- Prefer DuckDB over pyarrow for joins/aggregations/analytical queries directly
  on Parquet; pyarrow is for streaming Parquet writing/reading only.
- Use `rich` for CLI output (tables/panels), consistent with `er.match`,
  `er.family`, `er.hierarchy`.
