"""Rendering tests for er.cli.ask_render - a Console over StringIO, no live
services, same pattern as tests/test_entity_render.py."""

from __future__ import annotations

import io

from rich.console import Console

from er.agent.models import AskResult, Citation, Evidence, Verification, VerificationCheck
from er.cli.ask_render import probability_meter, render_result, render_verification


def _console() -> tuple[Console, io.StringIO]:
    buffer = io.StringIO()
    return Console(file=buffer, width=100, no_color=True), buffer


def _verification(status: str = "verified", **kwargs) -> Verification:
    return Verification(
        status=status,
        headline=kwargs.pop("headline", "Verified"),
        detail=kwargs.pop("detail", "Every claim was checked against the records."),
        model="typesafe/jev-1.13-20260917",
        latency_ms=412,
        verdict="supported",
        checks=[
            VerificationCheck(key="grounded", label="Claims match the records", probability=0.95, threshold=0.85, passed=True),
            VerificationCheck(key="scope_respected", label="Stays inside the retrieved data", probability=0.4, threshold=0.75, passed=False),
            VerificationCheck(key="citations_supported", label="Citations point at the right evidence", threshold=0.75),
        ],
        **kwargs,
    )


def test_meter_is_fixed_width_so_stacked_bars_share_one_scale():
    assert len(probability_meter(0.0)) == len(probability_meter(1.0)) == len(probability_meter(None)) == 12
    assert probability_meter(1.0).count("█") == 12
    assert probability_meter(0.0).count("█") == 0


def test_meter_clamps_out_of_range_values():
    assert probability_meter(1.4).count("█") == 12
    assert probability_meter(-0.2).count("█") == 0


def test_verification_panel_shows_every_check_and_its_reading():
    console, buffer = _console()
    render_verification(console, _verification())
    out = buffer.getvalue()
    assert "Verified" in out
    assert "Claims match the records" in out
    assert "0.95" in out
    assert "0.40" in out
    assert "typesafe/jev-1.13-20260917" in out
    assert "412 ms" in out


def test_a_check_with_no_reading_reads_as_no_signal_not_as_zero():
    console, buffer = _console()
    render_verification(console, _verification())
    assert "no signal" in buffer.getvalue()


def test_unavailable_says_it_was_not_checked_rather_than_that_it_failed():
    console, buffer = _console()
    render_verification(
        console,
        Verification(
            status="unavailable",
            headline="Not checked",
            detail="The verification model could not be reached, so this answer has not been checked either way.",
            reason="The verification model returned HTTP 503.",
        ),
    )
    out = buffer.getvalue()
    assert "Not checked" in out
    assert "HTTP 503" in out
    assert "Not verified" not in out


def test_no_verification_prints_nothing():
    console, buffer = _console()
    render_verification(console, None)
    assert buffer.getvalue() == ""


def test_result_renders_answer_badge_and_evidence_together():
    evidence = Evidence(
        evidence_id="ev_abc1234567",
        source="GLEIF entity record (exact LEI lookup)",
        source_timestamp="2026-08-01",
        fact_type="lookup",
        criteria=["Entity ID = 5493001KJTIIGC8Y1R12"],
        result_count=1,
        query_hash="a1b2c3d4e5f6",
    )
    result = AskResult(
        answer="Bloomberg Finance L.P. is ACTIVE [1].",
        citations=[Citation(marker=1, evidence_id="ev_abc1234567")],
        evidence={"ev_abc1234567": evidence},
        verification=_verification(),
    )
    console, buffer = _console()
    render_result(console, result)
    out = buffer.getvalue()
    assert "Bloomberg Finance L.P." in out
    assert "Verified" in out
    assert "GLEIF entity record" in out

