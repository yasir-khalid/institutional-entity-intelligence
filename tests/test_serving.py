import json

import pyarrow as pa
import pyarrow.parquet as pq

from er.config import load_config
from er.entity.resolution import load_match_decisions, record_review
from er.agent.tools import get_fund_structure, get_security
from er.serving.publish import (
    adv_document_documents,
    adv_page_documents,
    entity_documents,
    fund_series_documents,
    nport_fund_documents,
    security_documents,
)
from er.serving.store import ENTITIES, FUND_SERIES, SECURITIES, MemoryStore, OpenSearchStore


def _write(path, rows):
    pq.write_table(pa.Table.from_pylist(rows), path)


def _config(tmp_path):
    cfg = load_config().model_copy(deep=True)
    for section in (cfg.gleif, cfg.sec_13f, cfg.entity):
        section.processed_dir = tmp_path
    return cfg


def test_entity_document_carries_capped_identifiers_and_connections_through_linked_records(tmp_path):
    cfg = _config(tmp_path)
    _write(tmp_path / "entities.parquet", [{"entity_id": "LEI1", "canonical_name": "Fund Manager LLC"}])
    _write(
        tmp_path / "entity_identifiers.parquet",
        [
            {"entity_id": "LEI1", "identifier_type": "ISIN", "identifier_value": f"US{n:010d}", "confidence": "SOURCE",
             "source": "gleif", "source_file": None, "snapshot_date": None, "ingested_at": None}
            for n in range(250)
        ]
        + [{"entity_id": "LEI1", "identifier_type": "CIK", "identifier_value": "0000000001", "confidence": "AUTO_MATCH",
            "source": "sec_13f_crosswalk", "source_file": None, "snapshot_date": None, "ingested_at": None}],
    )
    _write(
        tmp_path / "gleif_relationship_exceptions.parquet",
        [{"lei": "LEI1", "exception_category": "DIRECT_ACCOUNTING_CONSOLIDATION_PARENT", "exception_reason": "NO_KNOWN_PERSON"}],
    )
    edge = {"valid_from": None, "valid_to": None, "source_file": None, "snapshot_date": None, "ingested_at": None}
    _write(
        tmp_path / "knowledge_edges.parquet",
        [
            {"start_node_id": "cik:0000000001", "end_node_id": "lei:LEI1", "edge_type": "SAME_AS",
             "source": "sec_13f_crosswalk", "source_record_ref": "x", **edge},
            {"start_node_id": "cik:0000000001", "end_node_id": "cik:0000000099", "edge_type": "BENEFICIAL_OWNER",
             "source": "sec_13dg", "source_record_ref": "0000000000-26-000001:1", **edge},
        ],
    )
    _write(
        tmp_path / "knowledge_nodes.parquet",
        [
            {"node_id": "cik:0000000001", "node_type": "LEGAL_ENTITY", "display_name": "Fund Manager"},
            {"node_id": "cik:0000000099", "node_type": "LEGAL_ENTITY", "display_name": "Issuer Inc"},
        ],
    )
    _write(
        tmp_path / "crosswalk_sec_13f_gleif.parquet",
        [{"cik": "0000000001", "filer_name": "Fund Manager", "lei": "LEI1", "decision": "AUTO_MATCH", "score": 160.0,
          "gap": 50.0, "reason": None, "snapshot_date": "2026-10-03", "runner_up_lei": None, "runner_up_score": None,
          "feature_contributions": json.dumps({"name_exact": 100.0}), "config_hash": "abc"}],
    )

    ((entity_id, doc),) = list(entity_documents(cfg))

    assert entity_id == "LEI1"
    assert doc["identifier_total"] == 251
    assert len(doc["identifiers"]) == 201  # 200 ISINs kept, plus the CIK
    assert doc["ciks"] == ["0000000001"]
    assert doc["exceptions"][0]["exception_reason"] == "NO_KNOWN_PERSON"
    assert doc["connections"]["linked_records"][0]["node_id"] == "cik:0000000001"
    (group,) = doc["connections"]["groups"]
    assert (group["edge_type"], group["direction"], group["total"]) == ("BENEFICIAL_OWNER", "outgoing", 1)
    assert group["connections"][0]["other_name"] == "Issuer Inc"
    assert group["connections"][0]["source_url"].endswith("/99/000000000026000001/primary_doc.xml")
    assert doc["match_decisions"][0]["feature_contributions"] == {"name_exact": 100.0}

    store = MemoryStore({ENTITIES: {entity_id: doc}})
    record_review(store, "cik:0000000001", "LEI1", "rejected", "ana", "different series")
    (decision,) = load_match_decisions(store, "LEI1")
    assert [(review.outcome, review.reviewer) for review in decision.reviews] == [("REJECTED", "ana")]


def test_opensearch_store_passes_source_fields_as_api_arguments():
    """OpenSearch ignores ``params`` here, returning an empty source selection."""

    class Client:
        def get(self, *, _source_includes=None, **_):
            document = {"entity_id": "LEI1", "canonical_name": "Fund Manager LLC"}
            return {"_source": {field: document[field] for field in _source_includes or document}}

        def mget(self, *, body, _source_includes=None, **_):
            document = {"entity_id": "LEI1", "canonical_name": "Fund Manager LLC"}
            source = {field: document[field] for field in _source_includes or document}
            return {"docs": [{"_id": doc_id, "found": True, "_source": source} for doc_id in body["ids"]]}

    store = OpenSearchStore(Client(), "er")

    assert store.get(ENTITIES, "LEI1", fields=("entity_id",)) == {"entity_id": "LEI1"}
    assert store.mget(ENTITIES, ["LEI1"], fields=("canonical_name",)) == {
        "LEI1": {"canonical_name": "Fund Manager LLC"}
    }


def test_adv_documents_and_pages_become_serving_documents(tmp_path):
    cfg = _config(tmp_path)
    cfg.sec_adv.processed_dir = tmp_path
    document = {
        "crd_number": "12345",
        "brochure_id": "789",
        "pdf_file_name": "brochure.pdf",
        "content_hash": "abc",
        "page_count": 1,
        "extraction_error": None,
        "source_file": "archive.zip:brochure.pdf",
        "snapshot_date": "2026-03-31",
        "ingested_at": "2026-04-01T00:00:00+00:00",
    }
    page = {**document, "page_number": 1, "text": "Assets under management: 125,000,000 dollars."}
    page.pop("page_count")
    page.pop("extraction_error")
    _write(tmp_path / "sec_adv_documents.parquet", [document])
    _write(tmp_path / "sec_adv_pages.parquet", [page])

    ((document_id, published_document),) = list(adv_document_documents(cfg))
    ((page_id, published_page),) = list(adv_page_documents(cfg))

    assert document_id == "abc:archive.zip:brochure.pdf"
    assert published_document["source_file"] == "archive.zip:brochure.pdf"
    assert page_id == "abc:1:archive.zip:brochure.pdf"
    assert published_page["text"] == page["text"]


def test_nport_fund_document_is_the_latest_report_with_holdings_ranked_by_usd_value(tmp_path):
    cfg = _config(tmp_path)
    cfg.nport.processed_dir = tmp_path
    fund = {"series_lei": "FUNDLEI", "series_id": "S1", "series_name": "Global Fund", "cik": "0000000001",
            "registrant_name": "Trust", "registrant_lei": "TRUSTLEI", "total_assets": 1.0,
            "total_liabilities": 0.0, "source_file": "q.zip", "snapshot_date": None, "ingested_at": None}
    _write(tmp_path / "nport_funds.parquet", [
        {**fund, "accession_number": "older", "report_date": "31-JAN-2026", "filing_date": "30-MAR-2026", "net_assets": 1.0},
        {**fund, "accession_number": "original", "report_date": "31-MAR-2026", "filing_date": "29-MAY-2026", "net_assets": 2.0},
        {**fund, "accession_number": "amended", "report_date": "31-MAR-2026", "filing_date": "15-JUN-2026", "net_assets": 3.0},
    ])
    holding = {"issuer_lei": None, "issuer_title": None, "isin": None, "ticker": None, "balance": None, "unit": None,
               "exchange_rate": None, "payoff_profile": "Long", "asset_category": "EC", "issuer_type": None,
               "investment_country": None, "fair_value_level": None, "derivative_category": None,
               "source_file": "q.zip", "snapshot_date": None, "ingested_at": None}
    _write(tmp_path / "nport_holdings.parquet", [
        {**holding, "accession_number": "amended", "holding_id": "h1", "issuer_name": "Small", "issuer_cusip": "C1",
         "currency_code": "JPY", "currency_value": 10.0, "percentage": 1.0},
        {**holding, "accession_number": "amended", "holding_id": "h2", "issuer_name": "Large", "issuer_cusip": "C2",
         "currency_code": "EUR", "currency_value": 900.0, "percentage": 30.0},
        {**holding, "accession_number": "original", "holding_id": "h3", "issuer_name": "Superseded", "issuer_cusip": "C3",
         "currency_code": "USD", "currency_value": 5000.0, "percentage": 50.0},
    ])

    ((doc_id, doc),) = list(nport_fund_documents(cfg))

    assert doc_id == "FUNDLEI"
    assert (doc["accession_number"], doc["net_assets"], doc["holding_count"]) == ("amended", 3.0, 2)
    assert [(h["issuer_name"], h["value_usd"]) for h in doc["top_holdings"]] == [("Large", 900.0), ("Small", 10.0)]


def test_fund_structure_is_found_by_ticker_or_registrant_lei_with_nport_leis_joined(tmp_path):
    cfg = _config(tmp_path)
    cfg.sec_series_class.processed_dir = cfg.nport.processed_dir = tmp_path
    register = {"reporting_file_number": "811-1", "cik": "0000000042", "entity_name": "Index Trust",
                "entity_org_type": "30", "city": None, "state": None, "zip_code": None,
                "source_file": "series.csv", "snapshot_date": "2026-12-31", "ingested_at": None}
    _write(tmp_path / "sec_series_classes.parquet", [
        {**register, "series_id": "S1", "series_name": "Equity Fund", "class_id": "C1", "class_name": "Admiral", "class_ticker": "eqax"},
        {**register, "series_id": "S1", "series_name": "Equity Fund", "class_id": "C2", "class_name": "Investor", "class_ticker": None},
        {**register, "series_id": "S2", "series_name": "Bond Fund", "class_id": "C3", "class_name": "ETF", "class_ticker": "BNDX"},
    ])
    _write(tmp_path / "nport_funds.parquet", [
        {"series_id": "S1", "series_lei": "SERIESLEI1", "registrant_lei": "TRUSTLEI", "report_date": "31-MAR-2026"},
    ])
    store = MemoryStore({FUND_SERIES: dict(fund_series_documents(cfg))})

    by_ticker = get_fund_structure(store, "EQAX", id_type="ticker").data["registrants"]
    by_registrant = get_fund_structure(store, "TRUSTLEI", id_type="lei")

    assert [(series["series_id"], series["series_lei"]) for series in by_ticker[0]["series"]] == [("S1", "SERIESLEI1")]
    assert [c["class_id"] for c in by_ticker[0]["series"][0]["classes"]] == ["C1", "C2"]
    facts = {fact.fact_id: fact.value for fact in by_registrant.facts}
    registrant = by_registrant.data["registrants"][0]
    # S2 files no N-PORT of its own but shares the registrant's LEI.
    assert facts[registrant["series_count_fact_id"]] == 2
    assert facts[registrant["cik_fact_id"]] == "0000000042"


def test_security_lookup_resolves_one_share_class_and_flags_an_ambiguous_cusip(tmp_path):
    cfg = _config(tmp_path)
    cfg.openfigi.processed_dir = tmp_path
    base = {"mapping_rank": 1, "market_sector": "Equity", "security_type": "Common Stock", "security_type_2": None,
            "error": None, "source_file": "mapping-x.json", "snapshot_date": "2026-10-03", "ingested_at": None}
    _write(tmp_path / "openfigi_mappings.parquet", [
        {**base, "cusip": "037833100", "figi": "BBG000B9XRY4", "name": "APPLE INC", "ticker": "AAPL", "exchange_code": "US",
         "share_class_figi": "BBG001S5N8V8", "composite_figi": "BBG000B9XRY4"},
        {**base, "cusip": "037833100", "figi": "BBG000B9XVV8", "name": "APPLE INC", "ticker": "AAPL", "exchange_code": "UW",
         "share_class_figi": "BBG001S5N8V8", "composite_figi": "BBG000B9XRY4"},
        {**base, "cusip": "123456789", "figi": "BBG000000001", "name": "A", "ticker": "AAA", "exchange_code": "US",
         "share_class_figi": None, "composite_figi": None},
        {**base, "cusip": "123456789", "figi": "BBG000000002", "name": "B", "ticker": "BBB", "exchange_code": "US",
         "share_class_figi": None, "composite_figi": None},
    ])
    store = MemoryStore({SECURITIES: dict(security_documents(cfg))})

    apple = get_security(store, "aapl", id_type="ticker")
    ambiguous = get_security(store, "123456789")

    (match,) = apple.data["matches"]
    assert (match["cusip"], match["status"]) == ("037833100", "resolved")
    assert match["securities"][0]["share_class_figi"] == "BBG001S5N8V8"
    assert match["securities"][0]["listing_count"] == 2
    assert ambiguous.data["matches"][0]["status"] == "ambiguous"
    assert "none of them can be named" in ambiguous.evidence[0].warnings[0]
