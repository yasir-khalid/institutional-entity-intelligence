"""Every derived number an answer may state comes from one of these, applied
to source facts. The formula id and its inputs travel with the result, so a
reader can see how a figure was computed and open each input it came from."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Formula:
    formula_id: str
    expression: str
    unit: str | None
    compute: Callable[..., float | None]


def _percent_change(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return round((current - previous) / previous * 100, 2)


FORMULAS = {
    formula.formula_id: formula
    for formula in (
        Formula("sum", "sum(inputs)", None, lambda *values: sum(values)),
        Formula("difference", "current - previous", None, lambda current, previous: current - previous),
        Formula("percent_change", "(current - previous) / previous * 100", "percent", _percent_change),
    )
}
