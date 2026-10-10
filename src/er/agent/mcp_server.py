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
from er.agent.tools import get_beneficial_owners as _get_beneficial_owners
from er.agent.tools import get_entity_connections as _get_entity_connections
from er.agent.tools import get_fund_structure as _get_fund_structure
from er.agent.tools import get_security as _get_security
from er.agent.tools import get_position_history as _get_position_history
from er.agent.tools import search_adv_documents as _search_adv_documents
from er.config import load_config
from er.serving.store import get_store

mcp = MCPServer(
    name="institutional-entity-intelligence",
    instructions=(
        "Tools for answering questions about legal entities (companies, funds, managers) "
        "resolved from GLEIF, SEC, Companies House and FFIEC data. Start with search_entity if "
        "you don't already have an entity_id (a GLEIF LEI); use get_entity_profile, "
        "get_relationship_hierarchy and get_entity_connections once you do. get_position_history and get_beneficial_owners take SEC CIKs, which "
        "get_entity_profile returns for 13F filers. get_fund_structure answers which series and "
        "share classes a fund registrant has; get_security says what a CUSIP, ticker or FIGI is."
    ),
)


@mcp.tool()
def search_entity(query: str, search_type: str = "name", country: str | None = None) -> ToolResult:
    """Search for an entity by legal name, LEI, or CUSIP. search_type must be
    one of "name", "lei", "cusip". Returns candidate entities with their
    entity_id (a GLEIF LEI) - pass that to get_entity_profile or
    get_relationship_hierarchy for detail."""
    return _search_entity(load_config(), get_store(load_config()), query, search_type=search_type, country=country)


@mcp.tool()
def get_entity_profile(entity_id: str) -> ToolResult:
    """Get an entity's full profile: identity, GLEIF registration lineage,
    every attached identifier (LEI/CIK/ISIN/...) with its source, latest
    SEC 13F filing activity if it is a resolved 13F filer, and the latest
    Form N-PORT report (net assets, largest holdings) if it is a registered
    fund series. entity_id is a GLEIF LEI."""
    return _get_entity_profile(get_store(load_config()), entity_id)


@mcp.tool()
def get_relationship_hierarchy(entity_id: str, depth: int = 2, direction: str = "all") -> ToolResult:
    """Get an entity's GLEIF relationship neighborhood: parents/managers
    upward, subsidiaries/funds downward, up to `depth` hops. direction must be
    one of "all", "parents", "children". entity_id is a GLEIF LEI."""
    return _get_relationship_hierarchy(get_store(load_config()), entity_id, depth=depth, direction=direction)


@mcp.tool()
def search_adv_documents(query: str, crd_number: str | None = None, limit: int = 10) -> ToolResult:
    """Search ingested Form ADV brochure pages for an exact phrase
    (case-insensitive) - a short string that literally appears in a brochure,
    such as a firm name or a section heading like "Fees and Compensation",
    not a list of keywords. Each match carries the text that follows it and
    its exact PDF page address. Pass the crd_number from an earlier match to
    restrict the search to one adviser."""
    return _search_adv_documents(get_store(load_config()), query, crd_number=crd_number, limit=limit)


@mcp.tool()
def get_position_history(cik: str, cusip: str, periods: int = 4) -> ToolResult:
    """A 13F manager's reported long position in one CUSIP over its recent
    report dates. Period totals and changes are derived facts computed by
    registered formulas - cite those instead of doing arithmetic yourself."""
    return _get_position_history(get_store(load_config()), cik, cusip, periods=periods)


@mcp.tool()
def get_beneficial_owners(issuer_cik: str, limit: int = 25) -> ToolResult:
    """Persons reporting over 5% of an issuer's equity class on Schedule 13D
    (active intent) or 13G (passive). This is beneficial ownership - distinct
    from 13F investment discretion and from a GLEIF accounting parent."""
    return _get_beneficial_owners(get_store(load_config()), issuer_cik, limit=limit)


@mcp.tool()
def get_entity_connections(entity_id: str, edge_type: str | None = None) -> ToolResult:
    """An entity's relationships outside GLEIF's accounting hierarchy, one group
    per kind of claim: SIGNIFICANT_CONTROL (UK Companies House persons with
    significant control), BANK_CONTROL_PARENT (FFIEC NIC), BENEFICIAL_OWNER
    (Schedule 13D/G), INSIDER_OF (Forms 3/4/5) and SUCCEEDED_BY (LEI
    successions), plus records in other sources linked to this LEI (SEC CIK,
    UK company number, RSSD). A connection with valid_to has ended - never
    present it as current. Pass edge_type to get one kind only."""
    return _get_entity_connections(get_store(load_config()), entity_id, edge_type=edge_type)


@mcp.tool()
def get_fund_structure(identifier: str, id_type: str = "lei") -> ToolResult:
    """A registered fund's structure from SEC's series/class register: the
    registrant, its fund series and each series' share classes with tickers.
    id_type is one of "lei" (registrant or series LEI), "cik" (registrant),
    "series_id" (S000...), "class_id" (C000...) or "ticker". A registrant LEI
    or CIK returns all its series; anything else returns the matching series."""
    return _get_fund_structure(get_store(load_config()), identifier, id_type=id_type)


@mcp.tool()
def get_security(identifier: str, id_type: str = "cusip") -> ToolResult:
    """What a security is, from OpenFIGI's mapping of the CUSIPs in 13F
    filings: name, ticker, security type, share-class and composite FIGIs.
    id_type is one of "cusip", "ticker" or "figi". A CUSIP with status
    "ambiguous" maps to several share classes - say so rather than picking
    one; "no_match" means OpenFIGI didn't recognise it. Only CUSIPs that
    appear in 13F filings are covered."""
    return _get_security(get_store(load_config()), identifier, id_type=id_type)


def run() -> None:
    mcp.run()


if __name__ == "__main__":
    run()
