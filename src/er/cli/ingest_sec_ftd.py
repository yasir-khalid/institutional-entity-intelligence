from __future__ import annotations

import time

from rich.console import Console

from er.config import load_config
from er.datasources.sec_ftd.ingest import run_all


def main() -> None:
    console = Console()
    started = time.monotonic()
    with console.status("Downloading and parsing SEC fails-to-deliver files..."):
        counts = run_all(load_config())
    console.print(
        f"Ingested {counts['rows']:,} fails-to-deliver rows from {counts['files']} files "
        f"in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
