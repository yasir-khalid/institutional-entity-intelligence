"""CLI: python -m er.entity --name "..." [--country XX]
   or:  python -m er.entity --lei <LEI>

The single "tell me about this institution" view: canonical identity, every
identifier attached to it (LEI, ISIN, SEC CIK, ...), its GLEIF relationship
neighborhood, and - when it has been resolved as a SEC 13F filer - its most
recently reported holdings. Resolves a messy --name via er.match first, exactly
like er.hierarchy and er.family do, so all entity-facing CLIs share one
resolution step.

This module only does argument parsing and wiring - it owns no rendering logic
itself (see er.entity.render) and no entity-resolution logic itself (see
er.entity.profile), so neither of those can accidentally end up depending on
argparse/rich/live services.
"""

from __future__ import annotations

import argparse

from rich.console import Console

from er.config import load_config
from er.entity.profile import get_entity_profile
from er.entity.render import render


def _resolve_entity_id(console: Console, cfg, args: argparse.Namespace) -> str | None:
    if args.lei:
        return args.lei

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
        return None
    console.print(f'Resolved "{args.name}" -> {result.lei}  (decision: {result.decision.value})')
    return result.lei


def main() -> None:
    parser = argparse.ArgumentParser(description="Show the canonical entity profile for an institution")
    parser.add_argument("--lei", default=None)
    parser.add_argument("--name", default=None, help="resolve this name via er.match first")
    parser.add_argument("--country", default=None, help="ISO alpha-2 or common alias, used only with --name")
    parser.add_argument(
        "--country-mode",
        default="soft",
        choices=["soft", "strict"],
        help="only used when resolving via --name (see er.match --help)",
    )
    args = parser.parse_args()
    if not args.lei and not args.name:
        parser.error("provide --lei or --name")

    console = Console()
    cfg = load_config()

    entity_id = _resolve_entity_id(console, cfg, args)
    if entity_id is None:
        return

    profile = get_entity_profile(cfg, entity_id)
    if profile is None:
        console.print(f"[red]No canonical entity found for {entity_id}.[/red] Run `make build-entities` first?")
        return
    render(console, profile)


if __name__ == "__main__":
    main()
