"""Tool implementations backing er.agent.mcp_server. Each function wraps
*existing* core logic completely unchanged (er.entity.search,
er.entity.profile, er.graph.build) - this module adds no entity-resolution
logic of its own, same rule as er.api.app and er.cli. Its only addition is
constructing deterministic Evidence records alongside the data for every
call, so a consumer (er.agent.orchestrator, or any other MCP client) can cite
exactly what was looked up rather than the model asserting an answer.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from urllib.parse import quote

from er.config import AppConfig
from er.datasources.sec_adv.search import search_pages
from er.entity.advisers import resolve_adviser
from er.entity.connections import load_connections
from er.entity.funds import FUND_ID_TYPES, load_fund_series
from er.entity.models import NPortFundReport
from er.entity.ownership import load_beneficial_owners
from er.entity.positions import load_position_rows
from er.entity.market import load_fails, load_ownership, load_short_volume, resolve_security
from er.entity.offerings import search_offerings
from er.entity.profile import get_entity_profile
from er.entity.securities import SECURITY_ID_TYPES, load_securities
from er.entity.search import match_result_to_matches, search_by_cusip, search_by_lei, search_by_name
from er.entity.xbrl import balance_check, cik_of, known_on, load_series, normalise_unit, resolve_issuer
from er.graph.build import build_hierarchy_tree
from er.graph.models import HierarchyNode
from er.knowledge.formulas import FORMULAS
from er.matching.decisions import config_fingerprint
from er.serving.store import Store

from .models import Derivation, Evidence, Fact, FactAddress, ToolResult


THIRTEEN_F_CAVEAT = (
    "Latest reported 13F holdings only - excludes short positions, derivatives, "
    "non-US securities, private investments and sub-threshold positions."
)
NPORT_CAVEAT = (
    "Form N-PORT is a dated monthly snapshot made public with a 60-day lag - "
    "the portfolio as of the report date, not today."
)
XBRL_CAVEAT = (
    "SEC XBRL company facts are the values the issuer tagged in its own EDGAR "
    "filing; they are as-reported, not adjusted, and an amended filing (10-K/A) "
    "restates a period rather than correcting the original in place. Each value "
    "is dated by the filing it came from, so a later filing can revise an "
    "earlier period."
)


def _evidence_id() -> str:
    return f"ev_{uuid.uuid4().hex[:10]}"


def _query_hash(tool_name: str, **kwargs: object) -> str:
    payload = f"{tool_name}:" + ",".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _fact(
    evidence: Evidence,
    *,
    subject: str,
    predicate: str,
    value: str | int | float | bool | None,
    document_id: str,
    locator: str,
    field: str,
    unit: str | None = None,
    as_of: str | None = None,
    provenance_class: str = "SOURCE_FACT",
    uri: str | None = None,
    page: int | None = None,
    char_start: int | None = None,
    char_end: int | None = None,
) -> Fact:
    address = FactAddress(
        source=evidence.source,
        document_id=document_id,
        snapshot_id=evidence.source_timestamp,
        locator=locator,
        field=field,
        uri=uri,
        page=page,
        char_start=char_start,
        char_end=char_end,
    )
    key = json.dumps(
        [address.model_dump(), subject, predicate, value, unit, as_of],
        sort_keys=True,
        separators=(",", ":"),
    )
    return Fact(
        fact_id=f"f_{hashlib.sha256(key.encode()).hexdigest()[:16]}",
        evidence_id=evidence.evidence_id,
        subject=subject,
        predicate=predicate,
        value=value,
        unit=unit,
        as_of=as_of,
        provenance_class=provenance_class,  # type: ignore[arg-type]
        address=address,
    )


def search_entity(
    cfg: AppConfig, store: Store, query: str, search_type: str = "name", country: str | None = None
) -> ToolResult:
    """Search for an entity by name, LEI, or CUSIP. Returns candidate entities
    with their entity_id (LEI) - pass that entity_id to get_entity_profile or
    get_relationship_hierarchy for detail. search_type must be one of "name",
    "lei", "cusip"."""
    qh = _query_hash("search_entity", query=query, search_type=search_type, country=country)

    match_result = None
    if search_type == "lei":
        lei = query.strip().upper()
        matches = search_by_lei(store, lei)
        source = "GLEIF entity record (exact LEI lookup)"
        criteria = [f"Entity ID = {lei}"]
        fact_type: str = "lookup"
    elif search_type == "cusip":
        cusip = query.strip().upper()
        matches = search_by_cusip(store, cusip)
        source = "SEC 13F holdings crosswalked to GLEIF"
        criteria = [f"CUSIP = {cusip}"]
        fact_type = "lookup"
    elif search_type == "name":
        match_result = search_by_name(cfg, query, country)
        matches = match_result_to_matches(match_result)
        source = "OpenSearch candidate retrieval + deterministic matching (er.matching.matcher)"
        criteria = [f'Query name = "{query}"']
        if country:
            criteria.append(f"Country = {country}")
        criteria.append(f"Matcher decision = {match_result.decision.value}")
        criteria.append(f"Matching config = {config_fingerprint(cfg.matching)}")
        fact_type = "search_match"
    else:
        raise ValueError(f'search_type must be one of "name", "lei", "cusip"; got {search_type!r}')

    evidence = Evidence(
        evidence_id=_evidence_id(),
        source=source,
        fact_type=fact_type,  # type: ignore[arg-type]
        criteria=criteria,
        record_refs=[m.entity_id for m in matches],
        fields_used=["canonical_name", "jurisdiction", "legal_country"],
        result_count=len(matches),
        query_hash=qh,
    )
    facts = [
        _fact(
            evidence,
            subject=f"search:{query}",
            predicate="search.result_count",
            value=len(matches),
            document_id=qh,
            locator=f"search_entity:{qh}",
            field="result_count",
        )
    ]
    if match_result is not None:
        config_hash = config_fingerprint(cfg.matching)
        decision_values = {
            "match.decision": match_result.decision.value,
            "match.selected_lei": match_result.lei,
            "match.score": match_result.score,
            "match.runner_up_gap": match_result.gap,
        }
        for predicate, value in decision_values.items():
            if value is None:
                continue
            facts.append(
                _fact(
                    evidence,
                    subject=f"search:{query}",
                    predicate=predicate,
                    value=value,
                    document_id=qh,
                    locator=f"match:{qh}:config={config_hash}",
                    field=predicate.removeprefix("match."),
                )
            )
        for feature, contribution in match_result.evidence.items():
            facts.append(
                _fact(
                    evidence,
                    subject=match_result.lei or f"search:{query}",
                    predicate=f"match.feature.{feature}",
                    value=contribution,
                    document_id=qh,
                    locator=f"match:{qh}:config={config_hash}:feature={feature}",
                    field="contribution",
                )
            )
    private_matches = []
    if search_type == "name":
        try:
            from er.knowledge.private_entities import load_private_entities

            registry = load_private_entities()
            private_matches = [
                {
                    "entity_id": e.id,
                    "name": e.name,
                    "jurisdiction": e.jurisdiction,
                    "resolution_status": "PROVISIONAL",
                    "confidence": e.confidence,
                }
                for e in registry.find(query, limit=5)
            ]
        except (FileNotFoundError, ValueError):
            private_matches = []
    return ToolResult(
        data={"matches": [m.model_dump() for m in matches],
              **({"private_entity_matches": private_matches} if private_matches else {})},
        evidence=[evidence], facts=facts,
    )


def _private_entity_facts(registry, entity, evidence: Evidence) -> list[Fact]:
    """Facts for outgoing and incoming curated relationships, so an ownership
    statement can cite a percentage instead of typing it."""
    facts: list[Fact] = [
        _fact(evidence, subject=entity.id, predicate="private_entity.name", value=entity.name,
              document_id=entity.id, locator=f"private_entities.json:{entity.id}", field="name")
    ]
    if entity.registration_id:
        facts.append(_fact(evidence, subject=entity.id, predicate="private_entity.registration_id",
                           value=entity.registration_id, document_id=entity.id,
                           locator=f"private_entities.json:{entity.id}", field="registration_id"))
    for rel in entity.relationships:
        if rel.pct is not None:
            facts.append(_fact(evidence, subject=entity.id, predicate=f"private_relationship.{rel.type}.pct",
                               value=rel.pct, unit="percent", document_id=entity.id,
                               locator=f"private_entities.json:{entity.id}:to={rel.to}", field="pct"))
    for other in registry.entities.values():
        for rel in other.relationships:
            if rel.to == entity.id and rel.pct is not None:
                facts.append(_fact(evidence, subject=entity.id,
                                   predicate=f"private_relationship.incoming.{rel.type}.pct",
                                   value=rel.pct, unit="percent", document_id=entity.id,
                                   locator=f"private_entities.json:{other.id}:to={entity.id}", field="pct"))
    return facts


def lookup_private_entity(query: str, jurisdiction: str | None = None, limit: int = 10) -> ToolResult:
    """Search the curated private-entity registry for SPVs and project companies
    that have no GLEIF LEI. Results are PROVISIONAL: cited to a public source,
    never merged into the canonical GLEIF entity layer."""
    from er.knowledge.private_entities import load_private_entities

    qh = _query_hash("lookup_private_entity", query=query, jurisdiction=jurisdiction, limit=limit)
    try:
        registry = load_private_entities()
    except FileNotFoundError:
        return ToolResult(data={"found": False, "matches": [],
                                "reason": "private-entity registry is not installed"},
                          evidence=[Evidence(evidence_id=_evidence_id(),
                                             source="Curated private-entity registry",
                                             fact_type="lookup", criteria=[f'Query name = "{query}"'],
                                             result_count=0, query_hash=qh,
                                             warnings=["Private-entity registry is not installed."])])
    matches = registry.find(query, jurisdiction=jurisdiction, limit=limit)
    evidence = Evidence(
        evidence_id=_evidence_id(),
        source="Curated private-entity registry",
        fact_type="records",
        criteria=[f'Query name = "{query}"'] + ([f"Jurisdiction = {jurisdiction}"] if jurisdiction else []),
        record_refs=[e.id for e in matches],
        fields_used=["name", "aliases", "jurisdiction", "registration_id", "relationships"],
        result_count=len(matches),
        query_hash=qh,
        warnings=[
            "PROVISIONAL: these are curated public-source records for private SPVs, not GLEIF LEI records. "
            "Do not present them as registry-verified ownership; cite the attached source and date."
        ],
    )
    facts: list[Fact] = []
    for e in matches:
        facts.extend(_private_entity_facts(registry, e, evidence))
    return ToolResult(data={"found": bool(matches), "matches": [registry.payload(e) for e in matches]},
                      evidence=[evidence], facts=facts)


def get_private_entity(entity_id: str) -> ToolResult:
    """Read one curated private-entity record by its provisional id."""
    from er.knowledge.private_entities import load_private_entities

    qh = _query_hash("get_private_entity", entity_id=entity_id)
    try:
        registry = load_private_entities()
    except FileNotFoundError:
        return ToolResult(data={"found": False, "entity": None, "reason": "private-entity registry is not installed"},
                          evidence=[Evidence(evidence_id=_evidence_id(),
                                             source="Curated private-entity registry",
                                             fact_type="lookup", criteria=[f"Entity ID = {entity_id}"],
                                             result_count=0, query_hash=qh,
                                             warnings=["Private-entity registry is not installed."])])
    entity = registry.get(entity_id)
    evidence = Evidence(
        evidence_id=_evidence_id(),
        source="Curated private-entity registry",
        fact_type="lookup",
        criteria=[f"Entity ID = {entity_id}"],
        record_refs=[entity_id],
        fields_used=["name", "aliases", "jurisdiction", "registration_id", "relationships"],
        result_count=1 if entity else 0,
        query_hash=qh,
        warnings=["PROVISIONAL: curated public-source record, not a GLEIF LEI."],
    )
    return ToolResult(data={"found": entity is not None, "entity": registry.payload(entity) if entity else None},
                      evidence=[evidence],
                      facts=_private_entity_facts(registry, entity, evidence) if entity else [])


def get_security_holders(cfg: AppConfig, identifier: str, id_type: str = "name", limit: int = 25) -> ToolResult:
    """Reverse N-PORT lookup: which registered fund reports hold a security
    issued by this name or CUSIP, and how much they report at the snapshot date."""
    from er.knowledge.nport_holders import NPORT_SOURCE_URI, find_nport_holders

    qh = _query_hash("get_security_holders", identifier=identifier, id_type=id_type, limit=limit)
    result = find_nport_holders(cfg, identifier, id_type=id_type, limit=limit)
    evidence = Evidence(
        evidence_id=_evidence_id(),
        source="SEC Form N-PORT holdings (reverse issuer lookup)",
        source_timestamp=result.get("holders", [{}])[0].get("report_date") if result.get("holders") else None,
        fact_type="records",
        criteria=[f"Identifier = {identifier}", f"Identifier type = {id_type}"],
        record_refs=[h["accession_number"] for h in result.get("holders", [])],
        fields_used=["registrant_name", "series_name", "issuer_name", "issuer_cusip", "currency_value", "report_date"],
        result_count=result.get("fund_reports", 0),
        query_hash=qh,
        warnings=result.get("warnings", []),
        source_uri=NPORT_SOURCE_URI,
    )
    facts = []
    if result.get("found"):
        facts.append(_fact(evidence, subject=f"issuer:{identifier}", predicate="nport.reported_value_usd",
                           value=result["reported_value_usd"], unit="USD", document_id="nport_holdings.parquet",
                           locator=f"nport_holders:{qh}", field="reported_value_usd"))
        facts.append(_fact(evidence, subject=f"issuer:{identifier}", predicate="nport.fund_reports",
                           value=result["fund_reports"], document_id="nport_holdings.parquet",
                           locator=f"nport_holders:{qh}", field="fund_reports"))
        for holder in result.get("holders", []):
            facts.append(_fact(
                evidence, subject=holder["accession_number"], predicate="nport.holder_value_usd",
                value=holder["value_usd"], unit="USD", document_id=holder["accession_number"],
                locator=f"nport_holdings.parquet:accession={holder['accession_number']}",
                field="currency_value", as_of=holder.get("report_date"),
            ))
    return ToolResult(data=result, evidence=[evidence], facts=facts)


def search_filings(cfg: AppConfig, query: str, cik: str | None = None, forms: list[str] | None = None,
                   limit: int = 5, client=None) -> ToolResult:
    """Search SEC EDGAR full-text for a phrase and return cited filing passages."""
    from er.knowledge.sec_filings import search_filings as _search_filings

    qh = _query_hash("search_filings", query=query, cik=cik, forms=forms, limit=limit)
    result = _search_filings(cfg, query, cik=cik, forms=forms, limit=limit, client=client)
    evidence = Evidence(
        evidence_id=_evidence_id(),
        source="SEC EDGAR full-text search + filing text",
        source_timestamp=result.get("hits", [{}])[0].get("filing_date") if result.get("hits") else None,
        fact_type="records",
        criteria=[f'Query = "{query}"'] + ([f"CIK = {cik}"] if cik else []) + ([f"Forms = {forms}"] if forms else []),
        record_refs=[h["accession_number"] for h in result.get("hits", []) if h.get("accession_number")],
        fields_used=["form", "filing_date", "cik", "accession_number", "passage"],
        result_count=result.get("result_count", 0),
        query_hash=qh,
        warnings=result.get("warnings", []),
        source_uri=result.get("source_uri"),
    )
    facts = []
    for hit in result.get("hits", []):
        document_id = hit.get("accession_number") or hit.get("url") or qh
        locator = f"edgar:{document_id}:chars={hit.get('char_start')}-{hit.get('char_end')}"
        for field in ("form", "filing_date", "cik", "url"):
            if hit.get(field):
                facts.append(_fact(evidence, subject=document_id, predicate=f"filing.{field}", value=hit[field],
                                   document_id=document_id, locator=locator, field=field,
                                   as_of=hit.get("filing_date")))
    return ToolResult(data=result, evidence=[evidence], facts=facts)


def get_entity_profile_tool(store: Store, entity_id: str) -> ToolResult:
    """Get an entity's full profile: identity, GLEIF registration lineage,
    every attached identifier (LEI/CIK/ISIN/...) with its source, and latest
    SEC 13F filing activity if it is a resolved 13F filer."""
    qh = _query_hash("get_entity_profile", entity_id=entity_id)
    profile = get_entity_profile(store, entity_id)
    if profile is None:
        return ToolResult(
            data={"found": False},
            evidence=[
                Evidence(
                    evidence_id=_evidence_id(),
                    source="GLEIF entity record",
                    fact_type="lookup",
                    criteria=[f"Entity ID = {entity_id}"],
                    record_refs=[entity_id],
                    result_count=0,
                    query_hash=qh,
                    warnings=["No canonical entity found for this entity_id."],
                )
            ],
        )

    evidence = [
        Evidence(
            evidence_id=_evidence_id(),
            source="GLEIF entity record",
            source_timestamp=profile.lineage.gleif_snapshot_date if profile.lineage else None,
            fact_type="lookup",
            criteria=[f"Entity ID = {entity_id}"],
            record_refs=[entity_id],
            fields_used=["canonical_name", "entity_type", "jurisdiction", "legal_country", "entity_status"],
            result_count=1,
            query_hash=qh,
        )
    ]
    facts: list[Fact] = []
    identity_evidence = evidence[0]
    for field in ("canonical_name", "entity_type", "jurisdiction", "legal_country", "entity_status"):
        value = getattr(profile, field)
        if value is not None:
            facts.append(
                _fact(
                    identity_evidence,
                    subject=entity_id,
                    predicate=f"entity.{field}",
                    value=value,
                    document_id=entity_id,
                    locator=f"gleif_entities.parquet:lei={entity_id}",
                    field=field,
                    as_of=identity_evidence.source_timestamp,
                )
            )
    if profile.lineage:
        lineage_evidence = Evidence(
            evidence_id=_evidence_id(),
            source="GLEIF registration lineage",
            source_timestamp=profile.lineage.gleif_snapshot_date,
            fact_type="lookup",
            criteria=[f"Entity ID = {entity_id}"],
            record_refs=[entity_id],
            fields_used=[
                "entity_creation_date",
                "initial_registration_date",
                "last_update_date",
                "next_renewal_date",
                "registration_status",
            ],
            result_count=1,
            query_hash=qh,
        )
        evidence.append(lineage_evidence)
        for field in (
            "entity_creation_date",
            "initial_registration_date",
            "last_update_date",
            "next_renewal_date",
            "registration_status",
        ):
            value = getattr(profile.lineage, field)
            if value is not None:
                facts.append(
                    _fact(
                        lineage_evidence,
                        subject=entity_id,
                        predicate=f"entity.{field}",
                        value=value,
                        document_id=entity_id,
                        locator=f"gleif_entities.parquet:lei={entity_id}",
                        field=field,
                        as_of=profile.lineage.gleif_snapshot_date,
                    )
                )
    if profile.identifiers:
        identifier_evidence = Evidence(
            evidence_id=_evidence_id(),
            source="Attached source identifiers",
            fact_type="records",
            criteria=[f"Entity ID = {entity_id}"],
            record_refs=[entity_id],
            fields_used=["identifier_type", "identifier_value", "source", "snapshot_date"],
            result_count=len(profile.identifiers),
            query_hash=qh,
        )
        evidence.append(identifier_evidence)
        for identifier in profile.identifiers[:200]:
            facts.append(
                _fact(
                    identifier_evidence,
                    subject=entity_id,
                    predicate=f"identifier.{identifier.identifier_type.lower()}",
                    value=identifier.identifier_value,
                    document_id=entity_id,
                    locator=(
                        "entity_identifiers.parquet:"
                        f"entity_id={entity_id}:type={identifier.identifier_type}:"
                        f"value={identifier.identifier_value}"
                    ),
                    field="identifier_value",
                    as_of=identifier.snapshot_date,
                )
            )
    if profile.sec_13f:
        filing_evidence = Evidence(
            evidence_id=_evidence_id(),
            source="SEC 13F filing",
            source_timestamp=profile.sec_13f.latest_filing_date,
            fact_type="lookup",
            criteria=[f"CIK = {profile.sec_13f.cik}"],
            record_refs=[profile.sec_13f.cik],
            fields_used=[
                "latest_period_of_report",
                "latest_filing_date",
                "reported_security_count",
                "top_reported_holdings",
            ],
            result_count=profile.sec_13f.reported_security_count,
            query_hash=qh,
            warnings=[THIRTEEN_F_CAVEAT],
        )
        evidence.append(filing_evidence)
        for field in ("cik", "latest_period_of_report", "latest_filing_date", "reported_security_count"):
            value = getattr(profile.sec_13f, field)
            if value is not None:
                facts.append(
                    _fact(
                        filing_evidence,
                        subject=entity_id,
                        predicate=f"sec_13f.{field}",
                        value=value,
                        document_id=profile.sec_13f.cik,
                        locator=f"sec_13f_filings.parquet:cik={profile.sec_13f.cik}",
                        field=field,
                        as_of=profile.sec_13f.latest_period_of_report,
                    )
                )
        for index, holding in enumerate(profile.sec_13f.top_reported_holdings):
            locator = f"sec_13f_effective_holdings.parquet:cik={profile.sec_13f.cik}:rank={index + 1}"
            if holding.cusip:
                facts.append(
                    _fact(
                        filing_evidence,
                        subject=entity_id,
                        predicate="sec_13f.reported_holding_cusip",
                        value=holding.cusip,
                        document_id=profile.sec_13f.cik,
                        locator=locator,
                        field="cusip",
                        as_of=profile.sec_13f.latest_period_of_report,
                    )
                )
            if holding.value is None:
                continue
            facts.append(
                _fact(
                    filing_evidence,
                    subject=entity_id,
                    predicate="sec_13f.reported_holding_value",
                    value=holding.value,
                    unit=profile.sec_13f.value_unit,
                    document_id=profile.sec_13f.cik,
                    locator=locator,
                    field="value_usd" if profile.sec_13f.value_unit == "USD" else "value",
                    as_of=profile.sec_13f.latest_period_of_report,
                )
            )

    if profile.nport:
        _add_nport_facts(profile.nport, entity_id, qh, evidence, facts)

    return ToolResult(data={"found": True, "profile": profile.model_dump()}, evidence=evidence, facts=facts)


def _add_nport_facts(report: NPortFundReport, entity_id: str, qh: str, evidence: list, facts: list) -> None:
    report_evidence = Evidence(
        evidence_id=_evidence_id(),
        source="SEC Form N-PORT report",
        source_timestamp=report.filing_date,
        fact_type="lookup",
        criteria=[f"Series LEI = {report.series_lei}", "Latest report; an amendment replaces its original"],
        record_refs=[report.accession_number],
        fields_used=["report_date", "net_assets", "holding_count", "top_holdings"],
        result_count=report.holding_count,
        query_hash=qh,
        warnings=[NPORT_CAVEAT],
        source_uri=_edgar_filing_url(report.cik, report.accession_number) if report.cik else None,
    )
    evidence.append(report_evidence)
    locator = f"nport_funds.parquet:accession={report.accession_number}"
    for field, unit in (
        ("series_name", None),
        ("accession_number", None),
        ("report_date", None),
        ("filing_date", None),
        ("net_assets", "USD"),
        ("total_assets", "USD"),
        ("holding_count", None),
    ):
        value = getattr(report, field)
        if value is not None:
            facts.append(
                _fact(
                    report_evidence,
                    subject=entity_id,
                    predicate=f"nport.{field}",
                    value=value,
                    unit=unit,
                    document_id=report.accession_number,
                    locator=locator,
                    field=field,
                    as_of=report.report_date,
                )
            )
    for holding in report.top_holdings:
        holding_locator = f"nport_holdings.parquet:accession={report.accession_number}:holding={holding.holding_id}"
        for field, value, unit in (
            ("value_usd", holding.value_usd, "USD"),
            ("percentage", holding.percentage, "percent"),
            ("cusip", holding.cusip, None),
            ("isin", holding.isin, None),
        ):
            if value is not None:
                facts.append(
                    _fact(
                        report_evidence,
                        subject=entity_id,
                        predicate=f"nport.holding_{field}",
                        value=value,
                        unit=unit,
                        document_id=report.accession_number,
                        locator=holding_locator,
                        field=field,
                        as_of=report.report_date,
                    )
                )


def _count_nodes(node: HierarchyNode) -> int:
    return 1 + sum(_count_nodes(c) for c in node.upward) + sum(_count_nodes(c) for c in node.downward)


def get_relationship_hierarchy(
    store: Store, entity_id: str, depth: int = 2, direction: str = "all"
) -> ToolResult:
    """Get an entity's GLEIF relationship neighborhood: parents/managers
    upward, subsidiaries/funds downward, up to `depth` hops. direction must be
    one of "all", "parents", "children"."""
    qh = _query_hash("get_relationship_hierarchy", entity_id=entity_id, depth=depth, direction=direction)
    root = build_hierarchy_tree(store, entity_id, depth=depth, direction=direction)

    evidence = Evidence(
        evidence_id=_evidence_id(),
        source="GLEIF relationship/exception records",
        fact_type="records",
        criteria=[f"Entity ID = {entity_id}", f"Depth = {depth}", f"Direction = {direction}"],
        record_refs=[entity_id],
        fields_used=["relationship_type", "label", "status"],
        result_count=_count_nodes(root),
        query_hash=qh,
    )
    facts = [
        _fact(
            evidence,
            subject=entity_id,
            predicate="relationship.node_count",
            value=_count_nodes(root),
            document_id=entity_id,
            locator=f"gleif_relationships.parquet:lei={entity_id}:depth={depth}:direction={direction}",
            field="result_count",
        )
    ]
    return ToolResult(data={"tree": root.model_dump()}, evidence=[evidence], facts=facts)


_NUMBER_IN_TEXT = re.compile(r"(?<![\w])[-+]?\d[\d,]*(?:\.\d+)?%?(?![\w])")


def search_adv_documents(
    store: Store,
    query: str,
    crd_number: str | None = None,
    limit: int = 10,
) -> ToolResult:
    matches = search_pages(store, query, crd_number=crd_number, limit=min(max(limit, 1), 25))
    evidence: list[Evidence] = []
    facts: list[Fact] = []
    qh = _query_hash("search_adv_documents", query=query, crd_number=crd_number, limit=limit)

    for match in matches:
        reference = f"{match['pdf_file_name']}#page={match['page_number']}"
        item_evidence = Evidence(
            evidence_id=_evidence_id(),
            source="SEC Form ADV brochure",
            source_timestamp=match["snapshot_date"],
            fact_type="records",
            criteria=[f'PDF contains "{query}"'] + ([f"CRD = {crd_number}"] if crd_number else []),
            record_refs=[reference],
            fields_used=["page_text"],
            result_count=1,
            query_hash=qh,
            source_uri=f"/api/sources/sec-adv/{quote(match['pdf_file_name'], safe='')}#page={match['page_number']}",
            page=match["page_number"],
        )
        evidence.append(item_evidence)
        for field in ("crd_number", "brochure_id", "page_number"):
            facts.append(
                _fact(
                    item_evidence,
                    subject=f"crd:{match['crd_number']}",
                    predicate=f"document.{field}",
                    value=match[field],
                    document_id=match["pdf_file_name"],
                    locator=f"pdf:{match['content_hash']}:page={match['page_number']}",
                    field=field,
                    as_of=match["snapshot_date"],
                    uri=f"{match['pdf_file_name']}#page={match['page_number']}",
                    page=match["page_number"],
                )
            )
        for token in _NUMBER_IN_TEXT.finditer(match["snippet"]):
            char_start = match["snippet_start"] + token.start()
            char_end = match["snippet_start"] + token.end()
            facts.append(
                _fact(
                    item_evidence,
                    subject=f"crd:{match['crd_number']}",
                    predicate="document.numeric_value",
                    value=token.group(),
                    document_id=match["pdf_file_name"],
                    locator=(
                        f"pdf:{match['content_hash']}:page={match['page_number']}:"
                        f"chars={char_start}-{char_end}"
                    ),
                    field="page_text",
                    as_of=match["snapshot_date"],
                    uri=f"{match['pdf_file_name']}#page={match['page_number']}",
                    page=match["page_number"],
                    char_start=char_start,
                    char_end=char_end,
                )
            )
    return ToolResult(data={"matches": matches}, evidence=evidence, facts=facts)


def _edgar_filing_url(cik: str, accession_number: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number.replace('-', '')}/"


def _derive(
    evidence: Evidence,
    derivations: list[Derivation],
    formula_id: str,
    inputs: list[Fact],
    *,
    subject: str,
    predicate: str,
    as_of: str | None,
) -> Fact | None:
    formula = FORMULAS[formula_id]
    value = formula.compute(*(fact.value for fact in inputs))
    if value is None:
        return None
    fact = _fact(
        evidence,
        subject=subject,
        predicate=predicate,
        value=value,
        unit=formula.output_unit([fact.unit for fact in inputs]),
        document_id=formula_id,
        locator=f"{formula_id}({','.join(fact.fact_id for fact in inputs)})",
        field="value",
        as_of=as_of,
        provenance_class="DERIVED_FACT",
    )
    derivations.append(
        Derivation(
            fact_id=fact.fact_id,
            formula_id=formula_id,
            expression=formula.expression,
            inputs=[fact.fact_id for fact in inputs],
        )
    )
    return fact


def get_position_history(store: Store, cik: str, cusip: str, periods: int = 4) -> ToolResult:
    """A manager's reported long position in one CUSIP over its recent 13F
    report dates, with each period's total and the change between periods
    computed by registered formulas from the information-table rows."""
    cik = cik.strip().zfill(10)
    cusip = cusip.strip().upper()
    periods = min(max(periods, 2), 8)
    qh = _query_hash("get_position_history", cik=cik, cusip=cusip, periods=periods)
    rows = load_position_rows(store, cik, cusip, periods=periods)
    if not rows:
        return ToolResult(data={"found": False, "cik": cik, "cusip": cusip})

    warnings = [THIRTEEN_F_CAVEAT]
    suspect = sorted({row["accession_number"] for row in rows if row["scale_suspect"]})
    if suspect:
        warnings.append(
            f"Filing(s) {', '.join(suspect)} were filed in whole dollars but their implied prices sit near "
            "1/1000 of other filers' - the values may really be in thousands. They are shown as reported."
        )
    source_evidence = Evidence(
        evidence_id=_evidence_id(),
        source="SEC 13F information table",
        source_timestamp=rows[0]["snapshot_date"],
        fact_type="records",
        criteria=[f"CIK = {cik}", f"CUSIP = {cusip}", "Long positions only - put/call rows excluded"],
        record_refs=[f"{row['accession_number']}:{row['infotable_sk']}" for row in rows],
        fields_used=["value_usd", "period_of_report"],
        result_count=len(rows),
        query_hash=qh,
        warnings=warnings,
        source_uri=_edgar_filing_url(cik, rows[0]["accession_number"]),
    )
    facts: list[Fact] = []
    by_period: dict[str, list[Fact]] = {}
    for row in rows:
        fact = _fact(
            source_evidence,
            subject=f"cik:{cik}",
            predicate="holding.reported_value",
            value=row["value_usd"],
            unit="USD",
            document_id=row["accession_number"],
            locator=f"INFOTABLE.tsv:INFOTABLE_SK={row['infotable_sk']}:VALUE",
            field="value_usd",
            as_of=row["period_of_report"],
            uri=_edgar_filing_url(cik, row["accession_number"]),
        )
        facts.append(fact)
        by_period.setdefault(row["period_of_report"], []).append(fact)

    derivation_evidence = Evidence(
        evidence_id=_evidence_id(),
        source="Calculated from 13F information-table rows",
        fact_type="derivation",
        criteria=[],
        record_refs=[source_evidence.evidence_id],
        fields_used=["value_usd"],
        query_hash=qh,
        warnings=warnings,
    )
    derivations: list[Derivation] = []
    totals: list[tuple[str, Fact]] = []
    for period, period_facts in by_period.items():
        total = _derive(
            derivation_evidence, derivations, "sum", period_facts,
            subject=f"cik:{cik}", predicate=f"position.value:{cusip}", as_of=period,
        )
        totals.append((period, total))
        derivation_evidence.criteria.append(
            f"Position on {period} = sum of {len(period_facts)} information-table row(s)"
        )

    changes = []
    difference_facts: list[Fact | None] = []
    percent_facts: list[Fact | None] = []
    for (period, current), (previous_period, previous) in zip(totals, totals[1:]):
        difference = _derive(
            derivation_evidence, derivations, "difference", [current, previous],
            subject=f"cik:{cik}", predicate=f"position.change:{cusip}", as_of=period,
        )
        percent = _derive(
            derivation_evidence, derivations, "percent_change", [current, previous],
            subject=f"cik:{cik}", predicate=f"position.percent_change:{cusip}", as_of=period,
        )
        difference_facts.append(difference)
        percent_facts.append(percent)
        changes.append(
            {
                "from_period": previous_period,
                "to_period": period,
                "change_fact_id": difference.fact_id if difference else None,
                "percent_change_fact_id": percent.fact_id if percent else None,
            }
        )
    derivation_evidence.criteria += [
        f"Change = {FORMULAS['difference'].expression}",
        f"% change = {FORMULAS['percent_change'].expression}",
    ]
    derivation_evidence.result_count = len(derivations)
    facts += [total for _, total in totals] + [
        fact for fact in (difference_facts + percent_facts) if fact is not None
    ]
    return ToolResult(
        data={
            "found": True,
            "cik": cik,
            "cusip": cusip,
            "name_of_issuer": rows[0]["name_of_issuer"],
            "periods": [
                {"period_of_report": period, "position_value_fact_id": total.fact_id}
                for period, total in totals
            ],
            "changes": changes,
        },
        evidence=[source_evidence, derivation_evidence],
        facts=facts,
        derivations=derivations,
    )


CONNECTION_SOURCES = {
    "SIGNIFICANT_CONTROL": "Companies House PSC register",
    "BANK_CONTROL_PARENT": "FFIEC NIC bank relationship",
    "BENEFICIAL_OWNER": "SEC Schedule 13D/G",
    "INSIDER_OF": "SEC Forms 3/4/5",
    "SUCCEEDED_BY": "LEI succession",
}


def _capped_warning(group) -> list[str]:
    # Publish lists current connections before ended ones, so a capped list
    # that already reaches an ended one holds every current one.
    shown = len(group.connections)
    if group.total <= shown:
        return []
    if any(connection.valid_to for connection in group.connections):
        return [f"Shows {shown} of {group.total}: every current entry, then the most recent ended ones."]
    return [f"Shows {shown} of {group.total}, all current; more current entries are not listed."]


def get_entity_connections(store: Store, entity_id: str, edge_type: str | None = None) -> ToolResult:
    """Relationships from sources other than GLEIF's hierarchy, one group per
    kind of claim, plus the records in other sources linked to this LEI."""
    qh = _query_hash("get_entity_connections", entity_id=entity_id, edge_type=edge_type)
    connections = load_connections(store, entity_id)
    evidence: list[Evidence] = []
    facts: list[Fact] = []

    linked = []
    if connections.linked_records:
        linked_evidence = Evidence(
            evidence_id=_evidence_id(),
            source="Knowledge graph SAME_AS links",
            fact_type="records",
            criteria=[f"Records linked to LEI {entity_id}"],
            record_refs=[record.node_id for record in connections.linked_records],
            fields_used=["node_id", "source"],
            result_count=len(connections.linked_records),
            query_hash=qh,
        )
        evidence.append(linked_evidence)
        for record in connections.linked_records:
            kind, _, value = record.node_id.partition(":")
            fact = _fact(
                linked_evidence,
                subject=entity_id,
                predicate=f"linked_record.{kind}",
                value=value,
                document_id=entity_id,
                locator=f"knowledge_edges.parquet:SAME_AS:{record.node_id}->lei:{entity_id}",
                field="node_id",
            )
            facts.append(fact)
            linked.append({**record.model_dump(), "value_fact_id": fact.fact_id})

    groups = []
    for group in connections.groups:
        if edge_type and group.edge_type != edge_type:
            continue
        group_evidence = Evidence(
            evidence_id=_evidence_id(),
            source=CONNECTION_SOURCES.get(group.edge_type, group.edge_type),
            fact_type="records",
            criteria=[f"LEI = {entity_id}", f"Edge = {group.edge_type} ({group.direction})"],
            record_refs=[connection.other_node_id for connection in group.connections],
            fields_used=["other_name", "valid_from", "valid_to", "percent"],
            result_count=group.total,
            query_hash=qh,
            warnings=_capped_warning(group),
        )
        evidence.append(group_evidence)
        rows = []
        for connection in group.connections:
            ends = (connection.other_node_id, f"lei:{entity_id}")
            start, end = ends if connection.direction == "incoming" else ends[::-1]
            row = {
                "other_name": connection.other_name,
                "other_node_id": connection.other_node_id,
                "other_type": connection.other_type,
                "ended": connection.valid_to is not None,
            }
            for field, value, unit in (
                ("valid_from", connection.valid_from, None),
                ("valid_to", connection.valid_to, None),
                ("percent", connection.percent, "percent"),
            ):
                if value is None:
                    continue
                fact = _fact(
                    group_evidence,
                    subject=connection.other_node_id,
                    predicate=f"connection.{field}",
                    value=value,
                    unit=unit,
                    document_id=connection.source,
                    locator=f"knowledge_edges.parquet:{group.edge_type}:{start}->{end}",
                    field=field,
                    uri=connection.source_url,
                )
                facts.append(fact)
                row[f"{field}_fact_id"] = fact.fact_id
            rows.append(row)
        groups.append({"edge_type": group.edge_type, "direction": group.direction, "total": group.total, "connections": rows})

    return ToolResult(
        data={"entity_id": entity_id, "linked_records": linked, "groups": groups},
        evidence=evidence,
        facts=facts,
    )


def get_fund_structure(store: Store, identifier: str, id_type: str = "lei") -> ToolResult:
    """A fund registrant's series and share classes from SEC's investment
    company series/class register, found by registrant or series LEI, CIK,
    series ID, class ID or ticker."""
    if id_type not in FUND_ID_TYPES:
        raise ValueError(f"id_type must be one of {', '.join(FUND_ID_TYPES)}")
    qh = _query_hash("get_fund_structure", identifier=identifier, id_type=id_type)
    rows = load_fund_series(store, identifier, id_type)
    evidence: list[Evidence] = []
    facts: list[Fact] = []
    registrants: dict[str, list[dict]] = {}
    for row in rows:
        registrants.setdefault(row["cik"], []).append(row)

    out = []
    for cik, series_rows in registrants.items():
        first = series_rows[0]
        register_evidence = Evidence(
            evidence_id=_evidence_id(),
            source="SEC investment company series/class register",
            source_timestamp=first.get("snapshot_date"),
            fact_type="records",
            criteria=[f"{id_type} = {identifier}", f"Registrant CIK = {cik}"],
            record_refs=[row["series_id"] for row in series_rows],
            fields_used=["series_id", "series_name", "class_id", "class_name", "class_ticker"],
            result_count=len(series_rows),
            query_hash=qh,
        )
        evidence.append(register_evidence)

        def fact(predicate: str, value, locator: str, field: str) -> str:
            made = _fact(
                register_evidence,
                subject=f"cik:{cik}",
                predicate=predicate,
                value=value,
                document_id=first.get("source_file") or "sec_series_classes",
                locator=locator,
                field=field,
                as_of=first.get("snapshot_date"),
            )
            facts.append(made)
            return made.fact_id

        registrant_locator = f"sec_series_classes.parquet:cik={cik}"
        series_out = [
            {
                "series_id": row["series_id"],
                "series_name": row["series_name"],
                "series_lei": row.get("series_lei"),
                "class_count_fact_id": fact(
                    "fund.series_class_count", len(row["classes"]),
                    f"sec_series_classes.parquet:series_id={row['series_id']}", "class_id",
                ),
                "classes": row["classes"],
            }
            for row in series_rows
        ]
        out.append(
            {
                "registrant_name": first.get("registrant_name"),
                "registrant_lei": first.get("registrant_lei"),
                "cik_fact_id": fact("fund.registrant_cik", cik, registrant_locator, "cik"),
                "series_count_fact_id": fact("fund.series_count", len(series_rows), registrant_locator, "series_id"),
                "class_count_fact_id": fact(
                    "fund.class_count", sum(len(row["classes"]) for row in series_rows), registrant_locator, "class_id"
                ),
                "series": series_out,
            }
        )
    return ToolResult(
        data={"identifier": identifier, "id_type": id_type, "found": bool(rows), "registrants": out},
        evidence=evidence,
        facts=facts,
    )


def get_security(store: Store, identifier: str, id_type: str = "cusip") -> ToolResult:
    """What a 13F CUSIP is, according to OpenFIGI: name, ticker, security type
    and FIGIs, one entry per share class it maps to - or the CUSIPs a ticker
    or FIGI belongs to."""
    if id_type not in SECURITY_ID_TYPES:
        raise ValueError(f"id_type must be one of {', '.join(SECURITY_ID_TYPES)}")
    qh = _query_hash("get_security", identifier=identifier, id_type=id_type)
    docs = load_securities(store, identifier, id_type)
    evidence: list[Evidence] = []
    facts: list[Fact] = []
    matches = []
    for doc in docs:
        securities = doc.get("securities") or []
        warnings = {
            "ambiguous": [
                f"This CUSIP maps to {len(securities)} different share classes in OpenFIGI; "
                "none of them can be named as the CUSIP's security."
            ],
            "no_match": [f"OpenFIGI did not recognise this CUSIP ({doc.get('error') or 'no match'})."],
        }.get(doc["status"], [])
        security_evidence = Evidence(
            evidence_id=_evidence_id(),
            source="OpenFIGI mapping of a 13F CUSIP",
            source_timestamp=doc.get("snapshot_date"),
            fact_type="lookup",
            criteria=[f"{id_type} = {identifier}", f"CUSIP = {doc['cusip']}"],
            record_refs=[doc["cusip"]],
            fields_used=["figi", "share_class_figi", "composite_figi", "name", "ticker", "security_type"],
            result_count=len(securities),
            query_hash=qh,
            warnings=warnings,
            source_uri=(
                f"https://www.openfigi.com/id/{securities[0]['security_key']}" if doc["status"] == "resolved" else None
            ),
        )
        evidence.append(security_evidence)
        locator = f"openfigi_mappings.parquet:cusip={doc['cusip']}"
        cusip_fact = _fact(
            security_evidence, subject=f"cusip:{doc['cusip']}", predicate="security.cusip", value=doc["cusip"],
            document_id=doc.get("source_file") or "openfigi", locator=locator, field="cusip", as_of=doc.get("snapshot_date"),
        )
        facts.append(cusip_fact)
        entries = []
        for security in securities:
            listing_fact = _fact(
                security_evidence, subject=f"figi:{security['security_key']}", predicate="security.listing_count",
                value=security["listing_count"], document_id=doc.get("source_file") or "openfigi",
                locator=f"{locator}:security={security['security_key']}", field="figi", as_of=doc.get("snapshot_date"),
            )
            facts.append(listing_fact)
            entries.append({**security, "listing_count_fact_id": listing_fact.fact_id})
        matches.append({"cusip": doc["cusip"], "cusip_fact_id": cusip_fact.fact_id, "status": doc["status"], "securities": entries})
    return ToolResult(
        data={"identifier": identifier, "id_type": id_type, "found": bool(docs), "matches": matches},
        evidence=evidence,
        facts=facts,
    )


def get_beneficial_owners(store: Store, issuer_cik: str, limit: int = 25) -> ToolResult:
    """Persons reporting more than 5% of a class of an issuer's equity on
    Schedule 13D (active) or 13G (passive), newest filing per person."""
    issuer_cik = issuer_cik.strip().zfill(10)
    limit = min(max(limit, 1), 50)
    qh = _query_hash("get_beneficial_owners", issuer_cik=issuer_cik, limit=limit)
    rows = load_beneficial_owners(store, issuer_cik, limit=limit)
    evidence: list[Evidence] = []
    facts: list[Fact] = []
    owners = []
    for row in rows:
        person_tag = (
            "reportingPersonInfo" if row["form_type"].startswith("SCHEDULE 13D")
            else "coverPageHeaderReportingPersonDetails"
        )
        item_evidence = Evidence(
            evidence_id=_evidence_id(),
            source=f"SEC {row['form_type'].title()} filing",
            source_timestamp=row["filing_date"],
            fact_type="lookup",
            criteria=[f"Issuer CIK = {issuer_cik}", f"Accession = {row['accession_number']}"],
            record_refs=[f"{row['accession_number']}:{row['person_index']}"],
            fields_used=["percent_of_class", "aggregate_shares", "filing_intent"],
            result_count=1,
            query_hash=qh,
            source_uri=row["document_url"],
        )
        evidence.append(item_evidence)
        subject = f"cik:{row['reporting_person_cik']}" if row["reporting_person_cik"] else row["reporting_person_name"]
        person_path = f"{person_tag}[{row['person_index']}]"
        fact_ids = {}
        for predicate, value, unit, path in (
            ("ownership.percent_of_class", row["percent_of_class"], "percent",
             "percentOfClass" if person_tag == "reportingPersonInfo" else "classPercent"),
            ("ownership.aggregate_shares", row["aggregate_shares"], "shares",
             "aggregateAmountOwned" if person_tag == "reportingPersonInfo"
             else "reportingPersonBeneficiallyOwnedAggregateNumberOfShares"),
            ("ownership.event_date", row["event_date"], None, None),
        ):
            if value is None:
                continue
            fact = _fact(
                item_evidence,
                subject=subject,
                predicate=predicate,
                value=value,
                unit=unit,
                document_id=row["accession_number"],
                locator=f"primary_doc.xml:{person_path}/{path}" if path else "primary_doc.xml:coverPageHeader",
                field=predicate.removeprefix("ownership."),
                as_of=row["event_date"],
                uri=row["document_url"],
            )
            facts.append(fact)
            fact_ids[predicate.removeprefix("ownership.") + "_fact_id"] = fact.fact_id
        owners.append(
            {
                "reporting_person_name": row["reporting_person_name"],
                "reporting_person_cik": row["reporting_person_cik"],
                "reporting_person_type": row["reporting_person_type"],
                "form_type": row["form_type"],
                "filing_intent": row["filing_intent"],
                "security_class": row["security_class"],
                **fact_ids,
            }
        )
    return ToolResult(
        data={"issuer_cik": issuer_cik, "found": bool(rows), "owners": owners},
        evidence=evidence,
        facts=facts,
    )


def _xbrl_observation_fact(evidence: Evidence, series, row: dict) -> Fact:
    accession = row.get("accession_number") or ""
    return _fact(
        evidence,
        subject=f"cik:{series.cik}",
        predicate=f"xbrl.{series.tag}",
        value=row["value"],
        unit=normalise_unit(series.unit),
        document_id=accession or f"CIK{series.cik}",
        locator=(
            f"companyfacts/{series.tag}/{series.unit}/{row.get('period_end')}"
            f"/filed={row.get('filed')}"
        ),
        field=series.tag,
        as_of=row.get("period_end"),
        uri=_edgar_filing_url(series.cik, accession) if accession else None,
    )


def get_issuer_financials(
    store: Store,
    identifier: str,
    id_type: str = "cik",
    tag: str | None = None,
    as_of: str | None = None,
    periods: int = 4,
) -> ToolResult:
    """As-reported financial statement values an issuer tagged in its EDGAR
    filings (SEC XBRL company facts), resolved to the issuer by CIK, ticker or
    name. With no `tag`, returns the concepts available and each one's latest
    value. With a `tag` (e.g. "Assets", "Revenues", "NetIncomeLoss"), returns
    that concept's recent observations - each dated by period and by the filing
    that reported it - plus, where the inputs are present, a derived
    period-over-period change and the balance-sheet identity
    Assets = LiabilitiesAndStockholdersEquity. Pass `as_of` (YYYY-MM-DD) to see
    only what had been filed on or before that date."""
    want = (tag or "").strip().lower()
    periods = min(max(periods, 2), 8)
    qh = _query_hash("get_issuer_financials", identifier=identifier, id_type=id_type, tag=tag, as_of=as_of)
    try:
        issuer = resolve_issuer(store, identifier, id_type)
    except ValueError as exc:
        return ToolResult(data={"found": False, "identifier": identifier, "id_type": id_type, "reason": str(exc)})
    if issuer is None:
        return ToolResult(data={"identifier": identifier, "id_type": id_type, "found": False})
    cik = cik_of(issuer["cik"])
    series = load_series(store, cik)
    if not series:
        return ToolResult(
            data={"issuer": _issuer_summary(issuer), "found": False,
                  "reason": "No XBRL company facts are ingested for this issuer."}
        )

    selected = [item for item in series if want and (item.tag.lower() == want or item.tag.lower().endswith(want))]
    available = sorted(item.tag for item in series)
    if want and not selected:
        return ToolResult(data={"issuer": _issuer_summary(issuer), "found": False, "tag": tag,
                                "available_tags": available,
                                "reason": "No observations for that tag; see available_tags."})

    facts: list[Fact] = []
    evidence: list[Evidence] = []
    checks: list[dict] = []
    payload_series: list[dict] = []
    for item in selected or series:
        rows = known_on(item.observations, as_of)[-periods:]
        if not rows:
            continue
        item_evidence = Evidence(
            evidence_id=_evidence_id(),
            source="SEC XBRL company facts (EDGAR)",
            source_timestamp=max(str(row.get("filed") or "") for row in rows) or None,
            fact_type="records",
            criteria=[f"CIK = {cik}", f"Concept = {item.tag}",
                      f"As filed on or before {as_of}" if as_of else "Latest as filed"],
            record_refs=[str(row.get("accession_number") or "") for row in rows if row.get("accession_number")],
            fields_used=["value", "period_end", "filed"],
            result_count=len(rows),
            query_hash=qh,
            warnings=[XBRL_CAVEAT],
            source_uri=f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{item.tag}.json",
        )
        evidence.append(item_evidence)
        item_facts = [_xbrl_observation_fact(item_evidence, item, row) for row in rows]
        facts.extend(item_facts)
        latest_fact = item_facts[-1]
        payload_series.append(
            {
                "tag": item.tag,
                "unit": normalise_unit(item.unit),
                "latest_value": rows[-1]["value"],
                "latest_period_end": rows[-1].get("period_end"),
                "latest_filed": rows[-1].get("filed"),
                "latest_fact_id": latest_fact.fact_id,
                "observations": [
                    {"value": row["value"], "period_end": row.get("period_end"),
                     "period_start": row.get("period_start"), "filed": row.get("filed"),
                     "form": row.get("form"), "accession_number": row.get("accession_number")}
                    for row in rows
                ],
            }
        )

    derivation_evidence = Evidence(
        evidence_id=_evidence_id(),
        source="Calculated from SEC XBRL company facts",
        fact_type="derivation",
        criteria=[],
        record_refs=[item.evidence_id for item in evidence],
        fields_used=["value"],
        query_hash=qh,
        warnings=[XBRL_CAVEAT],
    )
    derivations: list[Derivation] = []
    payload_derived: list[dict] = []

    for entry in payload_series:
        item = next(item for item in series if item.tag == entry["tag"])
        rows = known_on(item.observations, as_of)[-periods:]
        item_facts = [fact for fact in facts if fact.predicate == f"xbrl.{item.tag}"]
        if len(item_facts) >= 2:
            current, previous = item_facts[-1], item_facts[-2]
            change = _derive(
                derivation_evidence, derivations, "percent_change", [current, previous],
                subject=f"cik:{cik}", predicate=f"xbrl.{item.tag}.percent_change",
                as_of=rows[-1].get("period_end"),
            )
            if change is not None:
                facts.append(change)
                payload_derived.append({"predicate": change.predicate, "value": change.value,
                                        "unit": change.unit, "fact_id": change.fact_id,
                                        "inputs": derivations[-1].inputs})

    for a_tag, b_tag, formula_id, predicate in (
        ("AssetsCurrent", "LiabilitiesCurrent", "ratio", "xbrl.current_ratio"),
    ):
        numerator = _latest_fact(facts, f"xbrl.{a_tag}")
        denominator = _latest_fact(facts, f"xbrl.{b_tag}")
        if numerator and denominator:
            ratio = _derive(
                derivation_evidence, derivations, formula_id, [numerator, denominator],
                subject=f"cik:{cik}", predicate=predicate, as_of=numerator.as_of,
            )
            if ratio is not None:
                facts.append(ratio)
                payload_derived.append({"predicate": ratio.predicate, "value": ratio.value,
                                        "unit": ratio.unit, "fact_id": ratio.fact_id,
                                        "inputs": derivations[-1].inputs})

    identity = balance_check(series, as_of)
    if identity is not None:
        checks.append(identity)
        assets = _latest_fact(facts, "xbrl.Assets")
        total = _latest_fact(facts, "xbrl.LiabilitiesAndStockholdersEquity")
        if assets and total:
            residual = _derive(
                derivation_evidence, derivations, "difference", [assets, total],
                subject=f"cik:{cik}", predicate="xbrl.balance_residual", as_of=assets.as_of,
            )
            if residual is not None:
                facts.append(residual)
                payload_derived.append({"predicate": residual.predicate, "value": residual.value,
                                        "unit": residual.unit, "fact_id": residual.fact_id,
                                        "inputs": derivations[-1].inputs})
        if not identity["passed"]:
            for item in evidence:
                item.warnings.append(
                    f"Balance-sheet identity does not hold for {identity['period_end']}: "
                    f"Assets - LiabilitiesAndStockholdersEquity = {identity['residual']:,.0f}."
                )
        else:
            for item in evidence:
                item.warnings.append(
                    f"Balance-sheet identity holds for {identity['period_end']} "
                    "(Assets = LiabilitiesAndStockholdersEquity)."
                )

    return ToolResult(
        data={
            "issuer": _issuer_summary(issuer),
            "found": True,
            "as_of": as_of,
            "tag": tag,
            "series": payload_series,
            "derived": payload_derived,
            "checks": checks,
            "available_tags": available,
        },
        evidence=evidence + [derivation_evidence] if payload_derived else evidence,
        facts=facts,
        derivations=derivations,
    )


def _issuer_summary(issuer: dict) -> dict:
    return {
        "cik": cik_of(issuer["cik"]),
        "entity_name": issuer.get("entity_name"),
        "tickers": issuer.get("tickers") or [],
        "former_names": issuer.get("former_names") or [],
        "sic": issuer.get("sic"),
    }


def _latest_fact(facts: list[Fact], predicate: str) -> Fact | None:
    matches = [fact for fact in facts if fact.predicate == predicate]
    return matches[-1] if matches else None


ADV_CAVEAT = (
    "Regulatory AUM (Form ADV Item 5.F) is gross: it counts leverage, uncalled commitments and "
    "non-fee-paying assets, so it is usually larger than the AUM a manager reports to clients."
)
FORM_D_CAVEAT = (
    "Form D is a notice of an exempt offering. Amounts sold are cumulative and self-reported, an "
    "amendment (D/A) restates the running total, and a filing is not evidence the offering closed."
)
SHORT_VOLUME_CAVEAT = (
    "FINRA daily short sale volume counts trades marked short on FINRA-reported venues that day. It is "
    "not short interest (the open short position), and market-maker hedging puts much of normal "
    "volume in it."
)
FTD_CAVEAT = (
    "SEC fails-to-deliver figures are outstanding CNS fail balances on each settlement date, not new "
    "fails, so consecutive days must not be added together."
)
ADV_FIELDS = (
    ("raum", "5F(2)(c)", "USD"),
    ("raum_discretionary", "5F(2)(a)", "USD"),
    ("raum_non_us", "5F(3)", "USD"),
    ("accounts", "5F(2)(f)", None),
    ("employees", "5A", None),
    ("advisory_employees", "5B(1)", None),
    ("private_fund_count", "Count of Private Funds - 7B(1)", None),
    ("private_fund_gross_assets", "Total Gross Assets of Private Funds", "USD"),
    ("lei", "1P", None),
    ("cik", "CIK#", None),
    ("sec_number", "SEC#", None),
    ("latest_filing_date", "Latest ADV Filing Date", None),
)


def get_adviser_profile(store: Store, identifier: str, id_type: str = "crd") -> ToolResult:
    """An investment adviser's Form ADV Part 1A answers: regulatory AUM,
    accounts, employees, private funds, client types (Item 5.D), and its
    regulatory AUM in every monthly snapshot ingested, with the change since
    the earliest one computed by registered formulas."""
    qh = _query_hash("get_adviser_profile", identifier=identifier, id_type=id_type)
    try:
        firm = resolve_adviser(store, identifier, id_type)
    except ValueError as exc:
        return ToolResult(data={"found": False, "identifier": identifier, "reason": str(exc)})
    if firm is None:
        return ToolResult(data={"found": False, "identifier": identifier, "id_type": id_type})
    crd, snapshot = firm["crd_number"], firm["snapshot_date"]
    uri = f"https://adviserinfo.sec.gov/firm/summary/{crd}"
    evidence = Evidence(
        evidence_id=_evidence_id(),
        source="SEC Form ADV Part 1A (monthly adviser data)",
        source_timestamp=snapshot,
        fact_type="lookup",
        criteria=[f"{id_type} = {identifier}", f"CRD = {crd}", f"Snapshot = {snapshot}"],
        record_refs=[crd],
        fields_used=[column for _, column, _ in ADV_FIELDS],
        result_count=1,
        query_hash=qh,
        warnings=[ADV_CAVEAT],
        source_uri=uri,
    )
    facts: list[Fact] = []

    def fact(ev: Evidence, predicate: str, value, column: str, unit: str | None, as_of: str, source_file: str,
             subject: str = f"crd:{crd}") -> Fact:
        made = _fact(ev, subject=subject, predicate=predicate, value=value, unit=unit, document_id=source_file,
                     locator=f"{source_file}:Organization CRD#={crd}:{column}", field=column, as_of=as_of, uri=uri)
        facts.append(made)
        return made

    figures = {}
    for name, column, unit in ADV_FIELDS:
        if firm.get(name) is not None:
            figures[f"{name}_fact_id"] = fact(evidence, f"adv.{name}", firm[name], column, unit, snapshot,
                                              firm["source_file"]).fact_id

    all_evidence = [evidence]
    clients = []
    if firm.get("client_types"):
        client_evidence = Evidence(
            evidence_id=_evidence_id(), source="SEC Form ADV Item 5.D (clients by type)", source_timestamp=snapshot,
            fact_type="records", criteria=[f"CRD = {crd}", f"Snapshot = {snapshot}"], record_refs=[crd],
            fields_used=["5D(x)(1)", "5D(x)(2)", "5D(x)(3)"], result_count=len(firm["client_types"]), query_hash=qh,
            warnings=["A client type marked 'fewer than five' reports no client count."], source_uri=uri,
        )
        all_evidence.append(client_evidence)
        for client in firm["client_types"]:
            subject = f"crd:{crd}:client_type={client['client_type']}"
            row = {"client_type": client["client_type"], "fewer_than_five": client["fewer_than_five"],
                   "raum": client.get("raum"), "client_count": client.get("client_count")}
            if client.get("raum") is not None:
                row["raum_fact_id"] = fact(client_evidence, "adv.client_type_raum", client["raum"], "5D(x)(3)",
                                           "USD", snapshot, firm["source_file"], subject).fact_id
            if client.get("client_count") is not None:
                row["client_count_fact_id"] = fact(client_evidence, "adv.client_type_count", client["client_count"],
                                                   "5D(x)(1)", None, snapshot, firm["source_file"], subject).fact_id
            clients.append(row)

    history = [entry for entry in firm.get("history", []) if entry.get("raum") is not None]
    history_out, changes, derivations = [], [], []
    if history:
        history_evidence = Evidence(
            evidence_id=_evidence_id(), source="SEC Form ADV Part 1A snapshots (regulatory AUM history)",
            source_timestamp=snapshot, fact_type="records", criteria=[f"CRD = {crd}", "Item 5.F(2)(c) per snapshot"],
            record_refs=[entry["source_file"] for entry in history], fields_used=["5F(2)(c)"],
            result_count=len(history), query_hash=qh,
            warnings=[ADV_CAVEAT, "An adviser updates Item 5.F once a year, so consecutive monthly snapshots often repeat."],
            source_uri=uri,
        )
        all_evidence.append(history_evidence)
        points = [fact(history_evidence, "adv.raum", entry["raum"], "5F(2)(c)", "USD", entry["snapshot_date"],
                       entry["source_file"]) for entry in history]
        history_out = [{"snapshot_date": entry["snapshot_date"], "raum": entry["raum"], "raum_fact_id": point.fact_id}
                       for entry, point in zip(history, points)]
        if len(points) >= 2:
            derivation_evidence = Evidence(
                evidence_id=_evidence_id(), source="Calculated from Form ADV snapshots", fact_type="derivation",
                criteria=[f"Change = {FORMULAS['difference'].expression}",
                          f"% change = {FORMULAS['percent_change'].expression}",
                          f"From {history[0]['snapshot_date']} to {history[-1]['snapshot_date']}"],
                record_refs=[history_evidence.evidence_id], fields_used=["5F(2)(c)"], query_hash=qh,
            )
            difference = _derive(derivation_evidence, derivations, "difference", [points[-1], points[0]],
                                 subject=f"crd:{crd}", predicate="adv.raum.change", as_of=history[-1]["snapshot_date"])
            percent = _derive(derivation_evidence, derivations, "percent_change", [points[-1], points[0]],
                              subject=f"crd:{crd}", predicate="adv.raum.percent_change",
                              as_of=history[-1]["snapshot_date"])
            facts += [item for item in (difference, percent) if item is not None]
            derivation_evidence.result_count = len(derivations)
            all_evidence.append(derivation_evidence)
            changes.append({"from_snapshot": history[0]["snapshot_date"], "to_snapshot": history[-1]["snapshot_date"],
                            "change_fact_id": difference.fact_id if difference else None,
                            "percent_change_fact_id": percent.fact_id if percent else None})

    return ToolResult(
        data={
            "found": True,
            "crd_number": crd,
            "business_name": firm["business_name"],
            "legal_name": firm.get("legal_name"),
            "firm_type": firm.get("firm_type"),
            "city": firm.get("city"),
            "state": firm.get("state"),
            "website": firm.get("website"),
            "snapshot_date": snapshot,
            "lei_name": firm.get("lei_name"),
            "thirteen_f_cik": firm.get("thirteen_f_cik"),
            "fund_types": firm.get("fund_types") or [],
            **{name: firm.get(name) for name, _, _ in ADV_FIELDS},
            **figures,
            "client_types": clients,
            "raum_history": history_out,
            "raum_changes": changes,
        },
        evidence=all_evidence,
        facts=facts,
        derivations=derivations,
    )


def search_private_offerings(
    store: Store,
    query: str | None = None,
    kind: str | None = None,
    fund_type: str | None = None,
    industry: str | None = None,
    state: str | None = None,
    days: int | None = None,
    new_only: bool = False,
    sort: str = "newest",
    limit: int = 20,
) -> ToolResult:
    """Form D private offering notices, newest first or largest first, with amounts sold and
    offered as facts, and the total sold across the listed original filings
    computed by the registered sum formula."""
    limit = min(max(limit, 1), 50)
    qh = _query_hash("search_private_offerings", query=query, kind=kind, fund_type=fund_type, industry=industry,
                     state=state, days=days, new_only=new_only, sort=sort, limit=limit)
    rows, window = search_offerings(store, query, kind=kind, fund_type=fund_type, industry=industry, state=state,
                                    days=days, new_only=new_only, sort=sort, limit=limit + 1)
    more = len(rows) > limit
    rows = rows[:limit]
    criteria = [f"{name} = {value}" for name, value in (
        ("Issuer or related person contains", query), ("Kind", kind), ("Fund type", fund_type),
        ("Industry group", industry), ("State", state)) if value]
    if window:
        criteria.append(f"Filed {window['from']} to {window['to']} (the newest filing in the data set is {window['to']})")
    if new_only:
        criteria.append("Original filings only (amendments excluded)")
    criteria.append("Largest amount sold first" if sort == "largest" else "Newest filing first")
    evidence = Evidence(
        evidence_id=_evidence_id(), source="SEC Form D data sets", source_timestamp=window.get("to"),
        fact_type="records", criteria=criteria, record_refs=[row["accession_number"] for row in rows],
        fields_used=["TOTALAMOUNTSOLD", "TOTALOFFERINGAMOUNT", "MINIMUMINVESTMENTACCEPTED", "FILING_DATE"],
        result_count=len(rows), query_hash=qh,
        warnings=[FORM_D_CAVEAT] + ([f"Shows the {'largest' if sort == 'largest' else 'newest'} {limit}; "
                                     "more filings match."] if more else []),
    )
    facts: list[Fact] = []
    offerings = []
    sold_facts: list[Fact] = []
    for row in rows:
        accession = row["accession_number"]
        uri = _edgar_filing_url(row["issuer_cik"], accession)
        item = {key: row.get(key) for key in ("accession_number", "issuer_name", "issuer_cik", "filing_date",
                                              "submission_type", "is_amendment", "industry_group", "fund_type",
                                              "state", "offering_indefinite")}
        for predicate, field, column, unit in (
            ("form_d.total_sold", "total_sold", "TOTALAMOUNTSOLD", "USD"),
            ("form_d.total_offering", "total_offering", "TOTALOFFERINGAMOUNT", "USD"),
            ("form_d.minimum_investment", "minimum_investment", "MINIMUMINVESTMENTACCEPTED", "USD"),
            ("form_d.investor_count", "investor_count", "TOTALNUMBERALREADYINVESTED", None),
            ("form_d.filing_date", "filing_date", "FILING_DATE", None),
        ):
            if row.get(field) is None:
                continue
            made = _fact(evidence, subject=f"cik:{row['issuer_cik']}", predicate=predicate, value=row[field],
                         unit=unit, document_id=accession, locator=f"OFFERING.tsv:ACCESSIONNUMBER={accession}:{column}",
                         field=column, as_of=row.get("filing_date"), uri=uri)
            facts.append(made)
            item[field] = row[field]
            item[f"{field}_fact_id"] = made.fact_id
            if field == "total_sold" and not row.get("is_amendment"):
                sold_facts.append(made)
        offerings.append(item)

    derivations: list[Derivation] = []
    all_evidence = [evidence]
    total = None
    if len(sold_facts) >= 2:
        derivation_evidence = Evidence(
            evidence_id=_evidence_id(), source="Calculated from Form D amounts sold", fact_type="derivation",
            criteria=[f"Total = sum of TOTALAMOUNTSOLD over the {len(sold_facts)} listed original filings "
                      "(amendments left out so an offering is not counted twice)"],
            record_refs=[evidence.evidence_id], fields_used=["TOTALAMOUNTSOLD"], query_hash=qh,
            warnings=[FORM_D_CAVEAT] + (["Only the listed filings are summed, not every match."] if more else []),
        )
        total = _derive(derivation_evidence, derivations, "sum", sold_facts, subject="form_d:search",
                        predicate="form_d.total_sold_sum", as_of=window.get("to") or rows[0].get("filing_date"))
        if total is not None:
            facts.append(total)
            derivation_evidence.result_count = 1
            all_evidence.append(derivation_evidence)
    return ToolResult(
        data={"found": bool(rows), "window": window, "more": more, "offerings": offerings,
              "total_sold_fact_id": total.fact_id if total else None},
        evidence=all_evidence,
        facts=facts,
        derivations=derivations,
    )


def get_security_ownership(store: Store, identifier: str, limit: int = 15) -> ToolResult:
    """Who reports holding a security on 13F: per report period, the number of
    filers and their total reported value and shares; and the largest holders
    in the latest period with their share change since the previous one,
    computed by registered formulas. Long positions only."""
    limit = min(max(limit, 1), 50)
    qh = _query_hash("get_security_ownership", identifier=identifier, limit=limit)
    resolved = resolve_security(store, identifier)
    doc = load_ownership(store, resolved["cusip"], limit=limit) if resolved and resolved["cusip"] else None
    if doc is None:
        return ToolResult(data={"found": False, "identifier": identifier})
    cusip = doc["cusip"]
    locator = f"sec_13f_effective_holdings.parquet:cusip={cusip}:put_call=NULL"
    period_evidence = Evidence(
        evidence_id=_evidence_id(), source="SEC 13F information tables, by CUSIP", source_timestamp=doc["latest_period"],
        fact_type="records",
        criteria=[f"CUSIP = {cusip}", "Long positions only - put/call rows excluded",
                  "Per period: count of filers, sum of their reported value and shares"],
        record_refs=[period["period_of_report"] for period in doc["periods"]],
        fields_used=["value_usd", "shares_or_principal_amount"], result_count=doc["holder_count"], query_hash=qh,
        warnings=[THIRTEEN_F_CAVEAT],
    )
    facts: list[Fact] = []

    def fact(ev: Evidence, subject: str, predicate: str, value, unit: str | None, as_of: str, where: str,
             field: str, document_id: str) -> Fact:
        made = _fact(ev, subject=subject, predicate=predicate, value=value, unit=unit, document_id=document_id,
                     locator=f"{locator}:{where}", field=field, as_of=as_of)
        facts.append(made)
        return made

    periods = []
    totals = []
    for period in doc["periods"]:
        name = period["period_of_report"]
        count = fact(period_evidence, f"cusip:{cusip}", "ownership.holder_count", period["holder_count"], None, name,
                     f"period={name}:count(cik)", "cik", cusip)
        value = fact(period_evidence, f"cusip:{cusip}", "ownership.reported_value_total", period["value_usd"], "USD",
                     name, f"period={name}:sum(value_usd)", "value_usd", cusip)
        row = {"period_of_report": name, "holder_count": period["holder_count"], "value_usd": period["value_usd"],
               "shares": period.get("shares"), "holder_count_fact_id": count.fact_id, "value_fact_id": value.fact_id}
        if period.get("shares") is not None:
            row["shares_fact_id"] = fact(period_evidence, f"cusip:{cusip}", "ownership.shares_total", period["shares"],
                                         "shares", name, f"period={name}:sum(shares)", "shares_or_principal_amount",
                                         cusip).fact_id
        totals.append(value)
        periods.append(row)

    holder_evidence = Evidence(
        evidence_id=_evidence_id(), source="SEC 13F information tables (largest holders)",
        source_timestamp=doc["latest_period"], fact_type="records",
        criteria=[f"CUSIP = {cusip}", f"Period = {doc['latest_period']}", f"Largest {limit} by reported value",
                  f"Previous period = {doc.get('previous_period')}"],
        record_refs=[holder["accession_number"] for holder in doc["holders"]], fields_used=["value_usd", "shares"],
        result_count=doc["holder_count"], query_hash=qh, warnings=[THIRTEEN_F_CAVEAT],
    )
    derivation_evidence = Evidence(
        evidence_id=_evidence_id(), source="Calculated from 13F information-table rows", fact_type="derivation",
        criteria=[f"Change = {FORMULAS['difference'].expression}",
                  f"% change = {FORMULAS['percent_change'].expression}"],
        record_refs=[period_evidence.evidence_id, holder_evidence.evidence_id], fields_used=["value_usd", "shares"],
        query_hash=qh, warnings=[THIRTEEN_F_CAVEAT],
    )
    derivations: list[Derivation] = []
    total_change = None
    if len(totals) >= 2:
        total_change = _derive(derivation_evidence, derivations, "percent_change", [totals[-1], totals[-2]],
                               subject=f"cusip:{cusip}", predicate="ownership.reported_value_total.percent_change",
                               as_of=doc["latest_period"])
        if total_change is not None:
            facts.append(total_change)

    holders = []
    for holder in doc["holders"]:
        subject = f"cik:{holder['cik']}"
        where = f"cik={holder['cik']}"
        row = {"filer_name": holder.get("filer_name"), "cik": holder["cik"], "lei": holder.get("lei"),
               "new_position": holder.get("new", False), "value_usd": holder.get("value_usd"),
               "shares": holder.get("shares"), "previous_shares": holder.get("previous_shares"),
               "shares_change": holder.get("change"), "shares_percent_change": holder.get("percent_change")}
        if holder.get("value_usd") is not None:
            row["value_fact_id"] = fact(holder_evidence, subject, "holding.reported_value", holder["value_usd"], "USD",
                                        doc["latest_period"], f"{where}:period={doc['latest_period']}", "value_usd",
                                        holder["accession_number"]).fact_id
        current = previous = None
        if holder.get("shares") is not None:
            current = fact(holder_evidence, subject, "holding.shares", holder["shares"], "shares", doc["latest_period"],
                           f"{where}:period={doc['latest_period']}", "shares_or_principal_amount",
                           holder["accession_number"])
            row["shares_fact_id"] = current.fact_id
        if holder.get("previous_shares") is not None and doc.get("previous_period"):
            previous = fact(holder_evidence, subject, "holding.shares", holder["previous_shares"], "shares",
                            doc["previous_period"], f"{where}:period={doc['previous_period']}",
                            "shares_or_principal_amount", holder["previous_accession_number"])
            row["previous_shares_fact_id"] = previous.fact_id
        if current and previous:
            change = _derive(derivation_evidence, derivations, "difference", [current, previous], subject=subject,
                             predicate=f"holding.shares.change:{cusip}", as_of=doc["latest_period"])
            percent = _derive(derivation_evidence, derivations, "percent_change", [current, previous], subject=subject,
                              predicate=f"holding.shares.percent_change:{cusip}", as_of=doc["latest_period"])
            facts += [item for item in (change, percent) if item is not None]
            row["shares_change_fact_id"] = change.fact_id if change else None
            row["shares_percent_change_fact_id"] = percent.fact_id if percent else None
        holders.append(row)
    derivation_evidence.result_count = len(derivations)
    return ToolResult(
        data={
            "found": True,
            "cusip": cusip,
            "issuer_name": doc.get("issuer_name"),
            "title_of_class": doc.get("title_of_class"),
            "tickers": doc.get("tickers") or [],
            "latest_period": doc["latest_period"],
            "previous_period": doc.get("previous_period"),
            "periods": periods,
            "reported_value_percent_change_fact_id": total_change.fact_id if total_change else None,
            "holders": holders,
        },
        evidence=[period_evidence, holder_evidence] + ([derivation_evidence] if derivations else []),
        facts=facts,
        derivations=derivations,
    )


def get_short_activity(store: Store, identifier: str, days: int = 20) -> ToolResult:
    """A security's FINRA daily short sale volume and the short share of each
    day's volume (registered percent_of formula), plus its SEC fails-to-deliver
    balances. Found by ticker or CUSIP."""
    days = min(max(days, 5), 60)
    qh = _query_hash("get_short_activity", identifier=identifier, days=days)
    resolved = resolve_security(store, identifier)
    if resolved is None:
        return ToolResult(data={"found": False, "identifier": identifier})
    symbol, cusip = resolved["symbol"], resolved["cusip"]
    evidence: list[Evidence] = []
    facts: list[Fact] = []
    derivations: list[Derivation] = []
    volume_rows = load_short_volume(store, symbol, days=days) if symbol else []
    daily = []
    if volume_rows:
        volume_evidence = Evidence(
            evidence_id=_evidence_id(), source="FINRA Reg SHO daily short sale volume",
            source_timestamp=volume_rows[-1]["trade_date"], fact_type="records",
            criteria=[f"Symbol = {symbol}", f"Last {len(volume_rows)} trading days in the data"],
            record_refs=[row["source_file"] for row in volume_rows], fields_used=["ShortVolume", "TotalVolume"],
            result_count=len(volume_rows), query_hash=qh, warnings=[SHORT_VOLUME_CAVEAT],
            source_uri="https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/daily-short-sale-volume-files",
        )
        ratio_evidence = Evidence(
            evidence_id=_evidence_id(), source="Calculated from FINRA short sale volume", fact_type="derivation",
            criteria=[f"Short share of volume = {FORMULAS['percent_of'].expression}"],
            record_refs=[volume_evidence.evidence_id], fields_used=["ShortVolume", "TotalVolume"], query_hash=qh,
            warnings=[SHORT_VOLUME_CAVEAT],
        )
        evidence += [volume_evidence, ratio_evidence]
        for row in volume_rows:
            made = {}
            for field, column in (("short_volume", "ShortVolume"), ("total_volume", "TotalVolume")):
                made[field] = _fact(volume_evidence, subject=f"symbol:{symbol}", predicate=f"short_volume.{field}",
                                    value=row[field], unit="shares", document_id=row["source_file"],
                                    locator=f"{row['source_file']}:Symbol={symbol}:{column}", field=column,
                                    as_of=row["trade_date"])
                facts.append(made[field])
            ratio = _derive(ratio_evidence, derivations, "percent_of", [made["short_volume"], made["total_volume"]],
                            subject=f"symbol:{symbol}", predicate="short_volume.share_of_volume", as_of=row["trade_date"])
            if ratio is not None:
                facts.append(ratio)
            daily.append({"trade_date": row["trade_date"], "short_volume": row["short_volume"],
                          "total_volume": row["total_volume"], "short_share_percent": row.get("short_ratio"),
                          "short_volume_fact_id": made["short_volume"].fact_id,
                          "total_volume_fact_id": made["total_volume"].fact_id,
                          "short_share_fact_id": ratio.fact_id if ratio else None})
        ratio_evidence.result_count = len(derivations)
    fails = load_fails(store, cusip, limit=days) if cusip else None
    fails_out = []
    if fails and fails.get("fails"):
        fails_evidence = Evidence(
            evidence_id=_evidence_id(), source="SEC fails-to-deliver data", source_timestamp=fails["fails"][-1]["settlement_date"],
            fact_type="records", criteria=[f"CUSIP = {cusip}", f"Last {len(fails['fails'])} settlement dates with a fail"],
            record_refs=sorted({row["source_file"] for row in fails["fails"]}), fields_used=["QUANTITY (FAILS)", "PRICE"],
            result_count=len(fails["fails"]), query_hash=qh, warnings=[FTD_CAVEAT],
            source_uri="https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data",
        )
        evidence.append(fails_evidence)
        for row in fails["fails"]:
            locator = f"{row['source_file']}:CUSIP={cusip}:SETTLEMENT DATE={row['settlement_date']}"
            quantity = _fact(fails_evidence, subject=f"cusip:{cusip}", predicate="fails.quantity", value=row["quantity"],
                             unit="shares", document_id=row["source_file"], locator=f"{locator}:QUANTITY (FAILS)",
                             field="QUANTITY (FAILS)", as_of=row["settlement_date"])
            facts.append(quantity)
            fails_out.append({"settlement_date": row["settlement_date"], "quantity": row["quantity"],
                              "quantity_fact_id": quantity.fact_id})
    return ToolResult(
        data={"found": bool(daily or fails_out), "symbol": symbol, "cusip": cusip,
              "description": (fails or {}).get("description"), "short_volume": daily, "fails": fails_out},
        evidence=evidence,
        facts=facts,
        derivations=derivations,
    )
