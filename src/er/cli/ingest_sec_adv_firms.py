from __future__ import annotations

import time

from rich.console import Console

from er.config import load_config
from er.datasources.sec_adv_firms.ingest import run_all


def main() -> None:
    console = Console()
    started = time.monotonic()
    with console.status("Downloading and parsing Form ADV Part 1A monthly files..."):
        counts = run_all(load_config())
    console.print(
        f"Ingested {counts['firm_snapshots']:,} adviser snapshots and {counts['client_type_rows']:,} "
        f"client-type rows from {counts['files']} files in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
