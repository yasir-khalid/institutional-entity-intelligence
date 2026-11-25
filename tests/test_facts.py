from er.agent.facts import normalise_placeholders, render_answer
from er.agent.models import Fact, FactAddress


def test_answer_renderer_requires_known_cited_facts_for_numbers():
    fact = Fact(
        fact_id="f_count",
        evidence_id="ev_profile",
        subject="LEI1",
        predicate="sec_13f.reported_security_count",
        value=42,
        as_of="31-MAR-2026",
        address=FactAddress(
            source="SEC 13F filing",
            document_id="0001",
            locator="SUMMARYPAGE.tsv:ACCESSION_NUMBER=0001",
            field="TABLEENTRYTOTAL",
        ),
    )
    facts = {fact.fact_id: fact}

    answer, error = render_answer("It reported {{f:f_count}} securities [1].", facts, {"ev_profile"})
    assert answer == "It reported 42 securities [1]."
    assert error is None
    assert render_answer("It reported 42 securities [1].", facts, {"ev_profile"})[0] is None
    assert render_answer("It reported {{f:missing}} securities [1].", facts, {"ev_profile"})[0] is None
    assert render_answer("It reported {{f:f_count}} securities [1].", facts, set())[0] is None
    assert render_answer("It reported {{f:f_...}} securities [1].", facts, {"ev_profile"})[0] is None

    value = fact.model_copy(update={"fact_id": "f_value", "value": 1213580505, "unit": "USD"})
    change = fact.model_copy(update={"fact_id": "f_change", "value": -0.35, "unit": "percent"})
    facts = {**facts, "f_value": value, "f_change": change}
    answer, error = render_answer("Worth ${{f:f_value}}, {{f:f_change}}% on the quarter [1].", facts, {"ev_profile"})
    assert answer == "Worth $1,213,580,505, -0.35% on the quarter [1]."


def test_identifiers_and_dates_copied_whole_are_not_new_numbers():
    fact = Fact(
        fact_id="f_cik",
        evidence_id="ev_profile",
        subject="LEI1",
        predicate="sec_13f.cik",
        value="0001600177",
        as_of="31-MAR-2026",
        address=FactAddress(source="SEC 13F filing", document_id="0001", locator="COVERPAGE", field="CIK"),
    )
    facts = {fact.fact_id: fact}
    question = "How did its position in CUSIP 594918104 change?"

    answer = "CIK 0001600177 [1] filed for 31-MAR-2026 [1]; CUSIP 594918104 holds {{f:cik}} [1]."
    rendered, error = render_answer(normalise_placeholders(answer, facts), facts, {"ev_profile"}, question)
    assert error is None and rendered.endswith("holds 0001600177 [1].")

    assert render_answer("CIK 0001600177 [1].", facts, set(), question)[0] is None
    assert render_answer("It rose 31% [1].", facts, {"ev_profile"}, question)[0] is None


def test_ui_block_values_come_from_placeholders_only():
    address = FactAddress(source="SEC 13F", document_id="0001", locator="INFOTABLE", field="VALUE")
    value = Fact(fact_id="f_v", evidence_id="ev_1", subject="cik:1", predicate="holding.reported_value",
                 value=1500, unit="USD", as_of="31-MAR-2026", address=address)
    facts = {"f_v": value}
    block = (
        "Grew [1].\n```openui-lang\nroot = Stack([chart, table])\n"
        'chart = BarChart(["31-MAR-2026"], [Series("Value", [{{f:f_v}}])])\n'
        'table = Table([Col("Value", ["{{f:f_v}}"])])\n```'
    )
    rendered, error = render_answer(block, facts, {"ev_1"})
    assert error is None
    assert '[Series("Value", [1500])]' in rendered and 'Col("Value", ["$1,500"])' in rendered

    assert render_answer(block.replace("[{{f:f_v}}]", "[2500]"), facts, {"ev_1"})[0] is None
    # Copying the exact reported amount is still a literal the model typed: it
    # must use the placeholder, not just repeat a value it happened to see.
    assert render_answer("It reported 1500 [1].", facts, {"ev_1"})[0] is None
