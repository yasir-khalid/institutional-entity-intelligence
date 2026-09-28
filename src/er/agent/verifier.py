"""Post-answer verification of an er.agent answer with TypeSafe's Jev, a
"System One" decision model served over OpenRouter's Decisions API.

Why a second model at all, and why this one specifically:

Jev is not a chat model and does not generate text. You hand it a `state`
(the question, the answer, and every tool result the answer was built from)
plus a set of typed `questions`, and it returns one typed answer per question
in a single forward pass - a probability for a yes/no ("noul"), or a winner
plus a calibrated probability distribution for a "choice". Because the set of
valid outputs is fixed by the request schema, it cannot invent an option or
break our parsing the way a chat model asked for JSON can; it can still pick
the wrong option, so this is a *check*, never a guarantee.

That property is what makes it usable here. This repo's whole posture is that
a confident wrong answer is the worst failure mode (see AGENTS.md on
`decide()`), and that confidence numbers must never be LLM-invented prose (see
er.agent.models.Evidence). Asking a chat model "is this answer correct, 0-100?"
would violate both. Asking Jev a fixed list of typed questions gives calibrated
probabilities from a schema we control, and the verified/partial/unverified
badge is then derived from those probabilities by the deterministic, thresholds
-in-config rule in `classify()` below - the same "retuning is a config edit"
principle as er.matching.scoring.

Endpoint shape (verified live against the API, 2026-09-22):

    POST https://openrouter.ai/api/alpha/decisions
    {"model": "typesafe/jev-1.13", "state": <str|obj|list>,
     "questions": {"<key>": {"type": "noul"|"choice"|"score",
                             "instructions": "...", "criteria": ...}}}
 -> {"model": ..., "answers": {"<key>": {"type": "noul", "noul": 0.92}},
     "usage": {"input_tokens": ..., "output_tokens": ..., "cost": ...}}

Note this is *not* /api/v1/chat/completions - it is a different path prefix
from `agent.openrouter_base_url`, which is why the URL is its own config
field rather than a suffix appended to that base.

This module performs no entity resolution and never edits the answer: a
verification failure downgrades a badge, it does not rewrite or withhold what
the agent said. Any transport/parse error yields status "unavailable" (we did
not check), which is deliberately distinct from "unverified" (we checked and
it did not hold) - the same no-signal/false distinction er.matching.features
draws.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import httpx

from er.config import AppConfig, VerifierConfig

from .models import AskResult, Verification, VerificationCheck
from .payloads import SHRINK_PASSES, shrink
from .retry import error_message, is_transient, timeout

# The fixed question set. Keeping it here (rather than assembling it per call)
# means every answer is verified against exactly the same criteria, so two
# badges are comparable. Each `noul` is phrased so that 1.0 is the *good*
# outcome except `contradicted`, which is inverted on purpose - a question
# that can only ever be answered "no" by a well-behaved answer is a much
# sharper signal than folding it into "is it grounded".
NOUL_CHECKS: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "grounded",
        "Claims match the records",
        "Is every factual claim in `answer` directly supported by the tool results in `tool_calls`?",
        "Every entity name, identifier, date, count, status and relationship stated in the answer "
        "appears in the tool results, or follows directly from them.",
        "At least one factual claim in the answer is absent from the tool results, or asserts more "
        "than they show.",
    ),
    (
        "not_contradicted",
        "No conflict with the records",
        "Does `answer` avoid stating anything that conflicts with the tool results in `tool_calls`?",
        "Nothing in the answer disagrees with the tool results.",
        "A value in the answer disagrees with the same field in the tool results (a different name, "
        "identifier, status, date, count or relationship direction).",
    ),
    (
        "citations_supported",
        "Citations point at the right evidence",
        "Does each [n] marker in `answer` point to an entry in `citations` whose evidence actually "
        "substantiates the claim that marker is attached to?",
        "Every marker is attached to a claim that the cited evidence record's source and criteria "
        "genuinely cover.",
        "A marker is attached to a claim the cited evidence does not cover, or a specific factual "
        "claim carries no marker at all.",
    ),
    (
        "scope_respected",
        "Stays inside the retrieved data",
        "Does `answer` stay within what the tool results contain, without adding outside knowledge "
        "about these entities?",
        "The answer only reports what the tools returned, and says so plainly when the data is "
        "incomplete or ambiguous.",
        "The answer adds facts about these entities from general world knowledge, or presents an "
        "inference as if it were a retrieved record.",
    ),
)

VERDICT_CRITERIA: dict[str, str] = {
    "supported": "The tool results substantiate the whole answer.",
    "partially_supported": "The tool results substantiate the main claim, but some detail in the "
    "answer is unsupported, over-stated, or not covered by any lookup.",
    "unsupported": "The tool results do not substantiate the answer's main claim, or contradict it.",
}

# Shown in the CLI/web badge. Deliberately modest: Jev checked this answer
# against the records it was built from, which is not the same as the records
# being right, and not a claim that the answer is true in the world.
STATUS_COPY: dict[str, tuple[str, str]] = {
    "verified": (
        "Verified",
        "Every claim in this answer was checked against the records the agent retrieved, and matched.",
    ),
    "partial": (
        "Partially verified",
        "The main claim holds up against the retrieved records, but at least one check was weak - "
        "read the detail before relying on it.",
    ),
    "unverified": (
        "Not verified",
        "The retrieved records do not support this answer as written. Treat it as unconfirmed.",
    ),
    "unavailable": (
        "Not checked",
        "The verification model could not be reached, so this answer has not been checked either way.",
    ),
}


def build_questions() -> dict[str, dict[str, Any]]:
    """The Decisions API `questions` object. `criteria` is required for every
    type: a true/false object for noul, a key->description object for choice."""
    questions: dict[str, dict[str, Any]] = {
        key: {
            "type": "noul",
            "instructions": instructions,
            "criteria": {"true": when_true, "false": when_false},
        }
        for key, _label, instructions, when_true, when_false in NOUL_CHECKS
    }
    questions["verdict"] = {
        "type": "choice",
        "instructions": "Overall, how well do the tool results in `tool_calls` support `answer`?",
        "criteria": VERDICT_CRITERIA,
    }
    return questions


def build_state(
    question: str,
    result: AskResult,
    tool_calls: list[dict[str, Any]],
    max_chars: int,
) -> dict[str, Any]:
    """Assemble what Jev judges: the question, the answer, each citation
    resolved to the evidence record behind it, and the tool results.

    Citations are resolved here rather than left as opaque `ev_` ids so the
    `citations_supported` check has something to judge - an id alone says
    nothing about whether the cited lookup covers the claim.

    Jev's input limit is 32,768 tokens (measured), so oversized payloads are
    shrunk breadth-first through SHRINK_PASSES until they fit, and only dropped
    outright if even the hardest pass doesn't. Both paths leave a marker,
    because the thing that must never happen here is the verifier judging an
    answer against records we quietly withheld from it and reporting the
    resulting mismatch as the *answer's* fault.
    """
    base: dict[str, Any] = {
        "question": question,
        "answer": result.answer,
        "citations": [
            {
                "marker": c.marker,
                "evidence_id": c.evidence_id,
                "evidence": result.evidence[c.evidence_id].model_dump(
                    include={"source", "criteria", "result_count", "source_timestamp", "warnings"}
                ),
            }
            for c in result.citations
            if c.evidence_id in result.evidence
        ],
        "tool_calls": [dict(call) for call in tool_calls],
    }
    if len(json.dumps(base)) <= max_chars:
        return base

    for max_items in SHRINK_PASSES:
        state = dict(base)
        state["tool_calls"] = [shrink(call, max_items) for call in base["tool_calls"]]
        if len(json.dumps(state)) <= max_chars:
            return state

    # Last resort: a payload that is still too large even one-item-per-list.
    # Keep every call visible so a dropped result can never look like a call
    # that was never made.
    state = dict(base)
    state["tool_calls"] = [
        {
            "tool": call.get("tool"),
            "arguments": call.get("arguments"),
            "result_omitted": "dropped to fit the verifier's input budget",
        }
        for call in base["tool_calls"]
    ]
    return state


async def _post_decisions(
    cfg: AppConfig, state: dict[str, Any], questions: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    vcfg = cfg.agent.verifier
    async with httpx.AsyncClient(timeout=timeout(vcfg.timeout_seconds, vcfg.connect_timeout_seconds)) as http:
        resp = await http.post(
            vcfg.decisions_url,
            headers={"Authorization": f"Bearer {cfg.openrouter_api_key}"},
            json={"model": vcfg.model, "state": state, "questions": questions},
        )
        resp.raise_for_status()
        return resp.json()


def _noul(answers: dict[str, Any], key: str) -> float | None:
    answer = answers.get(key)
    if not isinstance(answer, dict):
        return None
    value = answer.get("noul")
    return float(value) if isinstance(value, (int, float)) else None


def classify(answers: dict[str, Any], vcfg: VerifierConfig) -> tuple[str, list[VerificationCheck], str | None, float | None]:
    """Turn Jev's typed answers into a badge status, deterministically.

    Every threshold below is a named field in `config/dev.yaml`; nothing here
    is a magic number, so tightening the badge is a config edit, not a code
    change - same rule as er.matching.scoring. A missing answer (the model
    skipped a key, or the payload was malformed) is treated as "no signal" and
    reported as `passed=None`, never silently as a pass.
    """
    thresholds = {
        "grounded": vcfg.grounded_min,
        "not_contradicted": vcfg.not_contradicted_min,
        "citations_supported": vcfg.citations_supported_min,
        "scope_respected": vcfg.scope_respected_min,
    }
    checks = []
    for key, label, *_ in NOUL_CHECKS:
        probability = _noul(answers, key)
        checks.append(
            VerificationCheck(
                key=key,
                label=label,
                probability=probability,
                threshold=thresholds[key],
                passed=None if probability is None else probability >= thresholds[key],
            )
        )

    verdict_answer = answers.get("verdict") if isinstance(answers.get("verdict"), dict) else {}
    verdict = verdict_answer.get("choice")
    verdict_confidence = verdict_answer.get("confidence")
    verdict_confidence = float(verdict_confidence) if isinstance(verdict_confidence, (int, float)) else None

    not_contradicted = _noul(answers, "not_contradicted")

    # The rule, and why it is shaped this way (measured - see
    # experiments/006-jev-answer-verification.md):
    #
    # `verdict` leads, because it is the one question that weighs the answer as
    # a whole; the four nouls then refine it. The single exception is
    # `not_contradicted`, which vetoes: an answer that conflicts with the
    # records is unverified no matter how the holistic verdict reads, because a
    # confidently wrong answer is the failure this project optimizes hardest
    # against (AGENTS.md, on decide()). Note the asymmetry is deliberate -
    # merely *unsupported* extra detail is a "partial", not an "unverified";
    # only a conflict is disqualifying.
    #
    # Testing the veto first is what makes that true: order it the other way
    # and a contradiction could be outvoted by three soft passes.
    # An incomplete check set is "unavailable", not a middling "partial": we
    # did not get the reading, so we have nothing to report about it either
    # way. Downgrading silently would let a transport hiccup read as a
    # judgement about the answer.
    if verdict is None or any(check.passed is None for check in checks):
        status = "unavailable"
    elif verdict == "unsupported" or not_contradicted < vcfg.not_contradicted_floor:
        status = "unverified"
    elif verdict == "supported" and all(check.passed for check in checks):
        status = "verified"
    else:
        status = "partial"

    return status, checks, verdict, verdict_confidence


def _after(attempts: int) -> str:
    return f" after {attempts} attempts" if attempts > 1 else ""


def unavailable(reason: str) -> Verification:
    headline, detail = STATUS_COPY["unavailable"]
    return Verification(status="unavailable", headline=headline, detail=detail, reason=reason)


async def _backoff(seconds: float) -> None:
    # Its own function so tests can skip the wait without patching asyncio.
    await asyncio.sleep(seconds)


async def _post_with_retry(
    cfg: AppConfig, state: dict[str, Any], questions: dict[str, dict[str, Any]]
) -> tuple[dict[str, Any], int]:
    """One Decisions call, retried on transient failures (er.agent.retry).
    Returns the payload and how many attempts it took; raises the last error
    if every attempt failed or the failure was not transient."""
    vcfg = cfg.agent.verifier
    attempts = vcfg.retries + 1
    for attempt in range(1, attempts + 1):
        try:
            return await _post_decisions(cfg, state, questions), attempt
        except Exception as exc:
            if attempt == attempts or not is_transient(exc):
                exc.add_note(f"attempts={attempt}")
                raise
            await _backoff(vcfg.retry_backoff_seconds * 2 ** (attempt - 1))
    raise AssertionError("unreachable")


# Below this the state is barely more than the answer itself; if even that
# is over the token limit, the check genuinely can't run.
MIN_STATE_CHARS = 6_000


def _too_many_tokens(exc: httpx.HTTPStatusError) -> bool:
    return exc.response.status_code == 400 and "max_tokens_exceeded" in exc.response.text


def _attempts_of(exc: BaseException) -> int:
    for note in getattr(exc, "__notes__", []):
        if note.startswith("attempts="):
            return int(note.split("=", 1)[1])
    return 1


async def verify_answer(
    cfg: AppConfig,
    question: str,
    result: AskResult,
    tool_calls: list[dict[str, Any]],
) -> Verification:
    """Check a finished answer against the tool results it was built from.

    Never raises: a verifier that is disabled, unreachable, slow, or returning
    something unexpected must degrade the badge to "not checked", not take the
    answer down with it.
    """
    vcfg = cfg.agent.verifier
    if not vcfg.enabled:
        return unavailable("Answer verification is disabled in config.")
    if not result.answer.strip():
        return unavailable("There was no answer text to check.")

    started = time.monotonic()
    budget = vcfg.max_state_chars
    while True:
        state = build_state(question, result, tool_calls, budget)
        try:
            payload, attempts = await _post_with_retry(cfg, state, build_questions())
            break
        except httpx.HTTPStatusError as exc:
            # The char budget is a proxy for Jev's token limit; if a payload
            # tokenizes denser than expected, halve what was actually sent and
            # try again rather than leave the answer unchecked. Halving the
            # *state*, not the budget: the shrinker moves in coarse steps, so a
            # state already well under its budget wouldn't get any smaller.
            sent = len(json.dumps(state, default=str))
            if _too_many_tokens(exc) and sent > MIN_STATE_CHARS:
                budget = sent // 2
                continue
            detail = error_message(exc.response)
            return unavailable(
                f"The verification model returned HTTP {exc.response.status_code}{_after(_attempts_of(exc))}"
                + (f": {detail}." if detail else ".")
            )
        except Exception as exc:  # noqa: BLE001 - a badge must never break the answer
            return unavailable(
                f"The verification model could not be reached{_after(_attempts_of(exc))} ({type(exc).__name__})."
            )
    elapsed_ms = int((time.monotonic() - started) * 1000)

    answers = payload.get("answers")
    if not isinstance(answers, dict):
        return unavailable("The verification model returned an unrecognised response.")

    status, checks, verdict, verdict_confidence = classify(answers, vcfg)
    headline, detail = STATUS_COPY[status]
    return Verification(
        status=status,
        headline=headline,
        detail=detail,
        model=payload.get("model") or vcfg.model,
        checks=checks,
        verdict=verdict,
        verdict_confidence=verdict_confidence,
        latency_ms=elapsed_ms,
        attempts=attempts,
        usage=payload.get("usage") if isinstance(payload.get("usage"), dict) else None,
        reason="The verification model did not return every check." if status == "unavailable" else None,
    )
