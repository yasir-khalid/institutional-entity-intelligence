from __future__ import annotations

import re

from .models import Fact


_PLACEHOLDER = re.compile(r"\{\{f:([a-zA-Z0-9_-]+)\}\}")
# The same placeholder with a "$" or "%" the model wrote around it, so the
# rendered value carries its unit exactly once.
_RENDERED = re.compile(r"(\$)?\{\{f:([a-zA-Z0-9_-]+)\}\}(%)?")
_MALFORMED = re.compile(r"\{\{[^}]*\}?\}?")
_CITATION = re.compile(r"\[\d+\]")
_NUMBER = re.compile(r"(?<![\w])[-+]?\d[\d,]*(?:\.\d+)?%?(?![\w])")


def normalise_placeholders(answer: str, facts: dict[str, Fact]) -> str:
    """Models often drop the "f_" prefix when copying an id. Restore it when
    that names exactly one known fact; anything else is left to be rejected."""

    def restore(match: re.Match) -> str:
        fact_id = match.group(1)
        if fact_id not in facts and f"f_{fact_id}" in facts:
            return f"{{{{f:f_{fact_id}}}}}"
        return match.group(0)

    return _PLACEHOLDER.sub(restore, answer)


def _strip_grounded_literals(prose: str, facts: dict[str, Fact], cited_evidence: set[str], question: str) -> str:
    # An identifier or date copied whole from a cited fact (a CIK, a report
    # date) or echoed from the question is not a new number. Only complete
    # values of four or more characters count - a "31" inside a date is not a
    # licence to write 31 anywhere.
    grounded = {
        str(text)
        for fact in facts.values()
        if fact.evidence_id in cited_evidence
        for text in (fact.value, fact.as_of)
        if text is not None and len(str(text)) >= 4
    }
    grounded |= {token.strip(".,;:()?\"'") for token in question.split() if any(char.isdigit() for char in token)}
    for text in sorted(grounded, key=len, reverse=True):
        prose = prose.replace(text, "")
    return prose


def render_answer(
    answer: str, facts: dict[str, Fact], cited_evidence: set[str], question: str = ""
) -> tuple[str | None, str | None]:
    fact_ids = _PLACEHOLDER.findall(answer)
    unknown = sorted(set(fact_ids) - facts.keys())
    if unknown:
        return None, f"unknown fact_id: {', '.join(unknown)}"

    uncited = sorted({fact_id for fact_id in fact_ids if facts[fact_id].evidence_id not in cited_evidence})
    if uncited:
        return None, f"fact placeholders are not covered by a submitted citation: {', '.join(uncited)}"

    prose = _CITATION.sub("", _PLACEHOLDER.sub("", answer))
    malformed = _MALFORMED.findall(prose)
    if malformed:
        return None, f"malformed fact placeholders (use {{{{f:fact_id}}}} exactly): {', '.join(malformed)}"

    numbers = _NUMBER.findall(_strip_grounded_literals(prose, facts, cited_evidence, question))
    if numbers:
        return None, f"numeric values must use fact placeholders: {', '.join(numbers)}"

    def render(match: re.Match) -> str:
        fact = facts[match.group(2)]
        dollar = match.group(1) if fact.unit != "USD" and match.group(1) else ""
        percent = match.group(3) if fact.unit != "percent" and match.group(3) else ""
        return f"{dollar}{display_value(fact)}{percent}"

    return _RENDERED.sub(render, answer), None


def display_value(fact: Fact) -> str:
    """A fact's value as an answer should show it: dollars and percentages
    with their symbol and thousands separators. Identifiers, dates and
    anything without a numeric unit are left exactly as stored."""
    value = fact.value
    if fact.unit not in ("USD", "percent", "shares", "points") or isinstance(value, bool) or value is None:
        return str(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    digits = f"{abs(number):,.0f}" if number.is_integer() else f"{abs(number):,.2f}"
    sign = "-" if number < 0 else ""
    if fact.unit == "USD":
        return f"{sign}${digits}"
    if fact.unit == "percent":
        return f"{sign}{digits}%"
    return f"{sign}{digits}"


def referenced_fact_ids(answer: str) -> set[str]:
    return set(_PLACEHOLDER.findall(answer))


def same_source_value(original: Fact, refreshed: Fact) -> bool:
    return (
        original.value == refreshed.value
        and original.unit == refreshed.unit
        and original.as_of == refreshed.as_of
        and original.address == refreshed.address
    )
