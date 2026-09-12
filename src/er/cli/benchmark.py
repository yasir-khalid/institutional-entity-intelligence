"""CLI: python -m er.cli.benchmark (or `make benchmark`)

Regenerates the auto-labeled ER benchmark from the ISIN<->LEI bridge and
intra-GLEIF confusable-name groups. All generation logic lives in
er.benchmark.generate.run_all() - this module only sets up logging and times it.
"""

from __future__ import annotations

import logging
import time

from er.benchmark.generate import run_all
from er.config import load_config

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    started = time.monotonic()
    run_all(cfg)
    logger.info("benchmark generation complete in %.0fs", time.monotonic() - started)


if __name__ == "__main__":
    main()
