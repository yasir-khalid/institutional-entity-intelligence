from __future__ import annotations

import logging
import time

from rich.console import Console

from er.config import load_config
from er.datasources.sec_xbrl.ingest import run_all


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    console = Console()
    started = time.monotonic()
    with console.status("Ingesting SEC XBRL company facts..."):
        counts = run_all(load_config())
    console.print(
        f"Ingested {counts['facts']:,} facts for {counts['issuers']:,} issuers "
        f"in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
