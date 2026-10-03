from __future__ import annotations

import time

from rich.console import Console

from er.config import load_config
from er.knowledge.build import run_all


def main() -> None:
    console = Console()
    started = time.monotonic()
    with console.status("Building typed knowledge graph..."):
        counts = run_all(load_config())
    console.print(
        f"Built {counts['nodes']:,} nodes, {counts['edges']:,} edges, and "
        f"{counts['identifiers']:,} identifiers; materialized {counts['facts']:,} facts "
        f"in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
