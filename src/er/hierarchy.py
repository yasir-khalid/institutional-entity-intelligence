"""CLI: python -m er.hierarchy --lei <LEI> [--direction parents|children|all] [--depth N]
   or:  python -m er.hierarchy --name "..." --country XX   (resolves via er.match first)

Given an LEI (or a messy name+country that gets resolved to one first), shows its
GLEIF relationship neighborhood: parents/managers/master-fund upward, subsidiaries/
managed-funds/feeder-funds downward, and any "missing parent" exceptions not
already explained by an active relationship - a missing row is never treated as a
confirmed absence of a parent.

--depth controls how many hops to walk (default 1, today's original single-hop
behavior). depth=2 also shows each neighbor's own neighbors, etc. Cycle-safe and
node-budget-capped - see er.graph.build.build_hierarchy_tree.
"""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.tree import Tree

from er.config import load_config
from er.graph.build import build_hierarchy_tree
from er.graph.models import HierarchyNode

DIRECTIONS = ("parents", "children", "all")


def _add_edge_branch(parent_branch: Tree, node: HierarchyNode, direction: str) -> None:
    status = f"[dim]{node.status or 'n/a'}[/dim]"
    rel_type = f"[dim]({node.relationship_type})[/dim]"
    suffix = "" if node.expanded else " [dim]…(depth limit reached)[/dim]"
    label = f"{node.label}: {node.name or '(unknown name)'}  LEI: {node.lei}  {status} {rel_type}{suffix}"
    branch = parent_branch.add(label)
    if node.expanded:
        _add_children(branch, node, direction)


def _add_children(branch: Tree, node: HierarchyNode, direction: str) -> None:
    if direction in ("parents", "all") and node.upward:
        up_branch = branch.add("[cyan]Upward[/cyan]")
        for child in node.upward:
            _add_edge_branch(up_branch, child, direction)

    if direction in ("children", "all") and node.downward:
        down_branch = branch.add("[cyan]Downward[/cyan]")
        by_label: dict[str, list[HierarchyNode]] = {}
        for child in node.downward:
            by_label.setdefault(child.label or child.relationship_type or "?", []).append(child)
        for label, children in by_label.items():
            rel_type = f"[dim]({children[0].relationship_type})[/dim]"
            group = down_branch.add(f"{label} {rel_type} ({len(children)})")
            for child in children:
                status = f"[dim]{child.status or 'n/a'}[/dim]"
                suffix = "" if child.expanded else " [dim]…(depth limit reached)[/dim]"
                leaf = group.add(f"{child.name or '(unknown name)'}  LEI: {child.lei}  {status}{suffix}")
                if child.expanded:
                    _add_children(leaf, child, direction)

    if direction in ("parents", "all") and node.exceptions:
        exc_branch = branch.add("[yellow]Known gaps[/yellow] (no relationship row, but a reason is on file)")
        for exc in node.exceptions:
            exc_branch.add(f"{exc.label}: {exc.reason_text}")


def render(console: Console, root: HierarchyNode, direction: str = "all") -> None:
    tree = Tree(f"[bold]{root.name or '(unknown name)'}[/bold]  LEI: {root.lei}")
    _add_children(tree, root, direction)

    has_content = bool(root.upward or root.downward or root.exceptions)
    if not has_content:
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
    parser.add_argument(
        "--depth",
        type=int,
        default=1,
        help="how many hops to walk (default 1 = immediate relationships only, today's original "
        "behavior). depth=2 also expands each neighbor's own relationships, etc.",
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

    root = build_hierarchy_tree(cfg, lei, depth=args.depth, direction=args.direction)
    render(console, root, args.direction)


if __name__ == "__main__":
    main()
