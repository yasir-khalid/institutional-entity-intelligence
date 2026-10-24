"""Deterministic, fail-closed preconditions on an answer's facts.

These are the arithmetic-and-provenance invariants that must hold for an answer
to be worth asking a verifier about. They are deliberately *not* confidence
scores: a confidence score lets a wrong-but-plausible answer through with a
slightly lower number attached, whereas a gate refuses the submission and hands
the model a typed reason to fix. The report on trustworthy financial RAG makes
exactly this point - validation and invariant checks, not self-reported
confidence, are what keep a derived figure honest.

Every gate is pure: given the facts and derivations an answer used, it returns a
GateCheck. `validate_facts()` runs them all; `first_failure()` renders the one
reason to hand back to the model. Nothing here reads a live service, so the
whole contract is unit-testable (tests/test_gates.py).
"""

from __future__ import annotations

from collections.abc import Sequence

from er.knowledge.formulas import FORMULAS

from .models import Derivation, Fact, GateCheck

# Units that describe a measured quantity: such a value is only meaningful with
# the date it was observed. A bare count (a result_count, a holding_count) is
# deliberately not in here - it belongs to the response, not to a point in time.
_DATED_UNITS = frozenset({"USD", "shares", "percent", "ratio", "points"})

# A recomputation must match the stored value to within this; formulas round, so
# an exact comparison would reject a correctly-computed percentage.
_TOLERANCE = 1e-6

_MAX_LISTED = 5


def _sample(ids: Sequence[str]) -> str:
    ordered = sorted(ids)
    shown = ", ".join(ordered[:_MAX_LISTED])
    return shown if len(ordered) <= _MAX_LISTED else f"{shown}, +{len(ordered) - _MAX_LISTED} more"


def _addresses(facts: dict[str, Fact], derivations: dict[str, Derivation]) -> GateCheck:
    missing = [
        fact_id
        for fact_id, fact in facts.items()
        if not (fact.address.source and fact.address.document_id and fact.address.locator)
    ]
    return GateCheck(
        key="addressed",
        label="Every fact has a source address",
        passed=not missing,
        message=f"facts without a complete source address: {_sample(missing)}" if missing else "",
    )


def _dated(facts: dict[str, Fact], derivations: dict[str, Derivation]) -> GateCheck:
    undated = [
        fact_id
        for fact_id, fact in facts.items()
        if fact.unit in _DATED_UNITS and not fact.as_of
    ]
    return GateCheck(
        key="dated",
        label="Every measured value is dated",
        passed=not undated,
        message=f"measured facts without an as-of date: {_sample(undated)}" if undated else "",
    )


def _derivation_inputs(facts: dict[str, Fact], derivations: dict[str, Derivation]) -> GateCheck:
    dangling: list[str] = []
    for derivation in derivations.values():
        for input_id in derivation.inputs:
            if input_id not in facts:
                dangling.append(f"{derivation.fact_id}<-{input_id}")
    return GateCheck(
        key="derivation_inputs",
        label="Every derivation's input facts are present",
        passed=not dangling,
        message=f"dangling derivation inputs: {_sample(dangling)}" if dangling else "",
    )


def _provenance(facts: dict[str, Fact], derivations: dict[str, Derivation]) -> GateCheck:
    wrong: list[str] = []
    for derivation in derivations.values():
        fact = facts.get(derivation.fact_id)
        if fact is not None and fact.provenance_class != "DERIVED_FACT":
            wrong.append(derivation.fact_id)
    for fact_id, fact in facts.items():
        if fact.provenance_class == "DERIVED_FACT" and fact_id not in derivations:
            wrong.append(fact_id)
    return GateCheck(
        key="provenance",
        label="Derived and source facts are labelled consistently",
        passed=not wrong,
        message=f"facts with an inconsistent provenance class: {_sample(wrong)}" if wrong else "",
    )


def _units(facts: dict[str, Fact], derivations: dict[str, Derivation]) -> GateCheck:
    bad: list[str] = []
    for derivation in derivations.values():
        formula = FORMULAS.get(derivation.formula_id)
        if formula is None:
            bad.append(f"{derivation.fact_id}(unknown formula {derivation.formula_id})")
            continue
        units = [facts[input_id].unit for input_id in derivation.inputs if input_id in facts]
        error = formula.unit_error(units)
        if error:
            bad.append(f"{derivation.fact_id}({error})")
            continue
        expected = formula.output_unit(units)
        actual = facts[derivation.fact_id].unit if derivation.fact_id in facts else expected
        if expected != actual:
            bad.append(f"{derivation.fact_id}(unit {actual!r}, expected {expected!r})")
    return GateCheck(
        key="units",
        label="Derived values use compatible units",
        passed=not bad,
        message=f"unit problems: {_sample(bad)}" if bad else "",
    )


def _recomputes(facts: dict[str, Fact], derivations: dict[str, Derivation]) -> GateCheck:
    bad: list[str] = []
    for derivation in derivations.values():
        formula = FORMULAS.get(derivation.formula_id)
        fact = facts.get(derivation.fact_id)
        if formula is None or fact is None:
            continue
        try:
            inputs = [float(facts[input_id].value) for input_id in derivation.inputs]
            stored = float(fact.value)
        except (KeyError, TypeError, ValueError):
            bad.append(f"{derivation.fact_id}(non-numeric)")
            continue
        recomputed = formula.compute(*inputs)
        if recomputed is None:
            bad.append(f"{derivation.fact_id}(formula produced no value)")
        elif abs(recomputed - stored) > max(_TOLERANCE, abs(stored) * _TOLERANCE):
            bad.append(f"{derivation.fact_id}({stored} != {recomputed})")
    return GateCheck(
        key="recomputes",
        label="Every derived value recomputes from its inputs",
        passed=not bad,
        message=f"derivations that do not recompute: {_sample(bad)}" if bad else "",
    )


_GATES = (_addresses, _dated, _derivation_inputs, _provenance, _units, _recomputes)


def validate_facts(facts: dict[str, Fact], derivations: dict[str, Derivation]) -> list[GateCheck]:
    """Every precondition, always in the same order, so a UI or a test can rely
    on the set and its order."""
    return [gate(facts, derivations) for gate in _GATES]


def first_failure(checks: list[GateCheck]) -> str | None:
    for check in checks:
        if not check.passed:
            return f"{check.label}: {check.message}"
    return None
