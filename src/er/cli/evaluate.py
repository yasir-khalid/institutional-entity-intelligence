"""CLI: python -m er.cli.evaluate (or `make evaluate`)

Scores er.matching.matcher against the full benchmark and writes
data/benchmark/evaluation_report.json. All the scoring logic lives in
er.evaluation.run_benchmark - this module only sets up logging, writes the
report to disk, and prints a summary.
"""

from __future__ import annotations

import json
import logging

from er.config import load_config
from er.evaluation.run_benchmark import build_report, evaluate
from er.indexing.opensearch_index import get_client

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    client = get_client(cfg)

    results = evaluate(cfg, client)
    report = build_report(results)

    out_path = cfg.benchmark.output_dir / "evaluation_report.json"
    out_path.write_text(json.dumps(report, indent=2))
    logger.info("evaluation report written to %s", out_path)
    logger.info("overall: %s", report["overall"])


if __name__ == "__main__":
    main()
