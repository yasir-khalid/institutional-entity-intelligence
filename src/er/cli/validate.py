"""CLI: python -m er.cli.validate (or `make validate`)

Runs er.validation.validate_all() over the processed GLEIF tables, writes the
report to disk, logs a summary, and exits non-zero if any hard failure was
found. All the actual validation logic lives in er.validation - this module
only handles I/O and the process exit code.
"""

from __future__ import annotations

import json
import logging
import sys

from er.config import load_config
from er.validation import validate_all

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    report = validate_all(cfg)

    out_path = cfg.gleif.processed_dir / "validation_report.json"
    out_path.write_text(json.dumps(report, indent=2))
    logger.info("validation report written to %s", out_path)

    for table_name, stats in report.items():
        if table_name == "hard_failures":
            continue
        logger.info("%s: %s", table_name, {k: v for k, v in stats.items() if k != "null_rates"})

    if report["hard_failures"]:
        logger.error("hard failures: %s", report["hard_failures"])
        sys.exit(1)
    logger.info("validation passed with no hard failures")


if __name__ == "__main__":
    main()
