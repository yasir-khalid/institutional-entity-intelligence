# Experiments

A record of techniques tried against the real benchmark (`data/benchmark/evaluation_pairs.parquet`,
scored via `make evaluate` / `uv run python -m er.evaluation.run_benchmark`), not just ideas -
every experiment here has a measured before/after number attached, and is explicitly marked
**VALIDATED** (kept, shipped) or **INVALIDATED** (tried, measured, reverted or not adopted).

This exists so a change to scoring/retrieval is never re-litigated from scratch, and so a
technique that sounds reasonable but didn't move the needle doesn't get re-tried blind six
months from now.

## Format

One file per experiment: `NNN-short-slug.md`, numbered in the order they were run. Each file:

```markdown
# NNN: Title

**Status:** VALIDATED | INVALIDATED | INCONCLUSIVE
**Date:** YYYY-MM-DD
**Targets:** which flagged gap this addresses (link back to README's "still open" list)

## Hypothesis
One or two sentences: what change, why it should help.

## Method
What was actually changed (files, exact diff summary) and how it was measured
(exact command run, e.g. `make evaluate`).

## Result
Before/after numbers, verbatim from the evaluation report - not paraphrased.

## Verdict
Kept or reverted, and why. If INVALIDATED, what to try instead (if anything comes to mind).
```

## Index

| # | Title | Status | Targets |
|---|---|---|---|
| [001](001-compact-name-field-for-glued-queries.md) | Compact (space-stripped) keyword field for glued/no-space name queries | VALIDATED | Medium-tier recall (~55%) |
| [002](002-failure-analysis-categorization.md) | Categorize evaluation failures instead of just aggregate precision/recall | VALIDATED | Failure-analysis categorization |
| [003](003-fix-master-feeder-conflict-false-positive.md) | Fix master/feeder conflict false-positive on ambiguous queries | VALIDATED | Confusable-pair dangerous-failure rate |
| [004](004-benchmark-collision-artifact-not-a-matcher-bug.md) | "0% precision on fund_number pairs" was a benchmark labeling artifact | VALIDATED (benchmark fix) | Confusable-pair dangerous-failure rate |
| [005](005-fund-structure-ambiguity-guard.md) | Refuse AUTO_MATCH when query is master/feeder-silent and top-2 disagree | VALIDATED | Confusable-pair dangerous-failure rate |
| [006](006-jev-answer-verification.md) | Verify every agent answer against its own tool results with a decision model | VALIDATED | Agent answer faithfulness |
| [007](007-13f-value-scale-check.md) | Flag 13F filings that still report values in thousands | VALIDATED | 13F value scale |
