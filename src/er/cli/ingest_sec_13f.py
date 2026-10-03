"""CLI: python -m er.cli.ingest_sec_13f (or `make ingest-sec-13f`)

Parses the latest downloaded SEC Form 13F bulk zip into data/processed/*.parquet.
All parsing logic lives in er.datasources.sec_13f.ingest.run_all() - this module
only sets up logging and prints the final summary.
"""

from __future__ import annotations

import logging

from er.config import load_config
from er.datasources.sec_13f.ingest import run_all

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    counts = run_all(cfg)
    logger.info(
        "ingestion complete: %d filings, %d holdings, %d validations, "
        "%d other managers, %d effective holdings, %d filings flagged as reported in thousands",
        counts["filings"],
        counts["holdings"],
        counts["validations"],
        counts["other_managers"],
        counts["effective_holdings"],
        counts["scale_suspect_filings"],
    )


if __name__ == "__main__":
    main()
