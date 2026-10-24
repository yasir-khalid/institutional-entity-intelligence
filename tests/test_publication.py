"""Exercise the publisher against an in-process OpenSearch storage boundary.

Real builders and Parquet input profiles run; only HTTP/bulk storage is replaced.
Failure assertions inspect what readers see, not internal helper call shapes.
"""
import copy

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from er.config import load_config
from er.serving import publish
from er.serving.store import ADV_PAGES, COVERAGE, DECISIONS, XBRL_FACTS, XBRL_ISSUERS, MemoryStore
from er.serving.coverage import build_coverage
from er.entity.resolution import review_queue, record_review


class SearchStorage:
    def __init__(self):
        self.indices = self
        self.documents = {}
        self.aliases = {}
        self.fail_bulk = None
        self.bad_count = None
        self.visible_snapshots = []

    def create(self, index, body):
        self.documents[index] = {}

    def exists(self, index):
        return index in self.documents

    def exists_alias(self, name):
        return name in self.aliases

    def get_alias(self, name):
        return {index: {} for index in self.aliases[name]}

    def delete(self, index, **kwargs):
        self.documents.pop(index, None)

    def put_settings(self, **kwargs):
        pass

    def refresh(self, **kwargs):
        pass

    def count(self, index):
        return {"count": len(self.documents[index]) + (1 if self.bad_count and self.bad_count in index else 0)}

    def update_aliases(self, body):
        updated = copy.deepcopy(self.aliases)
        for action in body["actions"]:
            if "remove" in action:
                row = action["remove"]
                updated[row["alias"]].remove(row["index"])
            else:
                row = action["add"]
                updated.setdefault(row["alias"], []).append(row["index"])
        self.aliases = updated
        self.visible_snapshots.append(copy.deepcopy(updated))

    def read(self, alias, doc_id):
        return self.documents[self.aliases[alias][0]][doc_id]


def bulk_storage(client, actions, **kwargs):
    for action in actions:
        if client.fail_bulk and client.fail_bulk in action["_index"]:
            raise RuntimeError("Interrupted upload")
        client.documents[action["_index"]][action["_id"]] = action["_source"]
        yield True, {}


@pytest.fixture
def publication(tmp_path, monkeypatch):
    cfg = load_config().model_copy(deep=True)
    for field in type(cfg).model_fields:
        section = getattr(cfg, field)
        if hasattr(section, "processed_dir"):
            section.processed_dir = tmp_path
    client = SearchStorage()
    client.documents[f"{cfg.serving.prefix}_investigations"] = {"saved": {"answer": "Preserved"}}
    monkeypatch.setattr(publish, "get_client", lambda cfg: client)
    monkeypatch.setattr(publish.helpers, "parallel_bulk", bulk_storage)
    pq.write_table(pa.Table.from_pylist([{"entity_id": "LEI1", "canonical_name": "Manager"}]), tmp_path / "entities.parquet")
    pq.write_table(pa.Table.from_pylist([{"entity_id": "LEI1", "identifier_type": "CIK", "identifier_value": "0000000001",
                                        "confidence": "SOURCE", "source": "sec_submissions", "source_file": None,
                                        "snapshot_date": None, "ingested_at": None}]), tmp_path / "entity_identifiers.parquet")
    pq.write_table(pa.Table.from_pylist([{"lei": "LEI1", "exception_category": "DIRECT_ACCOUNTING_CONSOLIDATION_PARENT",
                                        "exception_reason": "NO_KNOWN_PERSON"}]), tmp_path / "gleif_relationship_exceptions.parquet")
    row = {"crd_number": "123", "brochure_id": "789", "pdf_file_name": "brochure.pdf", "content_hash": "hash",
           "page_count": 1, "extraction_error": None, "source_file": "archive:brochure.pdf",
           "snapshot_date": "2026-03-31", "ingested_at": None}
    pq.write_table(pa.Table.from_pylist([row]), tmp_path / "sec_adv_documents.parquet")
    page = {**row, "page_number": 1, "text": "Original source text"}
    page.pop("page_count")
    page.pop("extraction_error")
    pq.write_table(pa.Table.from_pylist([page]), tmp_path / "sec_adv_pages.parquet")
    return cfg, client, page


@pytest.mark.parametrize("failure", ["bulk", "count"])
def test_later_staging_failure_leaves_every_live_alias_and_document_unchanged(publication, failure):
    cfg, client, page = publication
    publish.run_all(cfg)
    old = copy.deepcopy(client.aliases)
    page["text"] = "Updated source text"
    pq.write_table(pa.Table.from_pylist([page]), cfg.sec_adv.processed_dir / "sec_adv_pages.parquet")
    if failure == "bulk":
        client.fail_bulk = f"_{ADV_PAGES}_"
    else:
        client.bad_count = f"_{ADV_PAGES}_"
    with pytest.raises(RuntimeError, match="Interrupted upload" if failure == "bulk" else "does not reconcile"):
        publish.run_all(cfg)
    assert client.aliases == old
    assert client.read(f"{cfg.serving.prefix}_{ADV_PAGES}", "hash:1:archive:brochure.pdf")["text"] == "Original source text"
    assert len(client.visible_snapshots) == 1


def test_full_generation_switch_and_validated_rollback_preserve_runtime_metadata(publication):
    cfg, client, page = publication
    counts = publish.run_all(cfg)
    first = client.read(f"{cfg.serving.prefix}_{COVERAGE}", "current")["generation"]
    assert counts[ADV_PAGES] == 1
    assert {indexes[0].rsplit("_", 1)[1] for indexes in client.aliases.values()} == {first}
    page["text"] = "Updated source text"
    pq.write_table(pa.Table.from_pylist([page]), cfg.sec_adv.processed_dir / "sec_adv_pages.parquet")
    publish.run_all(cfg)
    current = client.read(f"{cfg.serving.prefix}_{COVERAGE}", "current")
    assert current["previous_generation"] == first
    assert current["partial"] is False
    assert len(client.visible_snapshots) == 2
    publish.rollback(cfg, first)
    assert client.read(f"{cfg.serving.prefix}_{ADV_PAGES}", "hash:1:archive:brochure.pdf")["text"] == "Original source text"
    assert client.documents[f"{cfg.serving.prefix}_investigations"]["saved"]["answer"] == "Preserved"
    # A missing retained index is rejected before any live aliases change.
    second_aliases = copy.deepcopy(client.aliases)
    target = next(iter(current["indexes"].values()))["index"]
    client.delete(target)
    with pytest.raises(ValueError, match="no longer available"):
        publish.rollback(cfg, current["generation"])
    assert client.aliases == second_aliases
    publish.run_all(cfg, only=[ADV_PAGES])
    partial = client.read(f"{cfg.serving.prefix}_{COVERAGE}", "current")
    assert partial["partial"] is True
    before_rollback = copy.deepcopy(client.aliases)
    with pytest.raises(ValueError, match="complete publication"):
        publish.rollback(cfg, partial["generation"])
    assert client.aliases == before_rollback


def test_coverage_dates_counts_and_queue_reviews_come_from_published_crosswalk(publication):
    cfg, client, _ = publication
    base = {"filer_name": "Manager", "lei": "LEI1", "decision": "REVIEW", "score": 120.0, "gap": 2.0,
            "snapshot_date": "2026-03-31", "feature_contributions": '{"name_exact":100.0}'}
    pq.write_table(pa.Table.from_pylist([{**base, "cik": "0000000001"}, {**base, "cik": "0000000002"}]),
                   cfg.sec_13f.processed_dir / "crosswalk_sec_13f_gleif.parquet")
    pq.write_table(pa.Table.from_pylist([{"filing_date": "15-JUN-2026"}]), cfg.sec_13f.processed_dir / "sec_13f_filings.parquet")
    inventory = build_coverage(cfg)
    assert inventory["decisions"] == {"AUTO_MATCH": 0, "REVIEW": 2, "UNMATCHED": 0}
    assert next(source for source in inventory["sources"] if source["source"] == "sec_13f")["as_of"] == "2026-06-15"
    store = MemoryStore({DECISIONS: dict(publish.decision_documents(cfg))})
    record_review(store, "cik:0000000001", "LEI1", "rejected", "Ana", "Another series")
    first = review_queue(store, limit=1)
    assert first["next_offset"] == 1
    assert first["items"][0]["decision"] == "REVIEW"
    assert first["items"][0]["feature_contributions"] == {"name_exact": 100.0}
    assert first["items"][0]["reviews"][0]["outcome"] == "REJECTED"
    assert review_queue(store, offset=1, limit=1)["next_offset"] is None


def test_xbrl_publishes_one_dated_series_per_concept_with_duplicates_collapsed(publication):
    cfg, client, _ = publication
    fact = {"cik": "0001571996", "entity_name": "Dell Technologies Inc.", "tag": "Assets", "unit": "USD",
            "value": 100.0, "period_start": None, "period_end": "2025-01-31", "fiscal_year": 2025,
            "fiscal_period": "FY", "form": "10-K", "filed": "2025-03-01", "accession_number": "a1",
            "frame": None, "source_file": "companyfacts/CIK0001571996.json", "snapshot_date": "2026-01-01",
            "ingested_at": None}
    pq.write_table(
        pa.Table.from_pylist([fact, {**fact}, {**fact, "period_end": "2024-01-31", "filed": "2024-03-01", "value": 90.0}]),
        cfg.sec_xbrl.processed_dir / "sec_xbrl_facts.parquet",
    )
    pq.write_table(
        pa.Table.from_pylist([{"cik": "0001571996", "entity_name": "Dell Technologies Inc.",
                               "tickers": ["DELL"], "former_names": [], "sic": "3571",
                               "sic_description": "Electronic Computers", "fiscal_year_end": "0131",
                               "source_file": "companyfacts/CIK0001571996.json", "snapshot_date": "2026-01-01",
                               "ingested_at": None}]),
        cfg.sec_xbrl.processed_dir / "sec_xbrl_issuers.parquet",
    )

    counts = publish.run_all(cfg)

    assert counts[XBRL_FACTS] == 1  # keyed by cik+tag+unit, not one doc per row
    assert counts[XBRL_ISSUERS] == 1
    document = client.read(f"{cfg.serving.prefix}_{XBRL_FACTS}", "0001571996:Assets:USD")
    assert [observation["period_end"] for observation in document["observations"]] == ["2024-01-31", "2025-01-31"]
    assert [observation["value"] for observation in document["observations"]] == [90.0, 100.0]
    issuer = client.read(f"{cfg.serving.prefix}_{XBRL_ISSUERS}", "0001571996")
    assert issuer["tickers"] == ["DELL"]
