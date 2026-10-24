"""SEC XBRL: the parse boundary (raw -> cleaned), the point-in-time read, and
the agent tool built on both - driven from a MemoryStore, no live services."""

import pytest

from er.agent.gates import first_failure, validate_facts
from er.agent.tools import get_issuer_financials
from er.config import load_config
from er.datasources.sec_xbrl.ingest import parse_company_facts
from er.entity.xbrl import balance_check, known_on, normalise_unit
from er.serving.store import XBRL_FACTS, XBRL_ISSUERS, MemoryStore


PAYLOAD = {
    "cik": 320193,
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "Assets": {
                "label": "Assets",
                "units": {
                    "USD": [
                        {"end": "2024-09-28", "val": 364980000000, "fy": 2024, "fp": "FY",
                         "form": "10-K", "filed": "2024-11-01", "accn": "0000320193-24-000123"},
                        {"end": "2025-09-27", "val": 359240000000, "fy": 2025, "fp": "FY",
                         "form": "10-K", "filed": "2025-10-31", "accn": "0000320193-25-000079"},
                    ]
                },
            },
            "LiabilitiesAndStockholdersEquity": {
                "label": "Liabilities and Stockholders' Equity",
                "units": {"USD": [{"end": "2025-09-27", "val": 359240000000, "form": "10-K",
                                   "filed": "2025-10-31", "accn": "0000320193-25-000079"}]},
            },
            "Revenues": {"units": {"USD": [{"end": "2025-09-27", "start": "2024-09-29", "val": 391035000000,
                                            "form": "10-K", "filed": "2025-10-31",
                                            "accn": "0000320193-25-000079"}]}},
            "EarningsPerShareDiluted": {"units": {"USD/shares": [{"end": "2025-09-27", "val": 6.11,
                                                                  "form": "10-K", "filed": "2025-10-31"}]}},
            # Not in the configured tag list, so it must not reach the output.
            "UnregisteredConcept": {"units": {"USD": [{"end": "2025-09-27", "val": 1,
                                                       "form": "10-K", "filed": "2025-10-31"}]}},
        }
    },
}


def _provenance():
    return {"source_file": "companyfacts/CIK0000320193.json", "snapshot_date": "2026-01-01",
            "ingested_at": "2026-01-01T00:00:00+00:00"}


def test_parse_keeps_only_configured_tags_and_the_filing_date_boundary():
    cfg = load_config()
    rows, issuer = parse_company_facts(cfg, "0000320193", PAYLOAD, _provenance())

    assert issuer["cik"] == "0000320193"
    assert issuer["entity_name"] == "Apple Inc."
    tags = sorted({row["tag"] for row in rows})
    assert "UnregisteredConcept" not in tags
    assert tags == ["Assets", "EarningsPerShareDiluted", "LiabilitiesAndStockholdersEquity", "Revenues"]

    assets = [row for row in rows if row["tag"] == "Assets"]
    assert [row["period_end"] for row in assets] == ["2024-09-28", "2025-09-27"]
    assert assets[1]["filed"] == "2025-10-31"
    assert assets[1]["accession_number"] == "0000320193-25-000079"
    assert assets[1]["value"] == 359240000000.0
    assert all(row["source_file"] and row["ingested_at"] for row in rows)


def test_parse_drops_an_observation_with_no_filing_date():
    payload = {"entityName": "X", "facts": {"us-gaap": {"Assets": {"units": {"USD": [
        {"end": "2025-09-27", "val": 5, "form": "10-K"},  # no `filed`
        {"end": "2025-09-27", "val": 6, "form": "10-K", "filed": "2025-10-31"},
    ]}}}}}
    rows, _ = parse_company_facts(load_config(), "0000000001", payload, _provenance())
    assert [row["value"] for row in rows] == [6.0]


def test_point_in_time_sees_only_what_had_been_filed():
    rows = [
        {"period_start": None, "period_end": "2024-09-28", "filed": "2024-11-01", "value": 1},
        {"period_start": None, "period_end": "2025-09-27", "filed": "2025-10-31", "value": 2},
    ]
    assert [row["value"] for row in known_on(rows, "2025-01-01")] == [1]
    assert [row["value"] for row in known_on(rows, "2025-12-31")] == [1, 2]
    assert [row["value"] for row in known_on(rows, None)] == [1, 2]

    # A restatement: the same period reported again later wins for a date past
    # the amendment, but not before it.
    amended = rows[:1] + [{"period_start": None, "period_end": "2024-09-28",
                           "filed": "2025-03-01", "value": 9}]
    assert [row["value"] for row in known_on(amended, "2025-01-01")] == [1]
    assert [row["value"] for row in known_on(amended, "2025-06-01")] == [9]


def test_normalise_unit_maps_xbrl_units_to_the_platform_vocabulary():
    assert normalise_unit("USD") == "USD"
    assert normalise_unit("shares") == "shares"
    assert normalise_unit("USD/shares") == "USD_per_share"
    assert normalise_unit("pure") == "ratio"
    assert normalise_unit("EUR") == "EUR"  # unknown units pass through unchanged


def test_balance_check_reports_none_when_a_side_is_missing():
    from er.entity.xbrl import Series

    only_assets = [Series("0000320193", "Apple Inc.", "Assets", "USD",
                          [{"period_end": "2025-09-27", "filed": "2025-10-31", "value": 100}])]
    assert balance_check(only_assets) is None


def _series_document(cik, tag, unit, observations, entity_name="Apple Inc."):
    return {"cik": cik, "tag": tag, "unit": unit, "entity_name": entity_name, "observations": observations}


def _store_with_apple():
    store = MemoryStore()
    store.put(XBRL_ISSUERS, "0000320193", {"cik": "0000320193", "entity_name": "Apple Inc.",
                                           "tickers": ["AAPL"], "former_names": [], "sic": "3571"})
    assets = [
        {"period_end": "2024-09-28", "period_start": None, "form": "10-K", "filed": "2024-11-01",
         "accession_number": "0000320193-24-000123", "value": 364980000000},
        {"period_end": "2025-09-27", "period_start": None, "form": "10-K", "filed": "2025-10-31",
         "accession_number": "0000320193-25-000079", "value": 359240000000},
    ]
    store.put(XBRL_FACTS, "0000320193:Assets:USD", _series_document("0000320193", "Assets", "USD", assets))
    store.put(XBRL_FACTS, "0000320193:LiabilitiesAndStockholdersEquity:USD",
              _series_document("0000320193", "LiabilitiesAndStockholdersEquity", "USD", [
                  {"period_end": "2025-09-27", "filed": "2025-10-31", "value": 359240000000,
                   "accession_number": "0000320193-25-000079"}]))
    return store


def test_tool_resolves_by_ticker_and_cites_dated_as_filed_values():
    result = get_issuer_financials(_store_with_apple(), "AAPL", id_type="ticker", tag="Assets")

    assert result.data["found"] is True
    assert result.data["issuer"]["cik"] == "0000320193"
    assert result.data["series"][0]["latest_value"] == 359240000000
    assert result.data["series"][0]["latest_period_end"] == "2025-09-27"
    assert ["2024-09-28", "2025-09-27"] == [row["period_end"] for row in result.data["series"][0]["observations"]]

    # Every measured value is addressed and dated at the source; the balance-sheet
    # identity is checked, and the whole result satisfies the submission gates.
    assets_facts = [fact for fact in result.facts if fact.predicate == "xbrl.Assets"]
    assert all(fact.as_of and fact.address.document_id for fact in assets_facts)
    assert result.data["checks"][0]["passed"] is True
    checks = validate_facts({fact.fact_id: fact for fact in result.facts},
                            {d.fact_id: d for d in result.derivations})
    assert all(check.passed for check in checks), first_failure(checks)


def test_tool_derives_a_period_change_and_flags_a_broken_identity():
    store = _store_with_apple()
    store.put(XBRL_FACTS, "0000320193:LiabilitiesAndStockholdersEquity:USD",
              _series_document("0000320193", "LiabilitiesAndStockholdersEquity", "USD", [
                  {"period_end": "2025-09-27", "filed": "2025-10-31", "value": 1,
                   "accession_number": "0000320193-25-000079"}]))

    result = get_issuer_financials(store, "0000320193", tag="Assets")

    change = next(item for item in result.data["derived"] if item["predicate"] == "xbrl.Assets.percent_change")
    change_fact = next(fact for fact in result.facts if fact.fact_id == change["fact_id"])
    assert change_fact.provenance_class == "DERIVED_FACT"
    assert change_fact.unit == "percent"

    check = result.data["checks"][0]
    assert check["passed"] is False
    assert any("identity does not hold" in warning for evidence in result.evidence for warning in evidence.warnings)


def test_tool_reports_unknown_tag_and_unknown_issuer_without_guessing():
    store = _store_with_apple()
    unknown_tag = get_issuer_financials(store, "0000320193", tag="NotAConcept")
    assert unknown_tag.data["found"] is False
    assert "Assets" in unknown_tag.data["available_tags"]
    assert not unknown_tag.facts

    unknown_issuer = get_issuer_financials(store, "9999999999", tag="Assets")
    assert unknown_issuer.data["found"] is False
    assert not unknown_issuer.facts


def test_tool_satisfies_the_dated_gate_only_because_xbrl_values_carry_period_end():
    result = get_issuer_financials(_store_with_apple(), "0000320193", tag="Assets")
    usd = [fact for fact in result.facts if fact.unit == "USD"]
    assert usd and all(fact.as_of for fact in usd)
