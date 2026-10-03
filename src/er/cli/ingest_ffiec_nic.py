from __future__ import annotations

import time

from rich.console import Console

from er.config import load_config
from er.datasources.ffiec_nic.ingest import run_all


def main() -> None:
    console = Console()
    started = time.monotonic()
    with console.status("Ingesting FFIEC NIC bank hierarchy..."):
        counts = run_all(load_config())
    console.print(
        f"Ingested {counts['institutions']:,} institutions, {counts['relationships']:,} relationships "
        f"and {counts['transformations']:,} transformations in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
