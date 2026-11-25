from __future__ import annotations

import time

from rich.console import Console

from er.config import load_config
from er.datasources.finra_short_volume.ingest import run_all


def main() -> None:
    console = Console()
    started = time.monotonic()
    with console.status("Downloading and parsing FINRA daily short sale volume..."):
        counts = run_all(load_config())
    console.print(
        f"Ingested {counts['rows']:,} symbol-days from {counts['days']} trading days "
        f"in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
