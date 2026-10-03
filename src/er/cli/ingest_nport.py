from __future__ import annotations

import time

from rich.console import Console

from er.config import load_config
from er.datasources.nport.ingest import run_all


def main() -> None:
    console = Console()
    started = time.monotonic()
    with console.status("Ingesting SEC N-PORT data..."):
        counts = run_all(load_config())
    console.print(
        f"Ingested {counts['funds']:,} funds, {counts['holdings']:,} holdings, and "
        f"{counts['observed_security_issuers']:,} observed identifier links "
        f"in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
