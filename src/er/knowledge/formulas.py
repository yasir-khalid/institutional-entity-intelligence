"""Every derived number an answer may state comes from one of these, applied
to source facts. The formula id and its inputs travel with the result, so a
reader can see how a figure was computed and open each input it came from.

Formulas are unit-aware on purpose. A derived value is only as trustworthy as
the arithmetic behind it, and "add USD to shares" is a silent, plausible-looking
error, not a crash - so `unit_error()` makes the inputs' units a checked
precondition (er.agent.gates runs it before an answer may be submitted) rather
than a convention the caller is trusted to honour. It is a gate, not a
confidence score: either the units line up or the derivation is refused.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Formula:
    formula_id: str
    expression: str
    unit: str | None
    compute: Callable[..., float | None]
    # Positional unit each input must carry. None means "any unit, but every
    # unitless/`input_units is None` formula still requires its inputs to agree
    # with one another". An empty tuple means the formula takes no inputs.
    input_units: tuple[str | None, ...] | None = None

    def unit_error(self, units: Sequence[str | None]) -> str | None:
        """Why these inputs may not be fed to this formula, or None if they may."""
        if self.input_units is not None:
            if len(units) != len(self.input_units):
                return f"{self.formula_id} expects {len(self.input_units)} input(s), got {len(units)}"
            for expected, actual in zip(self.input_units, units):
                if expected is not None and actual != expected:
                    return (
                        f"{self.formula_id} expects a {expected!r} input, "
                        f"got {actual!r}"
                    )
            return None
        # No declared signature: every input must carry the same unit (or all be
        # unitless). Mixing USD and shares - or USD and unitless - is refused.
        if len(set(units)) > 1:
            present = ", ".join(sorted({unit or "unitless" for unit in units}))
            return f"{self.formula_id} cannot mix units: {present}"
        return None

    def output_unit(self, units: Sequence[str | None]) -> str | None:
        return self.unit if self.unit is not None else (units[0] if units else None)


def _percent_change(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return round((current - previous) / previous * 100, 2)


def _ratio(numerator: float, denominator: float) -> float | None:
    if not denominator:
        return None
    return round(numerator / denominator, 4)


def _percent_of(part: float, total: float) -> float | None:
    if not total:
        return None
    return round(part / total * 100, 2)


FORMULAS = {
    formula.formula_id: formula
    for formula in (
        # Same-unit inputs, output in that unit.
        Formula("sum", "sum(inputs)", None, lambda *values: sum(values)),
        Formula("difference", "current - previous", None, lambda current, previous: current - previous),
        Formula("percent_change", "(current - previous) / previous * 100", "percent", _percent_change),
        # Dimensionless and share figures: inputs must share a unit, the output
        # is a bare ratio or a percentage.
        Formula("ratio", "numerator / denominator", "ratio", _ratio),
        Formula("percent_of", "part / total * 100", "percent", _percent_of),
    )
}
