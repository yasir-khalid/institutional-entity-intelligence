# 004: "0% precision on fund_number confusable pairs" was a benchmark labeling artifact, not a matcher bug

**Status:** VALIDATED (as a benchmark fix; the originally-suspected matcher bug is INVALIDATED - there wasn't one)
**Date:** 2026-09-12
**Targets:** Confusable-pair dangerous-failure rate (specifically the `fund_number` conflict type surfaced by experiment 003's `by_conflict_type` breakdown)

## Hypothesis

Experiment 003's `by_conflict_type` breakdown showed `fund_number` confusable pairs at
**0% AUTO_MATCH precision** (37/37 confident matches wrong) - a much bigger dangerous-
failure source than the master/feeder bug that experiment fixed. Initial hypothesis:
`fund_number_conflict`/`fund_number_exact` have a real scoring bug, similar in shape to
experiment 003's master/feeder fix, that needed a matching fix in `features.py`.

## Method

Before writing any fix, reproduced 4 of the 37 wrong AUTO_MATCHes directly against the
live matcher and inspected the actual candidate pool and evidence for each:

```python
match(client, cfg, 'hvb funding trust', 'US')
# 1  549300MUG4A5QV22CZ21  HVB FUNDING TRUST       US-DE  215.0  name_exact+name_core_exact
# 2  549300RDEOH0GT1T7O25  HVB FUNDING TRUST III   US-DE   55.0  name_ratio only
# 3  54930074G10HO103GR68  HVB FUNDING TRUST II    US-DE   55.0  name_ratio only
```

All 4 reproduced cases showed the exact same pattern: the benchmark's query text is
built from `aggressive_core` (`er.benchmark.generate`), which strips the trailing fund
number/roman-numeral from the true entity's name to create an "ambiguous" adversarial
query (e.g. "HVB FUNDING TRUST III" -> query "hvb funding trust"). But GLEIF's real data
turned out to independently contain a genuinely distinct, unrelated entity named exactly
"HVB FUNDING TRUST" (no numeral at all) - so the stripped query is a perfect
`name_exact`/`name_core_exact` match for that THIRD entity, which is the objectively
correct answer to the literal query text. The benchmark's `expected_lei` (one of the
numbered siblings) was never a fair label for that query in the first place - the matcher
wasn't wrong, the test case was mislabeled.

Fix: added a collision guard to `generate_hard_negatives()`
(`src/er/benchmark/generate.py`) - a hard-negative pair's `aggressive_core` is now
excluded from the benchmark whenever a THIRD, unrelated GLEIF entity's own
`legal_name_core` exactly equals it (`NOT EXISTS (... WHERE x.legal_name_core =
p.aggressive_core AND x.lei NOT IN (p.lei_a, p.lei_b))`). This keeps every remaining
confusable_pair row a fair test: nothing outside the intended pair legitimately answers
the stripped query.

Measured via `make evaluate` before/after regenerating the benchmark with this guard.

## Result

`hard_negatives.parquet` row counts, before/after the collision guard:

| conflict_type | before | after |
|---|---|---|
| fund_number | 30,084 | 26,432 |
| other_same_core | 38,226 | 21,351 (mostly collision artifacts - see caveat below) |
| master_feeder | 2,760 | 2,049 |
| **total** | 71,070 | 49,832 |

The `other_same_core` drop is much larger proportionally than `fund_number`/
`master_feeder` - expected, since `other_same_core` pairs by definition already share an
identical `aggressive_core` with nothing to strip, so a genuine third-party collision on
that exact string is a real and common occurrence for generic/short names, not a rare
edge case. This is arguably correct behavior for the guard (a truly ambiguous 3+-way name
collision shouldn't be scored as a clean 2-way confusable pair either), but is flagged
here as worth a second look if `other_same_core`'s sample size becomes too small.

Full `make evaluate` (6,000 rows) `by_conflict_type.fund_number`, before vs. after this
fix (both runs already include experiments 001/002/003):

| | before (mislabeled benchmark) | after (collision guard) |
|---|---|---|
| n | 445 | 524 (resampled from the collision-free pool) |
| AUTO_MATCH coverage | 8.31% (37 confident matches) | **0.19%** (1 confident match) |
| AUTO_MATCH precision | 0.0% | 0.0% (n=1 - noise, not a pattern) |
| dangerous_failure_rate | 0.0%* | 0.0% |
| decision: UNMATCHED | 89.66% | 99.62% |

*`dangerous_failure_rate` was already 0% before this fix because none of the 37 wrong
AUTO_MATCHes happened to pick the specific paired `confusable_lei` - they picked
unrelated third entities instead (also a benchmark-labeling symptom, not a real dangerous
failure by this metric's own definition). `AUTO_MATCH coverage` collapsing from 8.31% to
0.19% is the real confirmation: removing the mislabeled rows removed nearly all of the
"confident but wrong" cases, leaving one likely-genuine edge case in 524 rows rather than
a systemic 8% failure rate.

## Verdict

The benchmark fix is VALIDATED - it removes a real labeling flaw that would have kept
misdirecting future work toward "fixing" a matcher bug that doesn't exist. The originally
-suspected `fund_number_conflict`/`fund_number_exact` scoring bug is INVALIDATED: direct
reproduction showed the matcher's answer was correct given the literal query text in
every sampled case; there is no evidence of a real scoring defect on ambiguous fund-number
queries once the benchmark's labels are trustworthy.

**Lesson for future benchmark work**: any hard-negative generation strategy that
transforms a real name into an adversarial query (stripping tokens, abbreviating, etc.)
must verify the transformed string doesn't collide with a real, different, correctly-
labeled-elsewhere entity - otherwise "dangerous failure" metrics measure benchmark noise,
not matcher quality. Apply the same collision-guard pattern to any future query-mutation
strategy added to `er.benchmark.generate`.
