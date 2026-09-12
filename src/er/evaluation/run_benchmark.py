"""Runs the deterministic matcher (er.matching.matcher) against every row of
data/benchmark/evaluation_pairs.parquet and reports retrieval/decision quality.
Makes one live OpenSearch query per row - this is a one-off evaluation script, not
something wired into a hot path, so no batching/parallelism in this first pass.

CLI entry point: `python -m er.cli.evaluate` (or `make evaluate`) - writes the
report to disk and logs a summary. This module's evaluate()/build_report() have
no I/O concerns of their own.
"""

from __future__ import annotations

import logging
import time

import pyarrow.parquet as pq

from er.evaluation.metrics import RowResult, summarize
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
                conflict_type=p["conflict_type"],
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
        # Slices dangerous_failure_rate/failure_breakdown per hard_negatives conflict
        # type (fund_number / master_feeder / other_same_core) - without this, a fix
        # targeted at one conflict type (e.g. experiment 003's master/feeder fix) is
        # invisible in the aggregate confusable_pair metric whenever that type is a
        # small fraction of the sampled pool.
        "by_conflict_type": {
            c: summarize([r for r in results if r.conflict_type == c])
            for c in ("fund_number", "master_feeder", "other_same_core")
        },
    }


