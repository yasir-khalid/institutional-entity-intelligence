"""Shared test guards."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_live_decisions_api(monkeypatch):
    """er.config loads .env on import, and the Jev verifier is on by default,
    so any test that drives er.agent.orchestrator.ask() to completion would
    otherwise make a real, billed call to OpenRouter's Decisions API - which
    is exactly what happened silently in test_agent_tools until this guard
    existed. Unit tests must not touch live services (AGENTS.md).

    This makes the transport raise, which verify_answer() already turns into
    an "unavailable" badge - the same path a real outage takes. A test that
    wants a specific verdict stubs verify_answer itself."""
    import er.agent.verifier as verifier

    async def _refuse(*_args, **_kwargs):
        raise RuntimeError("unit tests must not call the live Decisions API")

    monkeypatch.setattr(verifier, "_post_decisions", _refuse)
