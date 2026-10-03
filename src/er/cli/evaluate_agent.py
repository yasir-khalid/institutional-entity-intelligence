"""CLI: python -m er.cli.evaluate_agent [--junit PATH] [--baseline PATH] [--save PATH]

Runs every case in config/agent_eval_cases.yaml through the live agent and
scores it on the hard path (er.evaluation.agent_eval) next to Jev's verdict.
Requires OPENROUTER_API_KEY. Exits non-zero when any hard check fails.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.table import Table

from er.config import REPO_ROOT, load_config
from er.evaluation.agent_eval import load_cases, run_cases, to_junit


def main() -> None:
    parser = argparse.ArgumentParser(description="Hard-path evaluation of agent answers")
    parser.add_argument("--cases", type=Path, default=REPO_ROOT / "config" / "agent_eval_cases.yaml")
    parser.add_argument("--junit", type=Path, help="write JUnit XML here (for CI)")
    parser.add_argument("--baseline", type=Path, help="earlier --save output; flags fact values that changed")
    parser.add_argument("--save", type=Path, help="write this run's fact values, for a later --baseline")
    args = parser.parse_args()

    cases = load_cases(args.cases)
    baseline = json.loads(args.baseline.read_text()) if args.baseline else None
    console = Console()
    started = time.monotonic()
    with console.status(f"Running {len(cases)} agent cases..."):
        results = asyncio.run(run_cases(load_config(), cases, baseline))

    table = Table(title="Agent evaluation")
    for column in ("Case", "Hard path", "Jev", "Disagree", "Failed checks"):
        table.add_column(column)
    for result in results:
        failed = [f"{check.name}: {check.message}" for check in result.checks if not check.passed]
        table.add_row(
            result.case_id,
            f"{sum(check.passed for check in result.checks)}/{len(result.checks)}",
            result.verification_status or "-",
            "yes" if result.disagreement else "",
            "\n".join(failed),
        )
    console.print(table)

    if args.junit:
        args.junit.parent.mkdir(parents=True, exist_ok=True)
        args.junit.write_text(to_junit(results))
    if args.save:
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(json.dumps({result.case_id: result.fact_values for result in results}, indent=2))
    console.print(f"Fetched in {time.monotonic() - started:.2f}s")
    sys.exit(0 if all(result.passed for result in results) else 1)


if __name__ == "__main__":
    main()
