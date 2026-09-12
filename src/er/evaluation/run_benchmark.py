"""CLI: python -m er.evaluation.run_benchmark

Runs the deterministic matcher (er.matching.matcher) against every row of
data/benchmark/evaluation_pairs.parquet and reports retrieval/decision quality.
Makes one live OpenSearch query per row - this is a one-off evaluation script, not
something wired into a hot path, so no batching/parallelism in this first pass.
"""

from __future__ import annotations

import json
import logging
import time

import pyarrow.parquet as pq

from er.config import load_config
from er.evaluation.metrics import RowResult, summarize
from er.indexing.opensearch_index import get_client
from er.matching.matcher import match

logger = logging.getLogger(__name__)

LOG_EVERY = 500


def evaluate(cfg, client) -> list[RowResult]:
    table = pq.read_table(cfg.benchmark.output_dir / "evaluation_pairs.parquet")
    pairs = table.to_pylist()

    results = []
    started = time.monotonic()
    for i, p in enumerate(pairs):
        result = match(client, cfg, p["query_name"], p["query_country"])
        results.append(
            RowResult(
                pair_id=p["pair_id"],
                case_type=p["case_type"],
                difficulty=p["difficulty"],
                expected_lei=p["expected_lei"],
                confusable_lei=p["confusable_lei"],
                candidate_leis=[c.lei for c in result.candidates],
                decision=result.decision.value,
                chosen_lei=result.lei,
            )
        )
        if (i + 1) % LOG_EVERY == 0:
            elapsed = time.monotonic() - started
            logger.info("%d/%d evaluated (%.0fs, %.1f/s)", i + 1, len(pairs), elapsed, (i + 1) / elapsed)

    return results


def build_report(results: list[RowResult]) -> dict:
    return {
        "overall": summarize(results),
        "by_difficulty": {
            d: summarize([r for r in results if r.difficulty == d]) for d in ("easy", "medium", "hard")
        },
        "by_case_type": {
            c: summarize([r for r in results if r.case_type == c])
            for c in ("isin_confirmed", "confusable_pair")
        },
    }


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
