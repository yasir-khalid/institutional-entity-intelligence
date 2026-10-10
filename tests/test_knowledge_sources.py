from __future__ import annotations

import json
import zipfile

import duckdb

from er.config import load_config
from er.crosswalk.sec_13f_to_gleif import CROSSWALK_SCHEMA
from er.datasources.common.parquet_writer import BatchedParquetWriter
from er.datasources.ffiec_nic.ingest import run_all as ingest_nic
from er.datasources.openfigi.ingest import build_mappings
from er.datasources.sec_series_class.ingest import parse_file
from er.knowledge.build import run_all


def _isolated_config(tmp_path):
    cfg = load_config().model_copy(deep=True)
    for section in (
        cfg.gleif,
        cfg.sec_13f,
        cfg.sec_submissions,
        cfg.sec_series_class,
        cfg.openfigi,
        cfg.nport,
        cfg.sec_insiders,
        cfg.sec_adv,
        cfg.companies_house,
        cfg.sec_13dg,
        cfg.ffiec_nic,
    ):
        section.raw_dir = tmp_path / section.__class__.__name__ / "raw"
        section.processed_dir = tmp_path / "processed"
    cfg.entity.processed_dir = tmp_path / "processed"
    cfg.entity.review_file = tmp_path / "match_reviews.csv"
    return cfg


def test_series_and_classes_remain_distinct_graph_nodes(tmp_path):
    cfg = _isolated_config(tmp_path)
    source = tmp_path / "investment-company-series-class-2026.csv"
    source.write_text(
        "Reporting File Number,CIK Number,Entity Name,Entity Org Type,Series ID,Series Name,"
        "Class ID,Class Name,Class Ticker,Address_1,Address_2,City,State,Zip Code\n"
        "811-00001,0000123456,Example Trust,30,S000000001,Example Fund,"
        "C000000001,Investor Class,EXMPL,1 Main St,,Boston,MA,02110\n"
    )

    assert parse_file(cfg, source) == 1
    counts = run_all(cfg)

    assert counts == {"nodes": 3, "edges": 2, "identifiers": 2, "facts": 0}
    nodes = duckdb.sql(
        f"SELECT node_id, node_type FROM read_parquet('{cfg.entity.processed_dir / 'knowledge_nodes.parquet'}')"
    ).fetchall()
    assert set(nodes) == {
        ("cik:0000123456", "LEGAL_ENTITY"),
        ("series:S000000001", "FUND_SERIES"),
        ("class:C000000001", "SHARE_CLASS"),
    }


def test_openfigi_links_a_cusip_only_when_its_listings_share_one_security(tmp_path):
    # One FIGI per exchange listing, all with one share-class FIGI, is one
    # security; two unrelated FIGIs for one CUSIP is ambiguous and unlinked.
    cfg = _isolated_config(tmp_path)
    cfg.openfigi.raw_dir.mkdir(parents=True)
    listing = {"name": "Acme Corp", "shareClassFIGI": "BBG00CLASS01"}
    cache = {
        "requested_at": "2026-10-02T12:00:00+00:00",
        "jobs": [{"idType": "ID_CUSIP", "idValue": "123456789"}, {"idType": "ID_CUSIP", "idValue": "987654321"}],
        "responses": [
            {"data": [{**listing, "figi": "BBG00LIST001", "exchCode": "US"}, {**listing, "figi": "BBG00LIST002", "exchCode": "UN"}]},
            {"data": [{"figi": "BBG000000001", "name": "Class A"}, {"figi": "BBG000000002", "name": "Class B"}]},
        ],
    }
    (cfg.openfigi.raw_dir / "mapping-example.json").write_text(json.dumps(cache))

    assert build_mappings(cfg) == 4
    run_all(cfg)

    edges = _rows(cfg.entity.processed_dir / "knowledge_edges.parquet", "start_node_id, end_node_id")
    assert edges == {("security:cusip:123456789", "figi:BBG00CLASS01")}


def _rows(path, columns):
    return set(duckdb.sql(f"SELECT {columns} FROM read_parquet('{path}')").fetchall())


def test_reviews_override_crosswalk_links_and_decisions_stay_citable(tmp_path):
    cfg = _isolated_config(tmp_path)
    writer = BatchedParquetWriter(cfg.sec_13f.processed_dir / "crosswalk_sec_13f_gleif.parquet", CROSSWALK_SCHEMA)
    for cik, lei in (("0000000001", "LEIA"), ("0000000002", "LEIB")):
        writer.add(
            {
                "filer_name": f"Filer {cik}", "cik": cik, "lei": lei, "decision": "AUTO_MATCH",
                "score": 160.0, "gap": 45.0, "runner_up_lei": "LEIZ", "runner_up_score": 115.0,
                "feature_contributions": json.dumps({"name_exact": 100.0, "country_exact": 15.0}),
                "config_hash": "abc123", "snapshot_date": "2026-10-01",
            }
        )
    writer.close()
    cfg.entity.review_file.write_text(
        "node_id,lei,outcome,reviewer,reviewed_at,rationale\n"
        "cik:0000000001,LEIA,CONFIRMED,ana,2026-10-01,same address\n"
        "cik:0000000001,LEIA,REJECTED,ana,2026-10-02,different fund series\n"
        "cik:0000000003,LEIC,CONFIRMED,ben,2026-10-02,checked the ADV\n"
    )

    run_all(cfg)

    edges = _rows(
        cfg.entity.processed_dir / "knowledge_edges.parquet",
        "start_node_id, end_node_id, source",
    )
    assert edges == {
        ("cik:0000000002", "lei:LEIB", "sec_13f_crosswalk"),
        ("cik:0000000003", "lei:LEIC", "human_review"),
    }
    facts = _rows(
        cfg.entity.processed_dir / "knowledge_facts.parquet",
        "subject_node_id, object_node_id, predicate, value",
    )
    assert ("cik:0000000002", "lei:LEIB", "match.feature.name_exact", "100.0") in facts
    assert ("cik:0000000002", "lei:LEIB", "match.runner_up_lei", "LEIZ") in facts
    assert ("cik:0000000001", "lei:LEIA", "review.outcome", "REJECTED") in facts


def test_nic_graph_keeps_only_current_control_and_links_rssd_to_lei(tmp_path):
    cfg = _isolated_config(tmp_path)
    cfg.ffiec_nic.raw_dir.mkdir(parents=True)
    tables = {
        "CSV_ATTRIBUTES_ACTIVE": (
            '"#ID_RSSD","NM_LGL","ID_LEI","DT_OPEN","DT_END"\n'
            '"1","HOLDCO INC","HOLDCOLEI00000000001","19900101","99991231"\n'
            '"2","BANK NA","0","19900101","99991231"\n'
            '"3","OLD PARENT INC","0","19900101","99991231"\n'
        ),
        "CSV_RELATIONSHIPS": (
            '"#ID_RSSD_PARENT","ID_RSSD_OFFSPRING","CTRL_IND","PCT_EQUITY","DT_START","DT_END"\n'
            '"1","2","1","100","20100101","99991231"\n'
            '"3","2","1","100","19900101","20091231"\n'
        ),
    }
    for name, body in tables.items():
        with zipfile.ZipFile(cfg.ffiec_nic.raw_dir / f"{name}.zip", "w") as archive:
            archive.writestr(f"{name}.csv", body)

    assert ingest_nic(cfg) == {"institutions": 3, "relationships": 2, "transformations": 0}
    run_all(cfg)

    assert _rows(cfg.entity.processed_dir / "knowledge_edges.parquet", "start_node_id, end_node_id, edge_type") == {
        ("rssd:1", "lei:HOLDCOLEI00000000001", "SAME_AS"),
        ("rssd:2", "rssd:1", "BANK_CONTROL_PARENT"),
    }
