# 002: Categorize evaluation failures instead of only reporting aggregate precision/recall

**Status:** VALIDATED
**Date:** 2026-09-12
**Targets:** Failure-analysis categorization

## Hypothesis

`dangerous_failure_rate_confusable_pairs` and the recall/precision numbers already in
`er.evaluation.metrics` tell you *that* something is wrong on some slice of the benchmark,
but not *what kind* of wrong - a retrieval-layer miss (the correct entity never reached the
candidate pool) and a scoring/threshold problem (it was retrieved and ranked first, but the
matcher still wouldn't commit) require completely different fixes, and conflating them
under one "not AUTO_MATCH" bucket makes it easy to work on the wrong layer. Hypothesis: a
row-level categorization function, applied uniformly across every row (not just
confusable_pair), makes the evaluation report self-diagnosing.

## Method

Added `categorize(row) -> str` and `failure_breakdown(rows) -> dict[str, float]` to
`src/er/evaluation/metrics.py`, using only fields already present on `RowResult`
(`decision`, `chosen_lei`, `expected_lei`, `candidate_leis`) - no new data collection
needed. Five mutually-exclusive categories:

- `success` - AUTO_MATCH and correct.
- `wrong_auto_match` - AUTO_MATCH but to the wrong entity (the costliest failure mode;
  generalizes `dangerous_failure_rate_confusable_pairs` to every case type, not just
  confusable pairs).
- `retrieval_miss` - expected entity never in the candidate pool at all (this is exactly
  the failure mode experiment 001 targeted and fixed for glued-name queries).
- `under_confident_top1` - expected entity retrieved AND ranked first, but the matcher
  didn't AUTO_MATCH - a scoring-margin/threshold issue, not a retrieval issue.
- `correctly_deferred` - expected entity retrieved but not ranked first, and the matcher
  correctly declined to AUTO_MATCH - not a bug, but still requires human review, so it's
  tracked distinctly from `success` rather than silently folded into "not a failure."

Wired into `summarize()` so every existing report slice (`overall`, `by_difficulty`,
`by_case_type`) gets a `failure_breakdown` for free with no changes to `run_benchmark.py`.

Measured via new unit tests (`tests/test_evaluation_metrics.py`): one test per category
plus a "breakdown sums to 1.0" invariant test.

## Result

```
16 passed (tests/test_evaluation_metrics.py) - up from 9 before this change.
```

`failure_breakdown` now appears in every `summarize()` output, e.g. for a mixed batch of
4 rows (1 success, 1 wrong_auto_match, 1 retrieval_miss, 1 under_confident_top1):
`{"success": 0.25, "wrong_auto_match": 0.25, "retrieval_miss": 0.25, "under_confident_top1": 0.25, "correctly_deferred": 0.0}`.

Full-benchmark `evaluation_report.json` (6,000-row sample, post experiment-001 reindex):

- **Overall**: `{"success": 0.52, "retrieval_miss": 0.1152, "wrong_auto_match": 0.02,
  "under_confident_top1": 0.2343, "correctly_deferred": 0.1105}`
- **Confusable pairs specifically** (`by_case_type.confusable_pair`):
  `{"success": 0.14, "retrieval_miss": 0.01, "wrong_auto_match": 0.098,
  "under_confident_top1": 0.241, "correctly_deferred": 0.511}`

This is already diagnostic in exactly the intended way: confusable pairs have almost no
`retrieval_miss` (1%, the retrieval layer is finding the right entity) but by far the
highest `wrong_auto_match` (9.8% vs. 2% overall) and the highest `correctly_deferred`
(51.1%) - confirming the confusable-pair problem is a scoring/threshold-confidence
problem, not a retrieval problem, exactly distinguishing the two failure classes this
categorization exists to separate. The medium-difficulty slice shows the opposite
pattern (`retrieval_miss` 20.4%, higher than its `wrong_auto_match` 0.66%) - still a
retrieval-layer story there, and a candidate target for a follow-up experiment 001-style
fix.

## Verdict

Kept (VALIDATED). This is additive and pure (new fields on an existing report, no changed
metric definitions), so it cannot regress anything measured before it - `dangerous_failure_rate_confusable_pairs`
is untouched and still reported alongside the new breakdown. Once `make evaluate` is
re-run post-reindex, a large `retrieval_miss` share on medium-tier rows would confirm more
retrieval-layer gaps remain (same diagnostic pattern as experiment 001); a large
`under_confident_top1` share would instead point at `matching.decision` thresholds in
`config/dev.yaml` as the next thing to tune.
