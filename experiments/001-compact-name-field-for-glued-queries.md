# 001: Compact (space-stripped) keyword field for glued/no-space name queries

**Status:** VALIDATED
**Date:** 2026-09-12
**Targets:** Medium-tier retrieval recall (~55% baseline)

## Hypothesis

Some real-world query names arrive with no spaces at all (e.g. "avaloncorrectionalservices",
"fnbbank" - concatenations that show up from upstream systems that strip whitespace, or
from users pasting compacted identifiers). Under OpenSearch's standard analyzer, a glued
query tokenizes to exactly one token, which has zero term overlap with a properly-spaced
indexed name ("avalon correctional services" -> 3 tokens). Hypothesis: this is a pure
retrieval-layer failure (candidate pool is empty), not a scoring problem, and adding a
space-stripped exact-match field will fix it without touching the scoring layer at all.

## Method

Diagnosed first, before writing any fix, by calling `search_candidates()` directly against
the live index for known glued-name cases and inspecting `pool_size`:

```python
cases = [('avaloncorrectionalservices', '549300QRFDJ5BZFMXU58'),
          ('wlg', '254900TZ0KR0OPXYU645'),
          ('fnbbank', '254900UEITST3NEK8Y27')]
for name, expected in cases:
    results = search_candidates(client, cfg, name, size=1000)
    ...
```

Result confirmed the hypothesis directly: `'avaloncorrectionalservices': pool_size=0`,
`'fnbbank': pool_size=0` - zero candidates retrieved, not merely mis-ranked. ("wlg" - a
genuinely short/ambiguous 3-letter query, not a glued-name case - retrieved 14 candidates
and is a separate, unrelated failure mode.)

Fix: added `legal_name_compact` (keyword, space-stripped `legal_name_norm`) to the
OpenSearch mapping (`src/er/indexing/opensearch_index.py`) and a matching exact-`term`
`should` clause in the candidate query (`src/er/retrieval/candidates.py`), boost 4 -
between the `aliases_norm` (2) and `legal_name_core` (3) clauses, since an exact compact
match is a strong signal but shouldn't dominate over a real multi-token name match.
Required `--recreate` (drop+recreate index) since the index's `dynamic: strict` mapping
rejects new fields on existing documents - reindexed all ~3.4M GLEIF entities.

Measured via `make evaluate` (`uv run python -m er.evaluation.run_benchmark`) before and
after the reindex completed.

## Result

Direct retrieval check, before fix (against live index, pre-reindex):
```
avaloncorrectionalservices: found=False rank=None pool_size=0
fnbbank:                    found=False rank=None pool_size=0
```

After the fix + reindex, the same direct retrieval check on both cases returns the
correct entity in the pool (verified live), and unit test
`test_compact_name_clause_matches_space_stripped_query` (tests/test_query_building.py)
locks in the query-building behavior. Full suite: 122 passed (0 regressions across
existing country/scoring/decision/matcher tests).

Full-benchmark `make evaluate` (6,000 rows), before (Phase 5 final baseline) vs. after
this fix + reindex:

| | before (Phase 5 final) | after (this experiment) |
|---|---|---|
| Recall@20 (overall) | 74.9% | **88.35%** |
| Recall@20 (confusable pairs) | 98.1% | 98.3% |
| AUTO_MATCH precision (overall) | 96.3% | 96.3% |
| Dangerous-failure rate (confusable pairs) | 6.1% | 6.1% |

The full post-fix report also now carries `failure_breakdown` (experiment 002):
`{"success": 0.52, "retrieval_miss": 0.1152, "wrong_auto_match": 0.02,
"under_confident_top1": 0.2343, "correctly_deferred": 0.1105}` overall - a
`retrieval_miss` rate of 11.5% remaining (down from what would have been higher
pre-fix) shows there is still real retrieval-layer room to improve, but the
compact-field fix's ~13.4-point Recall@20 jump confirms it closed a large, real gap
without moving AUTO_MATCH precision or the confusable-pair dangerous-failure rate at
all - exactly the "retrieval-completeness fix, isolated from scoring" outcome
predicted below.

## Verdict

Kept (VALIDATED). This is a retrieval-completeness fix, not a scoring change - it cannot
make a correct decision worse, only make previously-invisible correct candidates visible
to the existing (unchanged) scoring layer. Risk is limited to: (a) a compact match
firing on an unrelated entity that happens to share a compacted form - mitigated by
using `term` (exact string equality on the full compacted name, not a substring/prefix
match) rather than any fuzzy variant; (b) increased index size/reindex time for one
extra keyword field - negligible relative to the existing per-entity payload.

If a future glued-query case still fails after this fix, the next thing to try is
extending the same compact-match idea to `aliases_compact` (aliases aren't currently
mirrored into a compact form), not a different technique.
