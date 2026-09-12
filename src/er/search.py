"""CLI: python -m er.search --name "Albacore Partners I Master Fund" --country IE"""

from __future__ import annotations

import argparse

from rich.console import Console
from rich.table import Table

from er.config import load_config
from er.indexing.opensearch_index import get_client
from er.retrieval.candidates import search_candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Search GLEIF candidate entities")
    parser.add_argument("--name", required=True)
    parser.add_argument("--country", default=None, help="ISO alpha-2, e.g. IE")
    parser.add_argument("--size", type=int, default=None)
    args = parser.parse_args()

    console = Console()
    cfg = load_config()
    client = get_client(cfg)
    results = search_candidates(client, cfg, args.name, args.country, args.size)

    if not results:
        console.print("[dim]No candidates found.[/dim]")
        return

    table = Table(title=f'Candidates for "{args.name}"', show_header=True, header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Legal name")
    table.add_column("LEI")
    table.add_column("Jurisdiction")
    table.add_column("Country")
    table.add_column("Score", justify="right")
    for r in results:
        table.add_row(
            str(r["rank"]),
            r["legal_name"],
            r["lei"],
            str(r.get("jurisdiction") or ""),
            str(r.get("legal_country") or ""),
            f"{r['score']:.2f}",
        )
    console.print(table)


if __name__ == "__main__":
    main()
