"""CLI entrypoint: python -m er.cli.mcp_server

Runs the entity-intelligence MCP server over stdio - point any MCP client
(Claude Desktop, Cursor, er.agent.orchestrator) at this command. All tool
logic lives in er.agent (mcp_server.py registers the tools, tools.py
implements them) - this module is just the process entrypoint, same rule as
every other er.cli module.
"""

from __future__ import annotations

from er.agent.mcp_server import run

if __name__ == "__main__":
    run()
