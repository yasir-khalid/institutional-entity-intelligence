"""A standalone MCP server exposing a few read-only tools for answering
questions about entities in this dataset: search, full profile, and GLEIF
relationship hierarchy. Runnable directly by any MCP client (Claude Desktop,
Cursor, ...) via `python -m er.cli.mcp_server` (stdio transport) - er.agent's
own OpenRouter-backed agent (er.agent.orchestrator) is just one more client of
this same server, not a special case.

No entity-resolution logic lives here - see er.agent.tools, which this module
only wraps with MCP's tool-registration decorator and JSON-schema plumbing.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer

from er.agent.models import ToolResult
from er.agent.tools import get_entity_profile_tool as _get_entity_profile
from er.agent.tools import get_relationship_hierarchy as _get_relationship_hierarchy
from er.agent.tools import search_entity as _search_entity
from er.config import load_config

mcp = MCPServer(
    name="institutional-entity-intelligence",
    instructions=(
        "Tools for answering questions about legal entities (companies, funds, managers) "
        "resolved from GLEIF and SEC 13F data. Start with search_entity if you don't already "
        "have an entity_id (a GLEIF LEI); use get_entity_profile and get_relationship_hierarchy "
        "once you do."
    ),
)


@mcp.tool()
def search_entity(query: str, search_type: str = "name", country: str | None = None) -> ToolResult:
    """Search for an entity by legal name, LEI, or CUSIP. search_type must be
    one of "name", "lei", "cusip". Returns candidate entities with their
    entity_id (a GLEIF LEI) - pass that to get_entity_profile or
    get_relationship_hierarchy for detail."""
    return _search_entity(load_config(), query, search_type=search_type, country=country)


@mcp.tool()
def get_entity_profile(entity_id: str) -> ToolResult:
    """Get an entity's full profile: identity, GLEIF registration lineage,
    every attached identifier (LEI/CIK/ISIN/...) with its source, and latest
    SEC 13F filing activity if it is a resolved 13F filer. entity_id is a
    GLEIF LEI."""
    return _get_entity_profile(load_config(), entity_id)


@mcp.tool()
def get_relationship_hierarchy(entity_id: str, depth: int = 2, direction: str = "all") -> ToolResult:
    """Get an entity's GLEIF relationship neighborhood: parents/managers
    upward, subsidiaries/funds downward, up to `depth` hops. direction must be
    one of "all", "parents", "children". entity_id is a GLEIF LEI."""
    return _get_relationship_hierarchy(load_config(), entity_id, depth=depth, direction=direction)


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
