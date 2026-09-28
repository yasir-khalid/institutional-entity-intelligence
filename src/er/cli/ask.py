"""CLI: python -m er.cli.ask --question "..." [--entity-id <LEI>]

Terminal test harness for er.agent.orchestrator - spawns the MCP server (see
er.agent.mcp_server) over stdio, runs one question through the OpenRouter
tool-calling loop, and prints the answer, its Jev verification badge (see
er.agent.verifier), and its evidence, entirely outside the web UI. Requires
OPENROUTER_API_KEY in .env. Rendering lives in er.cli.ask_render.
"""

from __future__ import annotations

import argparse
import asyncio
import time

from mcp import Client
from rich.console import Console

from er.agent.orchestrator import ask, mcp_stdio_params
from er.cli.ask_render import render_result
from er.config import load_config


async def _run(question: str, entity_id: str | None) -> None:
    console = Console()
    cfg = load_config()
    started = time.monotonic()
    with console.status("[bold cyan]Asking...[/bold cyan]"):
        async with Client(mcp_stdio_params(cfg)) as client:
            result = await ask(client, cfg, question, entity_id)
    elapsed = time.monotonic() - started

    render_result(console, result)
    console.print(f"\n[dim]Answered in {elapsed:.2f}s[/dim]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the entity-intelligence agent a question")
    parser.add_argument("--question", required=True)
    parser.add_argument("--entity-id", default=None, help="GLEIF LEI to scope the question to, if any")
    args = parser.parse_args()
    asyncio.run(_run(args.question, args.entity_id))


if __name__ == "__main__":
    main()
