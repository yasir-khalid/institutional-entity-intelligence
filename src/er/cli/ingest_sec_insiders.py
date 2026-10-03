from __future__ import annotations

import time

from rich.console import Console

from er.config import load_config
from er.datasources.sec_insiders.ingest import run_all


def main() -> None:
    console = Console()
    started = time.monotonic()
    with console.status("Ingesting SEC insider transactions..."):
        counts = run_all(load_config())
    console.print(
        f"Ingested {counts['relationships']:,} owner relationships and "
        f"{counts['transactions']:,} transactions in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
