from __future__ import annotations

import time

from rich.console import Console

from er.config import load_config
from er.datasources.sec_form_d.ingest import run_all


def main() -> None:
    console = Console()
    started = time.monotonic()
    with console.status("Downloading and parsing Form D data sets..."):
        counts = run_all(load_config())
    console.print(
        f"Ingested {counts['offerings']:,} offerings, {counts['people']:,} related persons and "
        f"{counts['recipients']:,} sales recipients from {counts['quarters']} quarters "
        f"in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
