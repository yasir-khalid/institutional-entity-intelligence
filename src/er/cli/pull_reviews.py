"""CLI: python -m er.cli.pull_reviews

Copies the human match reviews written through the API (OpenSearch is their
system of record) to the CSV that `make build-knowledge-graph` reads.
"""

from __future__ import annotations

import time

from rich.console import Console

from er.config import load_config
from er.entity.resolution import export_reviews
from er.serving.store import get_store


def main() -> None:
    console = Console()
    cfg = load_config()
    started = time.monotonic()
    with console.status("Pulling match reviews from OpenSearch..."):
        count = export_reviews(get_store(cfg), cfg.entity.review_file)
    console.print(f"Wrote {count:,} reviews to {cfg.entity.review_file}")
    console.print(f"Fetched in {time.monotonic() - started:.2f}s")


if __name__ == "__main__":
    main()
