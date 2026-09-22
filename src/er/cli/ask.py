"""CLI: python -m er.cli.ask --question "..." [--entity-id <LEI>]

Terminal test harness for er.agent.orchestrator - spawns the MCP server (see
er.agent.mcp_server) over stdio, runs one question through the OpenRouter
tool-calling loop, and prints the answer plus its evidence, entirely outside
the web UI. Requires OPENROUTER_API_KEY in .env.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from mcp import Client
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from er.agent.orchestrator import ask, mcp_stdio_params
from er.config import load_config


async def _run(question: str, entity_id: str | None) -> None:
    console = Console()
    cfg = load_config()
    started = time.monotonic()
    with console.status("[bold cyan]Asking...[/bold cyan]"):
        async with Client(mcp_stdio_params(cfg)) as client:
            result = await ask(client, cfg, question, entity_id)
    elapsed = time.monotonic() - started

    console.print(Panel(result.answer or "[dim]no answer[/dim]", title="Answer", border_style="cyan"))

    if result.citations:
        table = Table(title="Evidence", show_header=True, header_style="bold")
        table.add_column("#", justify="right")
        table.add_column("Source")
        table.add_column("Criteria")
        table.add_column("Records", justify="right")
        table.add_column("As of")
        for c in result.citations:
            ev = result.evidence.get(c.evidence_id)
            if ev is None:
                continue
            table.add_row(
                str(c.marker),
                ev.source,
                "; ".join(ev.criteria),
                str(ev.result_count) if ev.result_count is not None else "—",
                ev.source_timestamp or "—",
            )
        console.print(table)
    else:
        console.print("[dim]No citations returned.[/dim]")

    console.print(f"\n[dim]Answered in {elapsed:.2f}s[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the entity-intelligence agent a question")
    parser.add_argument("--question", required=True)
    parser.add_argument("--entity-id", default=None, help="GLEIF LEI to scope the question to, if any")
    args = parser.parse_args()
    asyncio.run(_run(args.question, args.entity_id))


if __name__ == "__main__":
    main()
