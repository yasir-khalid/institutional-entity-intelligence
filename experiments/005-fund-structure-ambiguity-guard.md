# 005: Refuse AUTO_MATCH when the query is master/feeder-silent and the top-2 candidates disagree

**Status:** VALIDATED
**Date:** 2026-09-12
**Targets:** Confusable-pair dangerous-failure rate (`master_feeder` slice, discovered via experiment 003/004's `by_conflict_type` breakdown)

## Hypothesis

After experiment 004 showed the `fund_number` "0% precision" finding was a benchmark
labeling artifact, `master_feeder` still showed a real 26.1% dangerous-failure rate
(n=46) in the same corrected run - unlike `fund_number`, direct reproduction showed this
was NOT a benchmark artifact (no third-party name collision). Every sampled case showed
the same real scoring asymmetry: a query that omits "master"/"feeder" entirely (e.g. an
aggressive-core-stripped query, or a genuinely brand-style abbreviated query) string-
matches the master/plain variant's `legal_name_core` *exactly* (earning
`name_core_exact`'s 60-point bonus), while the feeder variant's own core still carries
the literal word "feeder" and can never earn that exact-match bonus - only the lower
`name_ratio` fuzzy score. This produces a large (60-240 point), confident-looking score
gap that reflects incidental tokenization asymmetry, not real evidence that the query
meant the master fund specifically.

## Method

Reproduced directly against the live matcher for multiple real cases:

```
strategic partners ix lux -> chosen STRATEGIC PARTNERS IX (LUX) SCSP (the master,
  name_core_exact=60, score 100) over STRATEGIC PARTNERS FEEDER IX (LUX) SCSP (the
  true expected feeder, name_ratio only, score 40) - gap 60, AUTO_MATCH, WRONG.
```

12 such cases found in the 46-row `master_feeder` sample, all following the identical
pattern (the wrong "plain" candidate string-matches better purely because it has no
extra token to lose exact-match credit on).

Fix: added `_fund_structure_ambiguous()` to `src/er/matching/matcher.py` - after
`decide()` returns AUTO_MATCH, check whether the query itself asserts neither master nor
feeder (`query["is_master"]` and `query["is_feeder"]` both False) AND the top-2 scored
candidates disagree on master/feeder status. If both hold, downgrade the decision to
REVIEW regardless of the score gap - the gap in this specific situation is known to be an
artifact of `name_core_exact`'s tokenization sensitivity, not disambiguating evidence.
This complements, rather than duplicates, experiment 003's `master_conflict`/
`feeder_conflict` fix: that fix stops a false *penalty* from being applied; this fix
catches a different failure path where no penalty ever needed to fire because the
asymmetry lives entirely in the *positive* `name_core_exact` bonus, which
`master_conflict`/`feeder_conflict` never touch.

Measured via the same 4 reproduction cases, 4 new unit tests
(`tests/test_matcher.py::test_fund_structure_*`), and a full `make evaluate` run.

## Result

Reproduction, before/after:

```
strategic partners ix lux              -> AUTO_MATCH (wrong)  -> REVIEW
hyperion quantitative strategies fund  -> AUTO_MATCH (wrong)  -> REVIEW
blackrock hajar fund                   -> AUTO_MATCH (wrong)  -> REVIEW
```

Full test suite: 139 passed (4 new tests, 0 regressions).

Full-benchmark `make evaluate` (6,000 rows) `by_conflict_type.master_feeder`, before vs.
after this fix (both include experiments 001-004, same 46-row sample):

| | before | after |
|---|---|---|
| n | 46 | 46 |
| dangerous_failure_rate | **26.09%** | **0.0%** |
| AUTO_MATCH coverage | 56.52% | 10.87% |
| AUTO_MATCH precision | 53.85% | **100%** |
| REVIEW rate | 0% | 45.65% |

The trade fully matches the intent: every wrong, confident match on this slice was
eliminated, at the cost of pushing most of those cases (46.65 of the recovered 45.65pp)
to REVIEW rather than a correct AUTO_MATCH - because the query genuinely doesn't contain
enough information to tell master from feeder, REVIEW (a human decides) is the honest
answer, not a forced guess. Overall benchmark impact (all 6,000 rows, experiments
001-005 combined): `dangerous_failure_rate_confusable_pairs` **6.2% -> 4.9%**,
`auto_match_precision` (overall) **97.33% -> 97.72%** - both moved the right direction
with no other metric regressing (Recall@20 unchanged at 88.3%, since this is a decision-
layer change with zero effect on retrieval).

## Verdict

Kept (VALIDATED) on direct-reproduction and unit-test grounds independent of the
aggregate number: this closes a real, reproducible dangerous-failure path with a
targeted, narrowly-scoped guard (fires only when the query is genuinely silent on
master/feeder AND the top-2 disagree - a query that positively asserts a claim, or a
pool where the top-2 already agree on structure, is untouched). The guard trades some
`AUTO_MATCH` coverage for safety in exactly the ambiguous cases the project's design
treats as most costly to get wrong (dangerous_failure_rate is prioritized over
coverage/recall throughout this project - see `dangerous_failure_rate_confusable_pairs`
in `er.evaluation.metrics`).

**Next step, not yet built**: the same asymmetry likely exists for `is_offshore`/
`is_domestic` structure tokens (`FUND_STRUCTURE_TOKENS` in
`er.normalisation.names`), which share the identical mechanism but weren't covered by
this fix's scope (master/feeder only). Worth the same reproduction-first check before
generalizing `_fund_structure_ambiguous()` to all four tokens.
