from er.agent.models import AskResult, Citation, Derivation, Evidence, Fact, FactAddress, GateCheck
from er.evaluation.agent_eval import AgentCase, ExpectedFact, check_answer

_PASSING_GATES = [GateCheck(key="units", label="units agree", passed=True)]


def _result(citations, value=42, gates=_PASSING_GATES, derivations=None):
    evidence = Evidence(evidence_id="ev_1", source="SEC 13F filing", fact_type="lookup", query_hash="q")
    fact = Fact(
        fact_id="f_count",
        evidence_id="ev_1",
        subject="LEI1",
        predicate="sec_13f.reported_security_count",
        value=value,
        address=FactAddress(source="SEC 13F filing", document_id="0001", locator="SUMMARYPAGE", field="TOTAL"),
    )
    return AskResult(
        answer="It reported 42 securities [1].",
        citations=[Citation(marker=1, evidence_id=evidence_id) for evidence_id in citations],
        evidence={"ev_1": evidence},
        facts={"f_count": fact},
        derivations=derivations or {},
        gates=gates,
    )


def _failed(checks):
    return {check.name for check in checks if not check.passed}


def test_hard_path_flags_unresolved_citations_missing_facts_and_moved_values():
    case = AgentCase(
        id="count",
        question="How many securities?",
        expect_facts=[ExpectedFact(predicate="sec_13f.reported_security_count")],
        expect_sources=["13F"],
    )

    assert _failed(check_answer(case, _result(["ev_1"]), baseline={"f_count": "42"})) == set()
    assert _failed(check_answer(case, _result(["ev_1", "ev_invented"]))) == {"citations_resolve"}
    assert _failed(check_answer(case, _result([]))) == {"submitted", "facts_cited", "source:13F"}
    assert _failed(check_answer(case, _result(["ev_1"], value=43), baseline={"f_count": "42"})) == {
        "snapshot_consistency"
    }

    pinned = case.model_copy(update={"expect_facts": [ExpectedFact(predicate="sec_13f.reported_security_count", value=40)]})
    assert _failed(check_answer(pinned, _result(["ev_1"]))) == {"recall:sec_13f.reported_security_count"}


def test_hard_path_flags_a_failed_gate_and_a_derivation_that_does_not_recompute():
    case = AgentCase(id="count", question="How many securities?")

    failed_gate = [GateCheck(key="dated", label="Every measured value is dated", passed=False, message="no as-of")]
    assert "gates_passed" in _failed(check_answer(case, _result(["ev_1"], gates=failed_gate)))
    # A submitted answer with no gate checks at all is not silently trusted.
    assert "gates_passed" in _failed(check_answer(case, _result(["ev_1"], gates=[])))

    # A derived percentage of 5 is passed off as the truth; the formula over the
    # stated inputs yields 100, so the invariant catches it independently.
    base = _result(["ev_1"], gates=_PASSING_GATES)
    base.facts["f_total"] = Fact(
        fact_id="f_total", evidence_id="ev_1", subject="LEI1", predicate="position.value",
        value=100, unit="USD", as_of="2026-03-31",
        address=FactAddress(source="SEC 13F filing", document_id="0001", locator="ROW", field="VALUE"),
    )
    base.facts["f_pct"] = Fact(
        fact_id="f_pct", evidence_id="ev_1", subject="LEI1", predicate="position.percent_change",
        value=5, unit="percent", as_of="2026-03-31", provenance_class="DERIVED_FACT",
        address=FactAddress(source="Calculated", document_id="percent_change", locator="x", field="value"),
    )
    base.derivations["f_pct"] = Derivation(
        fact_id="f_pct", formula_id="difference", expression="current - previous", inputs=["f_total", "f_count"]
    )
    assert "derivations_recompute" in _failed(check_answer(case, base))
