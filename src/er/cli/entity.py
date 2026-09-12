"""CLI: python -m er.cli.entity --name "..." [--country XX]
   or:  python -m er.cli.entity --lei <LEI>

The single "tell me about this institution" view: canonical identity, every
identifier attached to it (LEI, ISIN, SEC CIK, ...), its GLEIF relationship
neighborhood, and - when it has been resolved as a SEC 13F filer - its most
recently reported holdings. Resolves a messy --name via er.matching.matcher
first, exactly like er.cli.hierarchy and er.cli.family do, so all entity-facing
CLIs share one resolution step.

Every CLI lives under er.cli, entirely separate from the core entity-
resolution/ETL packages it calls (er.entity, er.matching, er.datasources, ...) -
none of those packages import argparse or rich, so they stay usable from a
future API or notebook without dragging in terminal-presentation code. This
module itself only does argument parsing and wiring - see er.cli.entity_render
for the actual rendering.
"""

from __future__ import annotations

import argparse
import time

from rich.console import Console

from er.cli.entity_render import render
from er.config import load_config
from er.entity.profile import get_entity_profile


def _resolve_entity_id(console: Console, cfg, args: argparse.Namespace) -> str | None:
    if args.lei:
        return args.lei

    from er.indexing.opensearch_index import get_client
    from er.matching.matcher import match

    with console.status("[bold cyan]Resolving name against GLEIF...[/bold cyan]"):
        client = get_client(cfg)
        result = match(client, cfg, args.name, args.country, country_mode=args.country_mode)

    if not result.lei:
        console.print(
            f'[red]Could not resolve "{args.name}" to a confident entity '
            f"(decision: {result.decision.value}).[/red]"
        )
        if result.reason:
            console.print(f"[dim]{result.reason}[/dim]")
        return None
    console.print(f'Resolved "{args.name}" -> {result.lei}  (decision: {result.decision.value})')
    return result.lei


def main() -> None:
    parser = argparse.ArgumentParser(description="Show the canonical entity profile for an institution")
    parser.add_argument("--lei", default=None)
    parser.add_argument("--name", default=None, help="resolve this name via er.cli.match first")
    parser.add_argument("--country", default=None, help="ISO alpha-2 or common alias, used only with --name")
    parser.add_argument(
        "--country-mode",
        default="soft",
        choices=["soft", "strict"],
        help="only used when resolving via --name (see er.cli.match --help)",
    )
    args = parser.parse_args()
    if not args.lei and not args.name:
        parser.error("provide --lei or --name")

    console = Console()
    cfg = load_config()

    started = time.monotonic()

    entity_id = _resolve_entity_id(console, cfg, args)
    if entity_id is None:
        return

    with console.status("[bold cyan]Fetching entity profile (identifiers, relationships, SEC activity)...[/bold cyan]"):
        profile = get_entity_profile(cfg, entity_id)
    elapsed = time.monotonic() - started

    if profile is None:
        console.print(f"[red]No canonical entity found for {entity_id}.[/red] Run `make build-entities` first?")
        return

    render(console, profile)
    console.print(f"\n[dim]Fetched in {elapsed:.2f}s[/dim]")


if __name__ == "__main__":
    main()
