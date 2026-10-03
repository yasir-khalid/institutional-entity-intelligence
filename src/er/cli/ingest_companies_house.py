from __future__ import annotations

import time

from rich.console import Console

from er.config import load_config
from er.datasources.companies_house.ingest import run_all


def main() -> None:
    console = Console()
    started = time.monotonic()
    with console.status("Ingesting Companies House snapshots..."):
        counts = run_all(load_config())
    console.print(
        f"Ingested {counts['companies']:,} companies and {counts['psc']:,} PSC records "
        f"in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
