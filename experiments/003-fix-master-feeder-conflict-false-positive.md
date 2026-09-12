# 003: Fix master/feeder conflict false-positive on ambiguous queries

**Status:** VALIDATED
**Date:** 2026-09-12
**Targets:** Confusable-pair dangerous-failure rate

## Hypothesis

`master_conflict`/`feeder_conflict` in `src/er/matching/features.py` compared
`bool(query.is_master) != bool(candidate.is_master)`. `is_master`/`is_feeder` are derived
from name text (`er.normalisation.names.extract_fund_structure_tokens`) - a query whose
name simply doesn't contain the word "master" or "feeder" gets `is_master=False,
is_feeder=False` by default, which is indistinguishable at the boolean level from a query
that *positively asserts* "this is not a master fund." Hypothesis: this silently
penalizes whichever candidate genuinely IS a master/feeder fund whenever the query is
abbreviated or has that token stripped - exactly what `case_type=confusable_pair,
conflict_type=master_feeder` benchmark rows do on purpose (`generate_hard_negatives`
builds their query from `aggressive_core`, which strips master/feeder/fund-number tokens
by construction) - so it should make the matcher favor the WRONG (plain/non-fund) entity
in exactly the scenario this benchmark slice is designed to test.

## Method

Reproduced directly with the pure feature functions (no live OpenSearch needed):

```python
query = build_query_record('acme capital fund')  # no master/feeder token
master_candidate = {'is_master': True, 'is_feeder': False}
feeder_candidate = {'is_master': False, 'is_feeder': True}
master_conflict(query, master_candidate)  # -> True (WRONG: query made no claim at all)
master_conflict(query, feeder_candidate)  # -> False
```

This confirmed an 80-point penalty (`penalties.master_conflict`) applied asymmetrically
to the true master-fund candidate whenever the query lacked the word "master" - directly
capable of flipping a correct AUTO_MATCH into a wrong one, or a wrong one into a
dangerously confident one.

Fix: added `_query_asserts_fund_structure(query)` - only check for a master/feeder
contradiction when the query *itself* positively contains a master or feeder token; if
the query asserts neither, both `master_conflict` and `feeder_conflict` return `False`
regardless of what the candidate is. A genuine contradiction (query says "master fund",
candidate is a feeder) is still caught, unaffected by this change.

Measured via:
1. The same reproduction script, before/after.
2. Two new tests in `tests/test_features.py`
   (`test_no_master_feeder_conflict_when_query_is_ambiguous_but_candidate_is_not`,
   `test_master_feeder_conflict_still_detected_when_query_asserts_the_other`) plus the
   two pre-existing tests (`test_master_feeder_conflict_detected`,
   `test_no_master_feeder_conflict_when_neither_side_claims_it`) re-run to confirm no
   regression on the genuine-conflict case.
3. Full suite: `uv run pytest`.

## Result

Before fix:
```
ambiguous query vs master candidate: True   (WRONG - false positive)
ambiguous query vs feeder candidate: False
```

After fix:
```
ambiguous query vs master: False
ambiguous query vs feeder: False
master query vs feeder candidate (should be True): True True
master query vs master candidate (should be False): False False
```

Full test suite: 128 passed (0 failures, 0 regressions) - up from 126 pre-fix (2 new
tests added).

First attempt at measuring this used only the aggregate `dangerous_failure_rate_confusable_pairs`
(6.1%, unchanged from the Phase 5 baseline) - but that metric mixes all three
`hard_negatives` conflict types (`other_same_core` 38,226 / `fund_number` 30,084 /
`master_feeder` 2,760, only ~3.9% of the pool), so it could never isolate this fix's
effect. Added `conflict_type` as a real column through `evaluation_pairs.parquet` (was
previously dropped after `hard_negatives.parquet`) and a `by_conflict_type` breakdown to
`build_report()` (`src/er/evaluation/run_benchmark.py`) specifically to make this
measurable, then regenerated the benchmark and re-ran `make evaluate`.

**Result, sliced by conflict type** (6,000-row benchmark, this fix + experiments 001/002
all applied):

| conflict_type | n | dangerous_failure_rate | wrong_auto_match | auto_match_precision |
|---|---|---|---|---|
| fund_number | 445 | 0.0% | 8.3% | 0.0% (0 correct of 37 AUTO_MATCHes) |
| master_feeder | 34 | **23.5%** | 32.4% | 47.6% |
| other_same_core | 521 | 9.8% | 11.7% | 68.4% |

**Honest finding**: `master_feeder`'s dangerous-failure rate is still the highest of the
three slices at 23.5% (n=34, so a wide confidence interval - roughly ±14 points at this
sample size) even with this fix applied. No isolated before/after for this fix alone
exists (evaluate was only run with 001+002+003 all applied together), so this result
does not show the fix made things worse or failed - it shows the false-conflict penalty
this experiment fixed was not the *only*, or even necessarily the dominant, source of
master_feeder dangerous failures. `fund_number`'s 0% `auto_match_precision` is a more
alarming adjacent finding (worth its own experiment): every one of its 37 AUTO_MATCHes
in this sample picked the wrong fund number confidently - the `fund_number_conflict`
feature (`penalties.fund_number_conflict`) is either not firing when it should, or is
being outweighed by name/address evidence that shouldn't be enough to override it.

## Verdict

Kept (VALIDATED) on correctness grounds, independent of the inconclusive aggregate
effect: this is a strict fix to a feature that was actively mis-scoring an entire
benchmark slice by design, confirmed directly via the reproduction script and unit
tests (`test_no_master_feeder_conflict_when_query_is_ambiguous_but_candidate_is_not`).
It cannot make a genuinely conflicting case score worse, since that path is untouched,
and can only remove a false penalty that was previously always wrong.

**Next step identified, not yet built**: an isolated ablation (evaluate with this fix
reverted but 001/002 kept) would give a true before/after for this fix specifically.
More urgently: investigate the `fund_number` conflict feature directly - 0%
`auto_match_precision` on 37 confident AUTO_MATCHes in this sample is a bigger,
adjacent dangerous-failure source than the one this experiment targeted, and is now
directly measurable thanks to the `by_conflict_type` breakdown this experiment added.
