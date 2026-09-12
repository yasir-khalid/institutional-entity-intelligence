"""Terminal rendering for an EntityProfile - lives under er.cli, not er.entity,
so the core entity-resolution package (models.py/build.py/sources.py/profile.py)
never depends on rich or any other presentation concern, and a future
non-terminal consumer (an API, a notebook) can import er.entity.profile without
pulling in display code at all. This module takes a finished EntityProfile and
a rich Console and only ever prints - it never resolves, queries, or builds
anything itself.
"""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from er.entity.models import EntityIdentifier, EntityProfile

# High-cardinality lists (an entity can have dozens of ISINs, or a manager can
# have 40+ funds under it) are collapsed to a count + sample so the profile
# stays a quick overview, not a full dump - full detail always lives in the
# underlying Parquet tables (entity_identifiers.parquet) or in er.cli.hierarchy's
# dedicated multi-hop view for relationships specifically.
COLLAPSE_THRESHOLD = 5


def _render_identifiers(console: Console, profile: EntityProfile) -> None:
    by_type: dict[str, list[EntityIdentifier]] = {}
    for ident in profile.identifiers:
        by_type.setdefault(ident.identifier_type, []).append(ident)

    table = Table(title="Identifiers", show_lines=False)
    table.add_column("Type")
    table.add_column("Value")
    table.add_column("Source")
    table.add_column("Confidence")
    table.add_row("LEI", profile.entity_id, "gleif", "SOURCE")
    for id_type, idents in by_type.items():
        if len(idents) > COLLAPSE_THRESHOLD:
            sample = ", ".join(i.identifier_value for i in idents[:3])
            table.add_row(
                id_type, f"{len(idents)} values (e.g. {sample}, ...)", idents[0].source, idents[0].confidence
            )
        else:
            for ident in idents:
                table.add_row(ident.identifier_type, ident.identifier_value, ident.source, ident.confidence)
    console.print(table)


def _render_relationships(console: Console, profile: EntityProfile) -> None:
    hierarchy = profile.hierarchy
    if not hierarchy or not (hierarchy.upward or hierarchy.downward or hierarchy.exceptions):
        console.print("[dim]No GLEIF relationships or exceptions on file.[/dim]")
        return

    # Grouped by (direction, label) rather than one row per edge - a manager
    # with 40+ funds must not flood this table the way it did before this fix;
    # a group over the collapse threshold shows a count + a few examples, with
    # `er.cli.hierarchy --lei ... --direction ...` pointed to for the full list.
    groups: dict[tuple[str, str], list] = {}
    for edge in hierarchy.upward:
        groups.setdefault(("Upward", edge.label), []).append(edge.name or edge.lei)
    for edge in hierarchy.downward:
        groups.setdefault(("Downward", edge.label), []).append(edge.name or edge.lei)
    for exc in hierarchy.exceptions:
        groups.setdefault(("Upward", exc.label), []).append(f"[dim]{exc.reason_text}[/dim]")

    table = Table(title="GLEIF relationships")
    table.add_column("Direction")
    table.add_column("Label")
    table.add_column("Entities")
    for (direction, label), names in groups.items():
        if len(names) > COLLAPSE_THRESHOLD:
            sample = ", ".join(names[:3])
            table.add_row(direction, label, f"{len(names)} entities (e.g. {sample}, ...)")
        else:
            table.add_row(direction, label, ", ".join(names))
    console.print(table)
    if any(len(names) > COLLAPSE_THRESHOLD for names in groups.values()):
        console.print(f"[dim]Full detail: uv run python -m er.cli.hierarchy --lei {profile.entity_id}[/dim]")


def _render_sec_13f(console: Console, profile: EntityProfile) -> None:
    console.print()
    sec = profile.sec_13f
    if sec is None:
        console.print("[dim]SEC 13F: not a resolved 13F filer (no CIK identifier attached).[/dim]")
        return
    if sec.latest_filing_date is None:
        console.print(f"[dim]SEC 13F: filer CIK {sec.cik} resolved, but no filings found.[/dim]")
        return

    console.print(
        f"[bold]SEC 13F[/bold]: filer (CIK {sec.cik}) - latest filing {sec.latest_filing_date} "
        f"for period {sec.latest_period_of_report}, {sec.reported_security_count} securities reported"
    )
    console.print(
        "[dim]This is the latest SEC Form 13F reported holdings snapshot, not a complete "
        "portfolio - 13F excludes shorts, derivatives, non-US securities, private investments, "
        "and small positions below reporting thresholds.[/dim]"
    )
    table = Table(title="Latest SEC 13F reported holdings (top 10 by value)")
    table.add_column("Issuer")
    table.add_column("Value ($000s)", justify="right")
    for h in sec.top_reported_holdings:
        table.add_row(h.name_of_issuer, f"{h.value:,}" if h.value is not None else "-")
    console.print(table)


def render(console: Console, profile: EntityProfile) -> None:
    console.print(f"\n[bold]{profile.canonical_name}[/bold]")
    console.print(f"Entity ID: {profile.entity_id}  |  Status: {profile.entity_status or 'unknown'}")
    console.print(f"Jurisdiction: {profile.jurisdiction or '-'}  |  Country: {profile.legal_country or '-'}")
    _render_identifiers(console, profile)
    _render_relationships(console, profile)
    _render_sec_13f(console, profile)
