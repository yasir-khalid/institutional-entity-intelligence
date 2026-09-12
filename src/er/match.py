"""CLI: python -m er.match --name "Albacore Partners I Master Fund" --country IE

Unlike er.search (retrieval only - a ranked candidate list), this runs the full
retrieve -> score -> decide pipeline and prints the decision with its evidence.
"""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from er.config import load_config
from er.indexing.opensearch_index import get_client
from er.matching.matcher import match
from er.matching.models import Decision

DECISION_STYLE = {
    Decision.AUTO_MATCH: "bold green",
    Decision.REVIEW: "bold yellow",
    Decision.UNMATCHED: "bold red",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Match a name against GLEIF entities")
    parser.add_argument("--name", required=True)
    parser.add_argument("--country", default=None, help="ISO alpha-2, e.g. IE")
    parser.add_argument("--postcode", default=None)
    parser.add_argument("--city", default=None)
    parser.add_argument("--registration-id", default=None)
    parser.add_argument("--top", type=int, default=5, help="how many candidates to print")
    args = parser.parse_args()

    console = Console()
    cfg = load_config()
    client = get_client(cfg)
    result = match(
        client,
        cfg,
        args.name,
        args.country,
        args.postcode,
        args.city,
        args.registration_id,
    )

    style = DECISION_STYLE[result.decision]
    header = Text(result.decision.value, style=style)

    if result.lei:
        chosen = next((c for c in result.candidates if c.lei == result.lei), None)
        body = Text()
        body.append(f"{chosen.legal_name}\n", style="bold")
        body.append(f"LEI: {result.lei}\n")
        body.append(f"Score: {result.score:.2f}")
        if result.gap is not None:
            body.append(f"   Gap to runner-up: {result.gap:.2f}")
        panel = Panel(body, title=header, subtitle=f'query: "{args.name}"', border_style=style.split()[-1])
    else:
        panel = Panel(
            Text("No confident candidate.", style="dim"),
            title=header,
            subtitle=f'query: "{args.name}"',
            border_style=style.split()[-1],
        )
    console.print(panel)

    if result.evidence:
        evidence_table = Table(title="Evidence", show_header=True, header_style="bold")
        evidence_table.add_column("Feature")
        evidence_table.add_column("Contribution", justify="right")
        for k, v in sorted(result.evidence.items(), key=lambda kv: -abs(kv[1])):
            style = "green" if v > 0 else "red"
            evidence_table.add_row(k, Text(f"{v:+.2f}", style=style))
        console.print(evidence_table)

    n = min(args.top, len(result.candidates))
    candidates_table = Table(title=f"Top {n} candidates", show_header=True, header_style="bold")
    candidates_table.add_column("#", justify="right")
    candidates_table.add_column("Legal name")
    candidates_table.add_column("LEI")
    candidates_table.add_column("Score", justify="right")
    for c in result.candidates[:n]:
        is_chosen = c.lei == result.lei
        row_style = "bold green" if is_chosen else None
        marker = "✓ " if is_chosen else ""
        candidates_table.add_row(
            str(c.rank), f"{marker}{c.legal_name}", c.lei, f"{c.score:.2f}", style=row_style
        )
    console.print(candidates_table)


if __name__ == "__main__":
    main()
