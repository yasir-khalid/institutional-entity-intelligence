"""CLI: python -m er.cli.publish [--only entities --only 13f_holdings ...]

Builds the OpenSearch serving indexes the API reads from processed Parquet
(er.serving.publish). Each index is loaded under a new name and swapped in
behind its alias only when complete.
"""

from __future__ import annotations

import argparse
import logging
import time

from rich.console import Console
from rich.table import Table

from er.config import load_config
from er.serving.publish import BUILDERS, run_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish processed Parquet to the OpenSearch serving indexes")
    parser.add_argument("--only", action="append", choices=list(BUILDERS), help="publish just this index; repeatable")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("opensearch").setLevel(logging.WARNING)

    console = Console()
    started = time.monotonic()
    counts = run_all(load_config(), only=args.only)
    table = Table(title="Published")
    table.add_column("Index")
    table.add_column("Documents", justify="right")
    for name, count in counts.items():
        table.add_row(name, f"{count:,}")
    console.print(table)
    console.print(f"Fetched in {time.monotonic() - started:.2f}s")


if __name__ == "__main__":
    main()
