"""CLI: python -m er.cli.crosswalk_sec_13f (or `make crosswalk-sec-13f`)

Resolves every unique SEC Form 13F filer to a GLEIF LEI. All the resolution
logic lives in er.crosswalk.sec_13f_to_gleif.build_crosswalk() - this module
only sets up logging and prints the final count.
"""

from __future__ import annotations

import logging

from er.config import load_config
from er.crosswalk.sec_13f_to_gleif import build_crosswalk

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    n = build_crosswalk(cfg)
    logger.info("crosswalk complete: %d unique filers resolved", n)


if __name__ == "__main__":
    main()
