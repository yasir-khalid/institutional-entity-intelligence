"""CLI: python -m er.cli.ingest_gleif (or `make ingest-gleif`)

Parses all four raw GLEIF files into data/processed/*.parquet. All parsing
logic lives in er.datasources.gleif.ingest.run_all() - this module only sets up
logging and prints the final summary.
"""

from __future__ import annotations

import logging

from er.config import load_config
from er.datasources.gleif.ingest import run_all

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    counts = run_all(cfg)
    logger.info(
        "ingestion complete: %d entities, %d relationships, %d relationship_exceptions, %d isin_lei",
        counts["entities"],
        counts["relationships"],
        counts["relationship_exceptions"],
        counts["isin_lei"],
    )


if __name__ == "__main__":
    main()
