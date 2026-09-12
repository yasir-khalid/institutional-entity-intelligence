"""CLI: python -m er.hierarchy --lei <LEI> [--direction parents|children|all]
   or:  python -m er.hierarchy --name "..." --country XX   (resolves via er.match first)

Given an LEI (or a messy name+country that gets resolved to one first), shows its
GLEIF relationship neighborhood: parents/managers/master-fund upward, subsidiaries/
managed-funds/feeder-funds downward, and any "missing parent" exceptions not
already explained by an active relationship - a missing row is never treated as a
confirmed absence of a parent.
"""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.tree import Tree

from er.config import load_config
from er.graph.build import build_hierarchy
from er.graph.models import HierarchyResult

DIRECTIONS = ("parents", "children", "all")


def render(console: Console, result: HierarchyResult, direction: str = "all") -> None:
    root_label = f"[bold]{result.name or '(unknown name)'}[/bold]  LEI: {result.lei}"
    tree = Tree(root_label)

    if direction in ("parents", "all") and result.upward:
        branch = tree.add("[cyan]Upward relationships[/cyan] (parents / managers / master fund)")
        for e in result.upward:
            status = f"[dim]{e.status or 'n/a'}[/dim]"
            rel_type = f"[dim]({e.relationship_type})[/dim]"
            branch.add(f"{e.label}: {e.name or '(unknown name)'}  LEI: {e.lei}  {status} {rel_type}")

    if direction in ("children", "all") and result.downward:
        branch = tree.add("[cyan]Downward relationships[/cyan] (subsidiaries / funds / feeders)")
        by_label: dict[str, list] = {}
        for e in result.downward:
            by_label.setdefault(e.label, []).append(e)
        for label, edges in by_label.items():
            rel_type = f"[dim]({edges[0].relationship_type})[/dim]"
            group = branch.add(f"{label} {rel_type} ({len(edges)})")
            for e in edges:
                status = f"[dim]{e.status or 'n/a'}[/dim]"
                group.add(f"{e.name or '(unknown name)'}  LEI: {e.lei}  {status}")

    if direction in ("parents", "all") and result.exceptions:
        branch = tree.add("[yellow]Known gaps[/yellow] (no relationship row, but a reason is on file)")
        for exc in result.exceptions:
            branch.add(f"{exc.label}: {exc.reason_text}")

    shown_upward = direction in ("parents", "all") and (result.upward or result.exceptions)
    shown_downward = direction in ("children", "all") and result.downward
    if not shown_upward and not shown_downward:
        tree.add(f"[dim]No {direction} relationships or exceptions on file for this entity.[/dim]")

    console.print(tree)


def main() -> None:
    parser = argparse.ArgumentParser(description="Show the GLEIF relationship hierarchy for an entity")
    parser.add_argument("--lei", default=None)
    parser.add_argument("--name", default=None, help="resolve this name via er.match first")
    parser.add_argument("--country", default=None, help="ISO alpha-2 or common alias, used only with --name")
    parser.add_argument(
        "--country-mode",
        default="soft",
        choices=["soft", "strict"],
        help="only used when resolving via --name (see er.match --help)",
    )
    parser.add_argument(
        "--direction",
        default="all",
        choices=DIRECTIONS,
        help="parents: upward relationships only. children: downward only. all (default): both.",
    )
    args = parser.parse_args()

    console = Console()
    cfg = load_config()

    lei = args.lei
    if not lei:
        if not args.name:
            parser.error("provide --lei or --name")

        from er.indexing.opensearch_index import get_client
        from er.matching.matcher import match

        client = get_client(cfg)
        result = match(client, cfg, args.name, args.country, country_mode=args.country_mode)
        if not result.lei:
            console.print(
                f'[red]Could not resolve "{args.name}" to a confident entity '
                f"(decision: {result.decision.value}).[/red]"
            )
            if result.reason:
                console.print(f"[dim]{result.reason}[/dim]")
            return
        console.print(f'Resolved "{args.name}" -> {result.lei}  (decision: {result.decision.value})\n')
        lei = result.lei

    hierarchy = build_hierarchy(cfg, lei)
    render(console, hierarchy, args.direction)


if __name__ == "__main__":
    main()
