"""CLI: python -m er.family --name "Point72"

Different operation from er.match: retrieves and groups the SET of legal entities
that make up a brand/institutional family, rather than resolving to one entity.
Never forces a single winner - members are grouped by confidence (HIGH: exact
brand-core match; POSSIBLE: a real sub-brand or lookalike that extends the brand
core but isn't identical) and role (management vs. fund/vehicle), with any
confirming GLEIF relationship evidence shown separately.
"""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table

from er.config import load_config
from er.family.discover import discover_family
from er.family.models import FamilyMember, FamilyResult
from er.indexing.opensearch_index import get_client


def _members_table(title: str, members: list[FamilyMember]) -> Table:
    table = Table(title=title, show_header=True, header_style="bold")
    table.add_column("Legal name")
    table.add_column("LEI")
    table.add_column("Jurisdiction")
    table.add_column("Graph-confirmed")
    for m in members:
        table.add_row(m.legal_name, m.lei, m.jurisdiction or "?", "✓" if m.graph_confirmed else "")
    return table


def render(console: Console, result: FamilyResult) -> None:
    console.print(f'[bold]Institutional family:[/bold] "{result.query_name}"  (brand core: "{result.brand_core}")\n')

    if not result.members:
        console.print("[dim]No family members found.[/dim]")
        return

    high = [m for m in result.members if m.confidence == "high"]
    possible = [m for m in result.members if m.confidence == "possible"]

    high_mgmt = [m for m in high if m.role == "management"]
    high_fund = [m for m in high if m.role == "fund"]

    if high_mgmt:
        console.print(_members_table("Management entities (HIGH confidence)", high_mgmt))
    if high_fund:
        console.print(_members_table("Funds / vehicles (HIGH confidence)", high_fund))
    if possible:
        console.print(_members_table("Possible related entities (not confirmed)", possible))

    if result.relationship_evidence:
        evidence_table = Table(title="Relationship evidence", show_header=True, header_style="bold yellow")
        evidence_table.add_column("From")
        evidence_table.add_column("Relationship")
        evidence_table.add_column("To")
        for e in result.relationship_evidence:
            evidence_table.add_row(e.from_name or e.from_lei, e.relationship_type, e.to_name or e.to_lei)
        console.print(evidence_table)


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover the legal entities that make up a brand/institutional family")
    parser.add_argument("--name", required=True)
    parser.add_argument("--country", default=None, help="ISO alpha-2 or common alias - narrows, doesn't restrict to one country")
    args = parser.parse_args()

    console = Console()
    cfg = load_config()
    client = get_client(cfg)
    result = discover_family(client, cfg, args.name, args.country)
    render(console, result)


if __name__ == "__main__":
    main()
