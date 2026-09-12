"""CLI: python -m er.entity --name "..." [--country XX]
   or:  python -m er.entity --lei <LEI>

The single "tell me about this institution" view: canonical identity, every
identifier attached to it (LEI, ISIN, SEC CIK, ...), its GLEIF relationship
neighborhood, and - when it has been resolved as a SEC 13F filer - its most
recently reported holdings. Resolves a messy --name via er.match first, exactly
like er.hierarchy and er.family do, so all entity-facing CLIs share one
resolution step.
"""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table

from er.config import load_config
from er.entity.models import EntityProfile
from er.entity.profile import get_entity_profile


def render(console: Console, profile: EntityProfile) -> None:
    console.print(f"\n[bold]{profile.canonical_name}[/bold]")
    console.print(f"Entity ID: {profile.entity_id}  |  Status: {profile.entity_status or 'unknown'}")
    console.print(f"Jurisdiction: {profile.jurisdiction or '-'}  |  Country: {profile.legal_country or '-'}")

    # High-cardinality identifier types (an entity can have dozens of ISINs, one
    # per share class/listing) are collapsed to a count + sample so the table
    # stays a profile overview, not a full dump - full detail is always in
    # entity_identifiers.parquet for whoever needs every value.
    COLLAPSE_THRESHOLD = 5
    by_type: dict[str, list] = {}
    for ident in profile.identifiers:
        by_type.setdefault(ident.identifier_type, []).append(ident)

    id_table = Table(title="Identifiers", show_lines=False)
    id_table.add_column("Type")
    id_table.add_column("Value")
    id_table.add_column("Source")
    id_table.add_column("Confidence")
    id_table.add_row("LEI", profile.entity_id, "gleif", "SOURCE")
    for id_type, idents in by_type.items():
        if len(idents) > COLLAPSE_THRESHOLD:
            sample = ", ".join(i.identifier_value for i in idents[:3])
            id_table.add_row(
                id_type, f"{len(idents)} values (e.g. {sample}, ...)", idents[0].source, idents[0].confidence
            )
        else:
            for ident in idents:
                id_table.add_row(ident.identifier_type, ident.identifier_value, ident.source, ident.confidence)
    console.print(id_table)

    if profile.hierarchy and (profile.hierarchy.upward or profile.hierarchy.downward or profile.hierarchy.exceptions):
        rel_table = Table(title="GLEIF relationships")
        rel_table.add_column("Direction")
        rel_table.add_column("Label")
        rel_table.add_column("Entity")
        rel_table.add_column("LEI")
        for edge in profile.hierarchy.upward:
            rel_table.add_row("Upward", edge.label, edge.name or "(unknown)", edge.lei)
        for edge in profile.hierarchy.downward:
            rel_table.add_row("Downward", edge.label, edge.name or "(unknown)", edge.lei)
        for exc in profile.hierarchy.exceptions:
            rel_table.add_row("Upward", exc.label, f"[dim]{exc.reason_text}[/dim]", "-")
        console.print(rel_table)
    else:
        console.print("[dim]No GLEIF relationships or exceptions on file.[/dim]")

    console.print()
    if profile.sec_13f is None:
        console.print("[dim]SEC 13F: not a resolved 13F filer (no CIK identifier attached).[/dim]")
    elif profile.sec_13f.latest_filing_date is None:
        console.print(f"[dim]SEC 13F: filer CIK {profile.sec_13f.cik} resolved, but no filings found.[/dim]")
    else:
        sec = profile.sec_13f
        console.print(
            f"[bold]SEC 13F[/bold]: filer (CIK {sec.cik}) - latest filing {sec.latest_filing_date} "
            f"for period {sec.latest_period_of_report}, {sec.reported_security_count} securities reported"
        )
        console.print(
            "[dim]This is the latest SEC Form 13F reported holdings snapshot, not a complete "
            "portfolio - 13F excludes shorts, derivatives, non-US securities, private investments, "
            "and small positions below reporting thresholds.[/dim]"
        )
        holdings_table = Table(title="Latest SEC 13F reported holdings (top 10 by value)")
        holdings_table.add_column("Issuer")
        holdings_table.add_column("Value ($000s)", justify="right")
        for h in sec.top_reported_holdings:
            holdings_table.add_row(h.name_of_issuer, f"{h.value:,}" if h.value is not None else "-")
        console.print(holdings_table)


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

    console = Console()
    cfg = load_config()

    entity_id = args.lei
    if not entity_id:
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
        console.print(f'Resolved "{args.name}" -> {result.lei}  (decision: {result.decision.value})')
        entity_id = result.lei

    profile = get_entity_profile(cfg, entity_id)
    if profile is None:
        console.print(f"[red]No canonical entity found for {entity_id}.[/red] Run `make build-entities` first?")
        return
    render(console, profile)


if __name__ == "__main__":
    main()
