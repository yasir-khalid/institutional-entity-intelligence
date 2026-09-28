# 006: Verify every agent answer against its own tool results with a decision model

**Status:** VALIDATED
**Date:** 2026-09-22
**Targets:** The agent layer's one unguarded seam. `er.agent.orchestrator` already
enforces that a citation names an `evidence_id` some tool call actually returned, but
nothing checked whether the *sentence* that marker is attached to follows from that
record. An answer could cite four real lookups and still over-state what they showed.

## Hypothesis

A "System One" decision model can check a finished answer against the records behind it
in well under a second, because the check is a fixed set of typed questions rather than
generated prose. TypeSafe's Jev (`typesafe/jev-1.13`, OpenRouter's Decisions API) returns
one calibrated probability per question in a single forward pass, and the set of valid
outputs is fixed by the request schema - so it cannot invent an option or a confidence
score the way a chat model asked to "rate this answer 0-100" can. If those probabilities
separate faithful answers from flawed ones by a wide margin, a deterministic
threshold rule over them is a defensible badge; if they don't, this is theatre and
should not ship.

## Method

Endpoint confirmed live before writing any code (the published third-party examples
disagree - one documents `options`/`rubric` keys and a `decisions` response wrapper,
which the API rejects):

```
POST https://openrouter.ai/api/alpha/decisions
{"model": "typesafe/jev-1.13", "state": <str|obj|list>,
 "questions": {"<key>": {"type": "noul"|"choice"|"score",
                         "instructions": "...", "criteria": ...}}}
-> {"model": "typesafe/jev-1.13-20260917",
    "answers": {"<key>": {"type": "noul", "noul": 0.92}},
    "usage": {"input_tokens": 422, "output_tokens": 61, "cost": 1.77e-05}}
```

New `src/er/agent/verifier.py` asks five questions about every finished answer: four
`noul` (grounded / not_contradicted / citations_supported / scope_respected) and one
`choice` verdict. The state is the question, the answer, each citation resolved to its
Evidence record, and every tool call with its result.

Measured with a 10-answer labelled set over one fixed record set (4 faithful, 4 flawed,
2 fabricated), run twice against the live model:

```
uv run python /tmp/jev_calibrate.py     # sweep script, readings below
```

## Result

Run 1 (raw readings, before any threshold was chosen):

```
good    concise             grounded=0.85  not_contra=0.96  cites=0.91  scope=0.91  supported
good    hedged              grounded=0.80  not_contra=0.96  cites=0.86  scope=0.89  supported
good    with-caveat         grounded=0.77  not_contra=0.94  cites=0.79  scope=0.94  supported
good    lists-ids           grounded=0.88  not_contra=0.97  cites=0.88  scope=0.91  supported
flawed  unsupported-detail  grounded=0.07  not_contra=0.79  cites=0.20  scope=0.21  partially_supported
flawed  uncited-claim       grounded=0.06  not_contra=0.78  cites=0.52  scope=0.09  partially_supported
flawed  overreach           grounded=0.05  not_contra=0.80  cites=0.11  scope=0.08  partially_supported
flawed  wrong-direction     grounded=0.49  not_contra=0.45  cites=0.53  scope=0.45  partially_supported
bad     contradicted        grounded=0.02  not_contra=0.04  cites=0.08  scope=0.03  unsupported
bad     wrong-entity        grounded=0.01  not_contra=0.01  cites=0.04  scope=0.01  unsupported

grounded             good min=0.77 | not-good max=0.49
not_contradicted     good min=0.94 | not-good max=0.80
citations_supported  good min=0.79 | not-good max=0.53
scope_respected      good min=0.89 | not-good max=0.45
```

Separation is wide on every check, and the fabricated answers bottom out near zero.
Latency 379-610 ms; cost ~1.8e-05 USD per verification.

Two things the sweep corrected, both of which would have shipped wrong on intuition:

**1. The obvious thresholds were miscalibrated.** The first cut set `grounded_min` at
0.85. A *faithful* answer reads ~0.8 on `grounded`, not ~0.95 - the question asks
whether **every** claim is supported, and a well-hedged answer still leaves the model
some doubt. That bar marked all four good answers "partially verified", i.e. the badge
would essentially never have said "verified". Thresholds now sit at the midpoint of the
measured gap: `grounded_min` 0.70, `not_contradicted_min` 0.87, `citations_supported_min`
0.70, `scope_respected_min` 0.75.

**2. The rule shape was wrong.** The first cut treated a low `grounded` as
disqualifying. But `unsupported-detail` (main claim right, one uncovered extra fact)
reads 0.07 on `grounded` while staying at 0.79 on `not_contradicted` - calling that
"unverified" over-states the problem as badly as calling it "verified" understates it.
The rule is now verdict-led with a single veto: `not_contradicted < 0.50` is unverified
whatever else it scored, because a confidently *wrong* answer is the failure this project
optimizes hardest against (AGENTS.md, on `decide()`); merely unsupported extra detail is
a "partial". That rule lands all 10 cases correctly, on both runs.

Run 2, after recalibration, end to end through `verify_answer()`: 10/10 correct
(`verified` × 4, `partial` × 3, `unverified` × 3). Individual readings moved by up to
0.07 between runs, which is why the thresholds keep a >= 0.05 margin on both sides of the
gap rather than sitting flush against the good-answer minimum - pinned by
`test_the_thresholds_sit_clear_of_both_observed_populations`.

### The bug the measurement found

The first live run on a real relationship question ("Who ultimately manages Albacore
Partners I Master Fund?") came back `partial` with three failed checks. The cause was not
the answer:

```
search_entity payload        2,904 chars
get_entity_profile payload   2,211 chars
hierarchy depth=3 payload  1,199,339 chars   <- 10x the entire 120k state budget
```

The original trimmer dropped an oversized tool result wholesale, so on *any* relationship
question the verifier was judging the answer's relationship claims against records that
had been withheld from it - and reporting the resulting mismatch as the answer's fault.
That is the worst possible failure for a verifier: it manufactures the very thing it
claims to detect.

`build_state()` now shrinks breadth-first instead (`SHRINK_PASSES`, capping list length
at every level, each elision replaced by a visible marker so a shortened list can never
read as a complete one). The same payload now fits at 38,857 chars with the root LEI and
the full upward parent chain intact - which is exactly the part an "ultimate parent"
answer cites. Re-running the identical question:

```
before:  partial     grounded=0.61  not_contra=0.84  cites=0.66  scope=0.77
after:   verified    grounded=0.74  not_contra=0.89  cites=0.73  scope=0.86
```

## Verdict

**VALIDATED.** Shipped as `er.agent.verifier`, wired into every `er.agent.orchestrator`
return path, rendered by `er.cli.ask_render` and `web/src/components/VerificationBadge.tsx`.

Caveats worth carrying forward:

- Jev cannot hallucinate an option, but it **can pick the wrong one**. The badge is a
  check, not a guarantee, and the UI says so in as many words: it confirms the answer
  matches what was retrieved, never that the records are complete or correct.
- `unavailable` (the check did not run) is a distinct status from `unverified` (it ran
  and the answer did not hold up), and renders grey, never red. A verifier outage must
  never look like an answer failing.
- The recorded readings live in `tests/test_verifier.py::RECORDED_SWEEP` so a threshold
  retuned by feel breaks a named case loudly. Re-record them (don't delete them) when the
  model version moves off `jev-1.13-20260917`.
- Not measured here: whether the badge is well-calibrated on *real* agent answers at
  volume, as opposed to a 10-case constructed set. The obvious next experiment is to run
  the verifier across a batch of benchmark questions and look at the status distribution.

---

## Follow-up: why a good answer reads 0.61-0.79 on `grounded`

**Date:** 2026-09-23

A real answer came back `partial` with `grounded` at 0.61, and the obvious
question - "does Jev say why?" - has a flat answer: **no, and it never can.**
Jev emits no text at all; the output is a probability per question. A rationale
is not something that can be read out of it.

What *can* be done is ask better questions, since Jev answers all of them in one
pass. Decomposing the answer into its 14 sentences and asking one `noul` per
sentence, against the same records (one request, 9,582 input tokens,
$0.0004):

```
     0.58  ...a renewal date of 29 September 2020 that was evidently not met [7]
     0.72  and acts as investment manager for a large set of Alger funds [5]
     0.85  FRED ALGER MANAGEMENT, LLC (LEI 549300TITGLG7BXCGB39, Delaware, US) is ...
     0.88  It carries CIK 0000003520 sourced from SEC 13F filings [4] ...
     0.90  A name search for "Fred Alger Management" returns two closely-matching ...
     0.91  It has no attached identifiers and no SEC 13F activity [6]
     0.92  So the answer depends on which legal entity is meant ...
     0.93  FRED ALGER MANAGEMENT, INC. (LEI 549300DJT5ERKM01RD40, New York, US) ...
     0.96  Initial LEI registration date: 22 January 2020; last update: 23 July 2026 ...
     0.97  GLEIF registration status: ISSUED [3]
     0.97  Entity status: INACTIVE [6]
     0.97  GLEIF registration status: RETIRED [7]
     0.98  It sits under direct and ultimate parent ALGER ASSOCIATES, INC.
```

Aggregate for that answer: 0.75. Twelve claims score 0.85-0.98; two don't.
**The aggregate tracks the weakest claim, not the average** - which is exactly
right for a question that asks whether *every* claim is supported, but it means
one hedged sentence drags the whole bar down with nothing on screen to say
which one.

And the two weak claims are genuinely weak. "A renewal date that was *evidently
not met*" is an inference the records don't state; "a *large set* of Alger
funds" is a quantity no record gives. The signal was real the whole time, just
unreadable.

### Answer length: suspected, tested, refuted

The intuitive explanation - a conjunction over more claims must fall as the
answer grows - is wrong. Scored over progressive prefixes of the same answer
against the same records:

```
prefix   chars  grounded  not_contra   cites   scope  verdict
 2 ln      237      0.74        0.92    0.73    0.80  supported
 4 ln      305      0.78        0.93    0.85    0.83  supported
 6 ln      603      0.75        0.92    0.81    0.85  supported
 9 ln      863      0.69        0.83    0.68    0.84  supported
13 ln     1443      0.72        0.93    0.84    0.86  supported
```

Flat from 237 to 1443 chars. Length is not a factor; don't re-suspect it.

(A first version of this test spliced together the highest-scoring sentences
into synthetic variants and produced a dramatic-looking collapse to 0.15. That
was the test's fault: the splice joined a claim about the LLC to a claim about
the INC., asserting both of a single entity. Jev was right and the fixture was
wrong - which is itself a data point on the check doing its job. Rebuilt with
coherent prefixes, as above.)

### Run-to-run variance

The same question scored `grounded` 0.79, 0.75, 0.72 and 0.61 across four runs.
A reading sitting near a threshold will flip the badge between identical runs.
This is the calibrated-probability equivalent of a tie in `decide()`, and the
honest response is the same: don't tighten the threshold to make the wobble
disappear, show the reader what is actually marginal.

### Shipped

`split_claims()` / `build_claim_questions()` in `er.agent.verifier`, issued as a
second Decisions request `asyncio.gather`-ed with the first - so it costs a
second request but no extra wall-clock time (measured 390 ms end to end, against
380-610 ms before) and is allowed to fail on its own without costing the badge.
Claims scoring below `claim_supported_min` (0.60) are quoted back under the
meters in both the CLI and the web badge.

First live run after shipping, on the same question:

```
Verified   grounded 0.75 / not_contradicted 0.93 / citations 0.82 / scope 0.83
Claim that pulled this down
  "FRED ALGER MANAGEMENT, INC. (jurisdiction US-NY) - this is an older,
   legacy record."  0.59
```

"An older, legacy record" is an editorial characterisation GLEIF does not make.
That is the number explaining itself.

### Removed (2026-09-25)

The per-claim drill-down was taken back out: it doubled the Decisions requests
per answer and the added latency isn't worth it for now. The badge is back to
one request with the four aggregate checks plus the verdict.

The findings above still stand and are the reason to bring it back if a low
reading ever needs explaining: the aggregate tracks the weakest claim, not the
average; answer length is not a factor; and run-to-run variance is about +/-0.1.
The implementation was `split_claims()` (sentence/line split, markdown
stripped, fragments under 25 chars dropped, capped at 24) plus one `noul` per
claim in a second request - re-adding it is a small change.
