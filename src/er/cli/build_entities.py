"""CLI: python -m er.cli.build_entities (or `make build-entities`)

Rebuilds the canonical entity layer (entities.parquet + entity_identifiers.parquet)
from GLEIF plus every registered source in er.entity.sources. All the assembly
logic lives in er.entity.build.run_all() - this module only sets up logging and
times it.
"""

from __future__ import annotations

import logging
import time

from er.config import load_config
from er.entity.build import run_all

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    started = time.monotonic()
    counts = run_all(cfg)
    logger.info(
        "entity layer built: %d entities, %d identifiers (%.0fs)",
        counts["entities"],
        counts["identifiers"],
        time.monotonic() - started,
    )


if __name__ == "__main__":
    main()
