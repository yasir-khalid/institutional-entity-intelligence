from __future__ import annotations

import argparse
import logging
import time

from rich.console import Console

from er.config import load_config
from er.datasources.sec_13dg.ingest import run_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest structured Schedule 13D/13G filings from EDGAR.")
    parser.add_argument("--quarter", action="append", help="e.g. 2026Q2; repeatable (default: config/dev.yaml)")
    parser.add_argument("--limit", type=int, help="read only the N most recent filings")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    console = Console()
    started = time.monotonic()
    with console.status("Reading Schedule 13D/G filings from EDGAR..."):
        counts = run_all(load_config(), quarters=args.quarter, limit=args.limit)
    console.print(
        f"Read {counts['documents']:,} of {counts['filings']:,} filings "
        f"({counts['missing']:,} without structured XML) into {counts['rows']:,} reporting-person rows "
        f"in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
