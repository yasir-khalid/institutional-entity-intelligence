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
from er.entity.connections import load_connections
from er.entity.funds import FUND_ID_TYPES, load_fund_series
from er.entity.models import NPortFundReport
from er.entity.ownership import load_beneficial_owners
from er.entity.positions import load_position_rows
from er.entity.profile import get_entity_profile
from er.entity.securities import SECURITY_ID_TYPES, load_securities
from er.entity.search import match_result_to_matches, search_by_cusip, search_by_lei, search_by_name
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
    return ToolResult(data={"matches": [m.model_dump() for m in matches]}, evidence=[evidence], facts=facts)


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
        unit=formula.unit or inputs[0].unit,
        document_id=formula_id,
        locator=f"{formula_id}({','.join(fact.fact_id for fact in inputs)})",
        field="value",
        as_of=as_of,
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
