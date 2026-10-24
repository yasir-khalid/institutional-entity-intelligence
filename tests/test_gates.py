"""The deterministic preconditions in er.agent.gates, plus the unit contract on
er.knowledge.formulas they rely on. Pure functions, no services."""

from __future__ import annotations

from er.agent.gates import first_failure, validate_facts
from er.agent.models import Derivation, Fact, FactAddress
from er.knowledge.formulas import FORMULAS


def _fact(fact_id, value, *, unit=None, as_of=None, source="SEC 13F filing", provenance="SOURCE_FACT"):
    return Fact(
        fact_id=fact_id,
        evidence_id="ev_1",
        subject="cik:0001",
        predicate="position.value",
        value=value,
        unit=unit,
        as_of=as_of,
        provenance_class=provenance,
        address=FactAddress(source=source, document_id="0001", locator=f"ROW:{fact_id}", field="value"),
    )


def _gate(checks, key):
    return next(check for check in checks if check.key == key)


def test_formula_unit_contract():
    assert FORMULAS["sum"].unit_error(["USD", "USD"]) is None
    assert FORMULAS["sum"].unit_error(["USD", "shares"]) is not None
    assert FORMULAS["sum"].unit_error(["USD", None]) is not None
    assert FORMULAS["percent_change"].unit_error(["USD", "USD"]) is None
    assert FORMULAS["percent_change"].output_unit(["USD", "USD"]) == "percent"
    assert FORMULAS["ratio"].unit_error(["USD", "USD"]) is None
    assert FORMULAS["ratio"].output_unit(["USD", "USD"]) == "ratio"
    assert FORMULAS["sum"].output_unit(["shares", "shares"]) == "shares"


def test_a_clean_derivation_passes_every_gate():
    facts = {
        "f_a": _fact("f_a", 100, unit="USD", as_of="2026-03-31"),
        "f_b": _fact("f_b", 40, unit="USD", as_of="2026-03-31"),
        "f_d": _fact("f_d", 60, unit="USD", as_of="2026-03-31", provenance="DERIVED_FACT"),
    }
    derivations = {"f_d": Derivation(fact_id="f_d", formula_id="difference", expression="a - b", inputs=["f_a", "f_b"])}

    checks = validate_facts(facts, derivations)

    assert len(checks) == 6
    assert all(check.passed for check in checks), first_failure(checks)


def test_each_gate_fails_closed_on_its_own_problem():
    good = {
        "f_a": _fact("f_a", 100, unit="USD", as_of="2026-03-31"),
        "f_b": _fact("f_b", 40, unit="USD", as_of="2026-03-31"),
        "f_d": _fact("f_d", 60, unit="USD", as_of="2026-03-31", provenance="DERIVED_FACT"),
    }
    derivation = Derivation(fact_id="f_d", formula_id="difference", expression="a - b", inputs=["f_a", "f_b"])

    unaddressed = {**good, "f_a": _fact("f_a", 100, unit="USD", as_of="2026-03-31", source="")}
    assert not _gate(validate_facts(unaddressed, {"f_d": derivation}), "addressed").passed

    undated = {**good, "f_a": _fact("f_a", 100, unit="USD")}
    assert not _gate(validate_facts(undated, {"f_d": derivation}), "dated").passed

    dangling = {"f_d": derivation}  # f_a/f_b missing
    assert not _gate(validate_facts({"f_d": good["f_d"]}, dangling), "derivation_inputs").passed

    unmarked = {**good, "f_d": _fact("f_d", 60, unit="USD", as_of="2026-03-31")}
    assert not _gate(validate_facts(unmarked, {"f_d": derivation}), "provenance").passed

    mismatched_units = {**good, "f_b": _fact("f_b", 40, unit="shares", as_of="2026-03-31")}
    assert not _gate(validate_facts(mismatched_units, {"f_d": derivation}), "units").passed

    tampered = {**good, "f_d": _fact("f_d", 61, unit="USD", as_of="2026-03-31", provenance="DERIVED_FACT")}
    recompute = _gate(validate_facts(tampered, {"f_d": derivation}), "recomputes")
    assert not recompute.passed and "61" in recompute.message


def test_first_failure_names_the_gate_and_the_reason():
    facts = {"f_a": _fact("f_a", 100, unit="USD")}
    assert first_failure(validate_facts(facts, {})) == "Every measured value is dated: measured facts without an as-of date: f_a"
    assert first_failure(validate_facts({}, {})) is None
