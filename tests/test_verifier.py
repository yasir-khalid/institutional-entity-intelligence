"""Unit tests for er.agent.verifier - the request it builds for Jev and, more
importantly, the deterministic probabilities -> badge rule. No network: the
Decisions API response is a synthetic fixture shaped exactly like the live
one (verified against https://openrouter.ai/api/alpha/decisions).
"""

from __future__ import annotations

import json

import pytest

from er.agent.models import AskResult, Citation, Evidence
from er.agent.verifier import build_questions, build_state, classify, unavailable
from er.config import VerifierConfig


def _evidence(evidence_id: str = "ev_abc1234567") -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source="GLEIF entity record (exact LEI lookup)",
        source_timestamp="2026-08-01",
        fact_type="lookup",
        criteria=["Entity ID = 5493001KJTIIGC8Y1R12"],
        record_refs=["5493001KJTIIGC8Y1R12"],
        fields_used=["legal_name", "entity_status"],
        result_count=1,
        query_hash="a1b2c3d4e5f6",
    )


def _result() -> AskResult:
    evidence = _evidence()
    return AskResult(
        answer="Bloomberg Finance L.P. is ACTIVE [1].",
        citations=[Citation(marker=1, evidence_id=evidence.evidence_id)],
        evidence={evidence.evidence_id: evidence},
    )


def _answers(
    grounded: float = 0.95,
    not_contradicted: float = 0.97,
    citations_supported: float = 0.9,
    scope_respected: float = 0.9,
    verdict: str = "supported",
    confidence: float = 0.93,
) -> dict:
    return {
        "grounded": {"type": "noul", "noul": grounded},
        "not_contradicted": {"type": "noul", "noul": not_contradicted},
        "citations_supported": {"type": "noul", "noul": citations_supported},
        "scope_respected": {"type": "noul", "noul": scope_respected},
        "verdict": {
            "type": "choice",
            "choice": verdict,
            "probabilities": {verdict: confidence},
            "confidence": confidence,
        },
    }


CFG = VerifierConfig()


def test_questions_match_the_decisions_api_contract():
    """Every question needs a type, instructions and criteria; noul criteria
    must be a true/false object and choice criteria a key->description map.
    Getting this wrong is a 4xx from the API, not a silently worse badge."""
    questions = build_questions()
    assert set(questions) == {
        "grounded",
        "not_contradicted",
        "citations_supported",
        "scope_respected",
        "verdict",
    }
    for key, question in questions.items():
        assert question["type"] in {"noul", "choice"}
        assert question["instructions"]
        assert question["criteria"]
        if question["type"] == "noul":
            assert set(question["criteria"]) == {"true", "false"}
    assert set(questions["verdict"]["criteria"]) == {"supported", "partially_supported", "unsupported"}


def test_state_resolves_citations_to_their_evidence_record():
    """An `ev_` id alone tells the verifier nothing about whether the cited
    lookup covers the claim - the record has to travel with it."""
    state = build_state("Is it active?", _result(), [{"tool": "search_entity", "result": {}}], 100_000)
    assert state["citations"][0]["evidence"]["source"].startswith("GLEIF")
    assert state["citations"][0]["evidence"]["criteria"] == ["Entity ID = 5493001KJTIIGC8Y1R12"]
    assert state["answer"] == "Bloomberg Finance L.P. is ACTIVE [1]."


def test_an_oversized_payload_is_shrunk_breadth_first_not_dropped():
    """The case that matters: a real depth-3 relationship tree is ~1.2M chars,
    ten times the whole budget. Dropping it wholesale would leave the verifier
    marking an answer's relationship claims unsupported because *we* withheld
    the records - so the tree is capped by breadth instead, keeping the top
    (which is what an "ultimate parent" answer cites) and shedding the tail."""
    tree = {"entity_id": "root", "children": [{"entity_id": f"sub{i}", "name": "X" * 60} for i in range(3_000)]}
    calls = [
        {"tool": "search_entity", "result": {"matches": [{"entity_id": "root"}]}},
        {"tool": "get_relationship_hierarchy", "result": {"tree": tree}},
    ]
    state = build_state("q", _result(), calls, 4_000)

    assert len(json.dumps(state)) <= 4_000
    hierarchy = state["tool_calls"][1]
    assert "result_omitted" not in hierarchy
    kept = hierarchy["result"]["tree"]["children"]
    assert kept[0]["entity_id"] == "sub0"
    # The small call alongside it is untouched - shrinking is uniform, not
    # "drop whatever happens to be biggest".
    assert state["tool_calls"][0]["result"] == {"matches": [{"entity_id": "root"}]}


def test_a_shortened_list_can_never_read_as_a_complete_one():
    """Without the marker, a capped list of parents would let the verifier
    score a correct "no other parents are recorded" as unsupported."""
    calls = [{"tool": "get_relationship_hierarchy", "result": {"parents": [{"id": i} for i in range(500)]}}]
    state = build_state("q", _result(), calls, 3_000)
    parents = state["tool_calls"][0]["result"]["parents"]
    assert isinstance(parents[-1], str)
    assert "more items elided" in parents[-1]


def test_a_payload_too_large_even_to_shrink_still_shows_the_call_was_made():
    """The last resort: the result goes, the call stays, marked."""
    calls = [{"tool": "get_entity_profile", "arguments": {"entity_id": "X"}, "result": {"blob": "y" * 50_000}}]
    state = build_state("q", _result(), calls, 900)
    assert state["tool_calls"][0]["tool"] == "get_entity_profile"
    assert state["tool_calls"][0]["arguments"] == {"entity_id": "X"}
    assert "result_omitted" in state["tool_calls"][0]
    assert len(json.dumps(state)) <= 900


def test_a_payload_that_fits_is_passed_through_untouched():
    calls = [{"tool": "search_entity", "result": {"matches": [{"entity_id": f"e{i}"} for i in range(400)]}}]
    state = build_state("q", _result(), calls, 200_000)
    assert len(state["tool_calls"][0]["result"]["matches"]) == 400


def test_all_checks_clear_and_verdict_supported_is_verified():
    status, checks, verdict, confidence = classify(_answers(), CFG)
    assert status == "verified"
    assert all(check.passed for check in checks)
    assert verdict == "supported"
    assert confidence == pytest.approx(0.93)


def test_one_weak_check_downgrades_to_partial_rather_than_failing():
    status, checks, _, _ = classify(_answers(citations_supported=0.4), CFG)
    assert status == "partial"
    assert [c.passed for c in checks if c.key == "citations_supported"] == [False]


def test_partially_supported_verdict_is_partial_even_when_every_noul_clears():
    assert classify(_answers(verdict="partially_supported"), CFG)[0] == "partial"


def test_a_contradiction_vetoes_even_a_supported_verdict():
    """The veto is tested before the verdict on purpose: an answer that
    conflicts with the records must not be able to ride a holistic
    "supported" back up to partial or verified."""
    assert classify(_answers(not_contradicted=0.2), CFG)[0] == "unverified"
    assert classify(_answers(not_contradicted=0.2, verdict="supported"), CFG)[0] == "unverified"


def test_unsupported_extra_detail_is_partial_not_unverified():
    """The asymmetry the rule is built on: an answer whose main claim holds but
    which adds an uncovered detail scores near-zero on `grounded` while staying
    high on `not_contradicted`. That is a "partially verified", not a failure -
    collapsing the two would make the badge useless at its most common
    outcome."""
    status, _, _, _ = classify(_answers(grounded=0.07, not_contradicted=0.79, verdict="partially_supported"), CFG)
    assert status == "partial"


def test_unsupported_verdict_is_unverified():
    assert classify(_answers(verdict="unsupported"), CFG)[0] == "unverified"


def test_a_missing_answer_is_no_signal_not_a_failure():
    """Jev skipping a key means we did not get a reading, which is a different
    state from a reading that failed - conflating them would mark a healthy
    answer as unverified on a transport hiccup, or a partly-unchecked answer as
    fully verified."""
    answers = _answers()
    del answers["grounded"]
    status, checks, _, _ = classify(answers, CFG)
    assert status == "unavailable"
    grounded = next(check for check in checks if check.key == "grounded")
    assert grounded.probability is None
    assert grounded.passed is None


# Readings recorded from the live model (typesafe/jev-1.13-20260917) over a
# labelled answer set on 2026-09-22 - the sweep in
# experiments/006-jev-answer-verification.md. Replaying them here pins the
# thresholds in config to the distribution they were chosen from: if someone
# retunes a threshold by feel, the case it breaks fails loudly instead of the
# badge quietly drifting. Re-record (don't delete) these when the model
# version changes.
RECORDED_SWEEP = [
    ("good/concise", 0.85, 0.96, 0.91, 0.91, "supported", "verified"),
    ("good/hedged", 0.80, 0.96, 0.86, 0.89, "supported", "verified"),
    ("good/with-caveat", 0.77, 0.94, 0.79, 0.94, "supported", "verified"),
    ("good/lists-ids", 0.88, 0.97, 0.88, 0.91, "supported", "verified"),
    ("flawed/unsupported-detail", 0.07, 0.79, 0.20, 0.21, "partially_supported", "partial"),
    ("flawed/uncited-claim", 0.06, 0.78, 0.52, 0.09, "partially_supported", "partial"),
    ("flawed/overreach", 0.05, 0.80, 0.11, 0.08, "partially_supported", "partial"),
    ("flawed/wrong-direction", 0.49, 0.45, 0.53, 0.45, "partially_supported", "unverified"),
    ("bad/contradicted", 0.02, 0.04, 0.08, 0.03, "unsupported", "unverified"),
    ("bad/wrong-entity", 0.01, 0.01, 0.04, 0.01, "unsupported", "unverified"),
]


@pytest.mark.parametrize(
    ("case", "grounded", "not_contradicted", "citations", "scope", "verdict", "expected"),
    RECORDED_SWEEP,
    ids=[row[0] for row in RECORDED_SWEEP],
)
def test_recorded_live_readings_land_on_the_right_badge(
    case, grounded, not_contradicted, citations, scope, verdict, expected
):
    answers = _answers(
        grounded=grounded,
        not_contradicted=not_contradicted,
        citations_supported=citations,
        scope_respected=scope,
        verdict=verdict,
    )
    assert classify(answers, CFG)[0] == expected, case


def test_the_thresholds_sit_clear_of_both_observed_populations():
    """The defaults must keep a margin on each side of the measured gap, not
    merely happen to land inside it - a threshold flush against the good-answer
    minimum passes the sweep today and fails on the next faithful answer."""
    good = [row for row in RECORDED_SWEEP if row[0].startswith("good/")]
    other = [row for row in RECORDED_SWEEP if not row[0].startswith("good/")]
    for index, minimum in (
        (1, CFG.grounded_min),
        (2, CFG.not_contradicted_min),
        (3, CFG.citations_supported_min),
        (4, CFG.scope_respected_min),
    ):
        assert minimum <= min(row[index] for row in good) - 0.05
        assert minimum >= max(row[index] for row in other) + 0.05


def test_thresholds_come_from_config_not_code():
    """Retuning the badge must be a config edit - the same rule the matcher's
    weights follow."""
    strict = VerifierConfig(citations_supported_min=0.99)
    assert classify(_answers(citations_supported=0.9), CFG)[0] == "verified"
    assert classify(_answers(citations_supported=0.9), strict)[0] == "partial"


def test_unavailable_never_claims_the_answer_failed():
    verification = unavailable("The verification model could not be reached (ConnectError).")
    assert verification.status == "unavailable"
    assert verification.checks == []
    assert "not been checked either way" in verification.detail



# --- transient failures ----------------------------------------------------------
# Seen in the web UI: "Not checked - The verification model could not be reached
# (ConnectTimeout)". Six Jev calls made straight afterwards all succeeded in
# ~0.3-0.5s. A single blip cost a 30s wait and an unverified answer.

import asyncio

import httpx

import er.agent.verifier as verifier


def _jev_answers_payload() -> dict:
    return {"model": "typesafe/jev-1.13-20260917", "answers": _answers(), "usage": {"input_tokens": 400}}


def _decisions(monkeypatch, outcomes: list):
    """Each call to the Decisions API takes the next outcome: an exception to
    raise, or a payload to return. Returns the list of calls made."""
    calls: list[int] = []
    queue = list(outcomes)

    async def fake_post(_cfg, _state, _questions):
        calls.append(1)
        outcome = queue.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(verifier, "_post_decisions", fake_post)
    monkeypatch.setattr(verifier, "_backoff", no_wait)
    return calls


def _verify():
    from er.config import load_config

    return asyncio.run(verifier.verify_answer(load_config(), "Is it active?", _result(), []))


def _http_status(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://openrouter.ai/api/alpha/decisions")
    return httpx.HTTPStatusError(str(code), request=request, response=httpx.Response(code, request=request))


def test_a_connect_timeout_is_retried_and_the_answer_still_gets_a_badge(monkeypatch):
    calls = _decisions(monkeypatch, [httpx.ConnectTimeout("timed out"), _jev_answers_payload()])
    verification = _verify()
    assert verification.status == "verified"
    assert verification.attempts == 2
    assert len(calls) == 2


def test_when_every_attempt_fails_the_badge_says_so_and_how_many_were_made(monkeypatch):
    calls = _decisions(monkeypatch, [httpx.ConnectTimeout("t")] * 3)
    verification = _verify()
    assert verification.status == "unavailable"
    assert verification.reason == "The verification model could not be reached after 3 attempts (ConnectTimeout)."
    assert len(calls) == 3


def test_a_rejected_request_is_not_retried(monkeypatch):
    """A 400/401 will fail the same way again - retrying only delays the badge."""
    calls = _decisions(monkeypatch, [_http_status(401)])
    verification = _verify()
    assert verification.reason == "The verification model returned HTTP 401."
    assert len(calls) == 1


def test_an_overloaded_verifier_is_retried(monkeypatch):
    calls = _decisions(monkeypatch, [_http_status(503), _jev_answers_payload()])
    assert _verify().status == "verified"
    assert len(calls) == 2


def test_connecting_gives_up_long_before_the_request_timeout():
    """Connecting to openrouter.ai normally takes ~0.07s. The ConnectTimeout
    that cost 30s was waiting the whole request timeout for a connection that
    was never going to open."""
    from er.agent.retry import timeout
    from er.config import load_config

    vcfg = load_config().agent.verifier
    t = timeout(vcfg.timeout_seconds, vcfg.connect_timeout_seconds)
    assert t.connect == 5.0
    assert t.read == 30.0


# --- Jev's token limit -------------------------------------------------------------
# Seen on "Trace the ownership chain above Citigroup Energy Holdings": a red
# Verification node, HTTP 400 "max_tokens_exceeded". Measured against the live
# API on 2026-09-28: 32,443 input tokens accepted, ~33.4k rejected - the limit
# is 32,768, not the 64k one write-up claims - and this JSON runs ~2.0 chars
# per token, so the old 120k-char budget meant ~52k tokens.


def _too_big() -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://openrouter.ai/api/alpha/decisions")
    response = httpx.Response(
        400, request=request,
        json={"error": {"message": 'HTTP 400: {"detail":{"error_type":"max_tokens_exceeded"}}', "code": 400}},
    )
    return httpx.HTTPStatusError("400", request=request, response=response)


def test_the_default_budget_fits_the_measured_token_limit():
    from er.config import load_config

    measured_chars_per_token = 2.0
    budget_tokens = load_config().agent.verifier.max_state_chars / measured_chars_per_token
    assert budget_tokens < 32_768 * 0.85  # headroom for content denser than measured


def test_a_state_over_the_token_limit_is_halved_and_retried_rather_than_left_unchecked(monkeypatch):
    sizes: list[int] = []
    outcomes = [_too_big(), _jev_answers_payload()]

    async def fake_post(_cfg, state, _questions):
        sizes.append(len(json.dumps(state)))
        outcome = outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def no_wait(_seconds):
        return None

    monkeypatch.setattr(verifier, "_post_decisions", fake_post)
    monkeypatch.setattr(verifier, "_backoff", no_wait)

    big_calls = [{"tool": "get_entity_profile", "result": {"identifiers": [
        {"isin": f"DE000A{i:06d}", "source": "GLEIF ISIN bridge " + "x" * 150} for i in range(20_000)
    ]}}]
    from er.config import load_config

    verification = asyncio.run(verifier.verify_answer(load_config(), "q", _result(), big_calls))
    assert verification.status == "verified"
    assert len(sizes) == 2
    assert sizes[1] < sizes[0]


def test_an_unrecoverable_bad_request_reports_the_providers_own_message(monkeypatch):
    request = httpx.Request("POST", "https://openrouter.ai/api/alpha/decisions")
    bad = httpx.HTTPStatusError(
        "400", request=request,
        response=httpx.Response(400, request=request, json={"error": {"message": "Unknown question type"}}),
    )
    calls = _decisions(monkeypatch, [bad])
    verification = _verify()
    assert verification.reason == "The verification model returned HTTP 400: Unknown question type."
    assert len(calls) == 1
