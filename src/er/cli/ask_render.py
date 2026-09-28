"""Pure presentation for er.cli.ask - takes a finished er.agent AskResult and
a Console, and only ever prints. No live-service imports, so it is unit
testable with Console(file=io.StringIO()) (see tests/test_ask_render.py),
same split as er.cli.entity_render vs er.cli.entity.
"""

from __future__ import annotations

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from er.agent.models import AskResult, Verification

# Status -> (border/accent colour, glyph). "unavailable" is deliberately grey
# and dashed rather than red: the check did not run, which is not the same
# claim as the answer failing it.
STATUS_STYLE: dict[str, tuple[str, str]] = {
    "verified": ("green", "✓"),
    "partial": ("yellow", "◑"),
    "unverified": ("red", "✗"),
    "unavailable": ("bright_black", "—"),
}

METER_WIDTH = 12


def probability_meter(probability: float | None, width: int = METER_WIDTH) -> str:
    """A fixed-width text meter for a 0-1 probability. Fixed width matters:
    these are read stacked, so the bars must share one baseline and one scale
    or they compare wrongly at a glance."""
    if probability is None:
        return "·" * width
    filled = round(max(0.0, min(1.0, probability)) * width)
    return "█" * filled + "░" * (width - filled)


def render_answer(console: Console, result: AskResult) -> None:
    console.print(Panel(result.answer or "[dim]no answer[/dim]", title="Answer", border_style="cyan"))


def render_verification(console: Console, verification: Verification | None) -> None:
    """The badge, printed under the answer. Shows the per-check probabilities
    rather than only the verdict, because a "partially verified" badge is
    useless without knowing *which* check was weak."""
    if verification is None:
        return

    colour, glyph = STATUS_STYLE.get(verification.status, ("bright_black", "—"))
    heading = Text.assemble(
        (f"{glyph} {verification.headline}", f"bold {colour}"),
        ("  ", ""),
        (verification.detail, "dim"),
    )

    body: list[object] = [heading]

    if verification.checks:
        table = Table(show_header=False, box=None, padding=(0, 1, 0, 0))
        table.add_column("check")
        table.add_column("meter")
        table.add_column("value", justify="right")
        for check in verification.checks:
            mark_colour = "bright_black" if check.passed is None else ("green" if check.passed else "red")
            mark = "·" if check.passed is None else ("✓" if check.passed else "✗")
            value = "no signal" if check.probability is None else f"{check.probability:.2f}"
            table.add_row(
                Text.assemble((mark, mark_colour), (f" {check.label}", "")),
                Text(probability_meter(check.probability), style=mark_colour),
                Text(value, style="dim"),
            )
        body.append(table)

    if verification.reason:
        body.append(Text(verification.reason, style="dim"))

    footer_parts = [
        f"checked by {verification.model}" if verification.model else None,
        f"{verification.latency_ms} ms" if verification.latency_ms is not None else None,
        f"verdict: {verification.verdict}" if verification.verdict else None,
    ]
    footer = " · ".join(part for part in footer_parts if part)
    if footer:
        body.append(Text(footer, style="dim"))

    console.print(Panel(Group(*body), title="Verification", border_style=colour))


def render_evidence(console: Console, result: AskResult) -> None:
    if not result.citations:
        console.print("[dim]No citations returned.[/dim]")
        return
    table = Table(title="Evidence", show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Source")
    table.add_column("Criteria")
    table.add_column("Records", justify="right")
    table.add_column("As of")
    for citation in result.citations:
        evidence = result.evidence.get(citation.evidence_id)
        if evidence is None:
            continue
        table.add_row(
            str(citation.marker),
            evidence.source,
            "; ".join(evidence.criteria),
            str(evidence.result_count) if evidence.result_count is not None else "—",
            evidence.source_timestamp or "—",
        )
    console.print(table)


def render_result(console: Console, result: AskResult) -> None:
    render_answer(console, result)
    render_verification(console, result.verification)
    render_evidence(console, result)
