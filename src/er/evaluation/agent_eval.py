"""Hard-path evaluation of agent answers - the deterministic half of a
double-entry check. Jev's verdict (er.agent.verifier) is the soft half. The
cases where the two disagree are the useful ones, so both are reported.

check_answer() and to_junit() are pure; run_cases() is the only function here
that needs the MCP server, OpenRouter and the processed data.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from xml.etree import ElementTree

import yaml
from mcp import Client
from pydantic import BaseModel

from er.agent.models import AskResult
from er.agent.orchestrator import ask, mcp_stdio_params
from er.config import AppConfig


class ExpectedFact(BaseModel):
    predicate: str
    value: str | int | float | bool | None = None


class AgentCase(BaseModel):
    id: str
    question: str
    entity_id: str | None = None
    expect_facts: list[ExpectedFact] = []
    # Substrings of Evidence.source that must be cited - for claims that are
    # not numbers (a parent's name, a status) and so never become facts.
    expect_sources: list[str] = []


class Check(BaseModel):
    name: str
    passed: bool
    message: str = ""


class CaseResult(BaseModel):
    case_id: str
    checks: list[Check]
    verification_status: str | None = None
    fact_values: dict[str, str] = {}
    elapsed_s: float = 0.0

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def disagreement(self) -> bool:
        if self.verification_status not in ("verified", "unverified"):
            return False
        return self.passed != (self.verification_status == "verified")


def load_cases(path: Path) -> list[AgentCase]:
    return [AgentCase.model_validate(raw) for raw in yaml.safe_load(path.read_text())]


def check_answer(case: AgentCase, result: AskResult, baseline: dict[str, str] | None = None) -> list[Check]:
    cited = {citation.evidence_id for citation in result.citations}
    unresolved = sorted(cited - result.evidence.keys())
    # Inputs of a derived fact are carried for display; only facts the answer
    # itself stated have to be cited.
    inputs_only = {
        fact_id for derivation in result.derivations.values() for fact_id in derivation.inputs
    } - result.derivations.keys()
    uncited_facts = sorted(
        fact_id
        for fact_id, fact in result.facts.items()
        if fact.evidence_id not in cited and fact_id not in inputs_only
    )
    cited_sources = [result.evidence[evidence_id].source for evidence_id in cited if evidence_id in result.evidence]

    checks = [
        Check(name="submitted", passed=bool(result.citations), message="" if result.citations else "no cited answer"),
        Check(
            name="citations_resolve",
            passed=not unresolved,
            message=f"unknown evidence: {', '.join(unresolved)}" if unresolved else "",
        ),
        Check(
            name="facts_cited",
            passed=not uncited_facts,
            message=f"facts without a cited source: {', '.join(uncited_facts)}" if uncited_facts else "",
        ),
    ]
    for expected in case.expect_facts:
        values = [str(fact.value) for fact in result.facts.values() if fact.predicate == expected.predicate]
        if not values:
            checks.append(Check(name=f"recall:{expected.predicate}", passed=False, message="fact not used"))
        elif expected.value is not None and str(expected.value) not in values:
            checks.append(
                Check(
                    name=f"recall:{expected.predicate}",
                    passed=False,
                    message=f"expected {expected.value}, answer used {', '.join(values)}",
                )
            )
        else:
            checks.append(Check(name=f"recall:{expected.predicate}", passed=True))
    for source in case.expect_sources:
        found = any(source.lower() in cited.lower() for cited in cited_sources)
        checks.append(
            Check(name=f"source:{source}", passed=found, message="" if found else "source not cited")
        )
    if baseline is not None:
        changed = sorted(
            fact_id
            for fact_id, fact in result.facts.items()
            if fact_id in baseline and baseline[fact_id] != str(fact.value)
        )
        checks.append(
            Check(
                name="snapshot_consistency",
                passed=not changed,
                message=f"values changed since baseline: {', '.join(changed)}" if changed else "",
            )
        )
    return checks


async def run_cases(
    cfg: AppConfig,
    cases: list[AgentCase],
    baseline: dict[str, dict[str, str]] | None = None,
    case_timeout_s: float = 180,
) -> list[CaseResult]:
    results = []
    async with Client(mcp_stdio_params(cfg)) as client:
        for case in cases:
            started = time.monotonic()
            try:
                answer = await asyncio.wait_for(ask(client, cfg, case.question, case.entity_id), case_timeout_s)
            except Exception as exc:  # one broken case must not hide the rest
                results.append(
                    CaseResult(
                        case_id=case.id,
                        checks=[Check(name="submitted", passed=False, message=f"{type(exc).__name__}: {exc}")],
                        elapsed_s=time.monotonic() - started,
                    )
                )
                continue
            results.append(
                CaseResult(
                    case_id=case.id,
                    checks=check_answer(case, answer, baseline.get(case.id) if baseline else None),
                    verification_status=answer.verification.status if answer.verification else None,
                    fact_values={fact_id: str(fact.value) for fact_id, fact in answer.facts.items()},
                    elapsed_s=time.monotonic() - started,
                )
            )
    return results


def to_junit(results: list[CaseResult]) -> str:
    suite = ElementTree.Element(
        "testsuite",
        name="agent-eval",
        tests=str(sum(len(result.checks) for result in results)),
        failures=str(sum(not check.passed for result in results for check in result.checks)),
        time=f"{sum(result.elapsed_s for result in results):.2f}",
    )
    for result in results:
        for check in result.checks:
            case = ElementTree.SubElement(suite, "testcase", classname=f"agent_eval.{result.case_id}", name=check.name)
            if not check.passed:
                ElementTree.SubElement(case, "failure", message=check.message or check.name)
        properties = ElementTree.SubElement(
            ElementTree.SubElement(suite, "testcase", classname=f"agent_eval.{result.case_id}", name="soft_path"),
            "properties",
        )
        ElementTree.SubElement(properties, "property", name="jev_status", value=result.verification_status or "none")
        ElementTree.SubElement(properties, "property", name="disagrees_with_hard_path", value=str(result.disagreement))
    return ElementTree.tostring(suite, encoding="unicode", xml_declaration=True)
