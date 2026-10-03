import json

import pyarrow as pa
import pyarrow.parquet as pq

from er.config import load_config
from er.entity.resolution import load_match_decisions, record_review
from er.serving.publish import adv_document_documents, adv_page_documents, entity_documents
from er.serving.store import ENTITIES, MemoryStore, OpenSearchStore


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
