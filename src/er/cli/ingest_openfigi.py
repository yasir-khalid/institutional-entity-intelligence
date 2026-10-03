from __future__ import annotations

import time

from rich.console import Console

from er.config import load_config
from er.datasources.openfigi.ingest import run_all


def main() -> None:
    console = Console()
    started = time.monotonic()
    counts = run_all(load_config())
    console.print(
        f"Fetched {counts['requested']:,} CUSIPs; wrote {counts['mappings']:,} mapping rows "
        f"in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
