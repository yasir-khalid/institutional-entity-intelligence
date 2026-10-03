from er.agent.models import AskResult, Citation, Evidence, Fact, FactAddress
from er.evaluation.agent_eval import AgentCase, ExpectedFact, check_answer


def _result(citations, value=42):
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
