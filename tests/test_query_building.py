"""Unit tests for build_candidate_query - pure function, no live OpenSearch needed."""

import pytest

from er.retrieval.candidates import build_candidate_query


def _name_should_clauses(body):
    """The name-matching `should` clauses, regardless of whether a country boost
    wraps them in a `boosting` query (soft mode) or not (no country / strict)."""
    query = body["query"]
    if "boosting" in query:
        return query["boosting"]["positive"]["bool"]["should"]
    return query["bool"]["should"]


def test_no_country_has_no_country_clause():
    body = build_candidate_query("Acme Corp", None, size=20)
    assert "boosting" not in body["query"]
    should = _name_should_clauses(body)
    assert not any("term" in clause and "legal_country" in clause.get("term", {}) for clause in should)


def test_soft_mode_is_a_boosting_query_not_a_hard_filter():
    # Regression test for a real bug: country used to be a `filter` clause, which
    # silently excluded the true entity whenever the source's country field was
    # wrong (confirmed live: "NORTH ROCK CAPITAL MANAGEMENT (UK) LLP" vanished from
    # the candidate pool entirely when queried with the wrong --country IE). Soft
    # mode (the default) must never exclude - only boost matches and penalize
    # mismatches via `boosting`, never a `filter`.
    body = build_candidate_query("Acme Corp", "GB", size=20)
    assert "filter" not in body["query"].get("bool", {})
    assert "boosting" in body["query"]

    should = _name_should_clauses(body)
    country_clauses = [c for c in should if "term" in c and "legal_country" in c["term"]]
    assert len(country_clauses) == 1
    assert country_clauses[0]["term"]["legal_country"]["value"] == "GB"
    assert country_clauses[0]["term"]["legal_country"]["boost"] > 0

    negative = body["query"]["boosting"]["negative"]
    assert negative["bool"]["must_not"] == [{"term": {"legal_country": "GB"}}]
    assert 0 < body["query"]["boosting"]["negative_boost"] < 1


def test_strict_mode_uses_a_hard_filter():
    body = build_candidate_query("Acme Corp", "GB", size=20, country_mode="strict")
    assert "boosting" not in body["query"]
    assert body["query"]["bool"]["filter"] == [{"term": {"legal_country": "GB"}}]


def test_invalid_country_mode_raises():
    with pytest.raises(ValueError):
        build_candidate_query("Acme Corp", "GB", size=20, country_mode="bogus")


def test_minimum_should_match_is_one_regardless_of_country():
    # A name-only match must still be enough to retrieve a candidate - adding the
    # country clause/boosting wrapper must never raise this requirement.
    with_country = build_candidate_query("Acme Corp", "GB", size=20)
    without_country = build_candidate_query("Acme Corp", None, size=20)
    assert with_country["query"]["boosting"]["positive"]["bool"]["minimum_should_match"] == 1
    assert without_country["query"]["bool"]["minimum_should_match"] == 1


def test_country_is_uppercased():
    body = build_candidate_query("Acme Corp", "gb", size=20)
    should = _name_should_clauses(body)
    country_clauses = [c for c in should if "term" in c and "legal_country" in c["term"]]
    assert country_clauses[0]["term"]["legal_country"]["value"] == "GB"


def test_country_aliases_are_normalized():
    # "UK"/"United Kingdom" don't exist in GLEIF's stored data (which uses ISO
    # alpha-2 "GB") - without alias resolution, --country UK would silently fail to
    # narrow anything at all.
    for alias in ["UK", "United Kingdom", "great britain"]:
        body = build_candidate_query("Acme Corp", alias, size=20)
        should = _name_should_clauses(body)
        country_clauses = [c for c in should if "term" in c and "legal_country" in c["term"]]
        assert country_clauses[0]["term"]["legal_country"]["value"] == "GB", alias
