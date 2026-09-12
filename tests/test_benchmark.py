import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from er.benchmark.generate import _name_variant, _seed_fraction, generate_hard_negatives, generate_positives
from er.config import AppConfig, BenchmarkConfig, GleifConfig, OpenSearchConfig, SearchConfig

ENTITY_COLUMNS = [
    "lei",
    "legal_name",
    "legal_name_norm",
    "legal_name_core",
    "jurisdiction",
    "legal_country",
    "entity_status",
    "fund_number",
    "is_master",
    "is_feeder",
]


def _entity_row(lei, name_core, jurisdiction="IE", fund_number=None, is_master=False, is_feeder=False):
    return {
        "lei": lei,
        "legal_name": name_core.title(),
        "legal_name_norm": name_core,
        "legal_name_core": name_core,
        "jurisdiction": jurisdiction,
        "legal_country": jurisdiction,
        "entity_status": "ACTIVE",
        "fund_number": fund_number,
        "is_master": is_master,
        "is_feeder": is_feeder,
    }


@pytest.fixture
def cfg(tmp_path):
    processed = tmp_path / "processed"
    processed.mkdir()
    benchmark_dir = tmp_path / "benchmark"
    benchmark_dir.mkdir()
    return AppConfig(
        gleif=GleifConfig(
            raw_dir=tmp_path / "raw",
            processed_dir=processed,
            entities_zip="e.zip",
            relationships_zip="r.zip",
            exceptions_zip="x.zip",
            isin_lei_zip="i.zip",
        ),
        opensearch=OpenSearchConfig(index_name="test"),
        search=SearchConfig(),
        benchmark=BenchmarkConfig(output_dir=benchmark_dir, seed=42, eval_sample_size=100, min_core_tokens=3),
    )


def _write_entities(cfg, rows):
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, cfg.gleif.processed_dir / "gleif_entities.parquet")


def _write_isin_lei(cfg, rows):
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, cfg.gleif.processed_dir / "isin_lei.parquet")


def test_name_variant_is_deterministic():
    a1 = _name_variant("Acme Global Fund", "acme global fund", "LEI123")
    a2 = _name_variant("Acme Global Fund", "acme global fund", "LEI123")
    assert a1 == a2


def test_name_variant_easy_uses_raw_name():
    # find a seed_key that lands in bucket 0 (easy) by brute force over a few candidates
    for key in [f"LEI{i}" for i in range(20)]:
        query, difficulty = _name_variant("Raw Name Ltd", "raw name", key)
        if difficulty == "easy":
            assert query == "Raw Name Ltd"
            return
    pytest.fail("no candidate key landed in the easy bucket")


def test_seed_fraction_within_duckdb_range():
    for seed in [0, 1, 42, 999999]:
        assert -1.0 <= _seed_fraction(seed) <= 1.0


def test_generate_hard_negatives_detects_fund_number_conflict(cfg):
    # Regression test for the grouping bug: legal_name_core embeds the fund number
    # ("...fund ii" vs "...fund iii" are DIFFERENT legal_name_core strings), so
    # grouping by legal_name_core alone could never pair these up. Only the
    # aggressive_core (fund-number/structure-token stripped) grouping key can.
    cfg.gleif.processed_dir.mkdir(parents=True, exist_ok=True)
    _write_entities(
        cfg,
        [
            _entity_row("LEI0000000000000001", "acme global opportunities fund ii", fund_number=2),
            _entity_row("LEI0000000000000002", "acme global opportunities fund iii", fund_number=3),
        ],
    )
    out_path = generate_hard_negatives(cfg)
    table = pq.read_table(out_path)
    assert table.num_rows == 1
    row = table.to_pylist()[0]
    assert row["conflict_type"] == "fund_number"
    assert row["aggressive_core"] == "acme global opportunities fund"
    assert {row["lei_a"], row["lei_b"]} == {"LEI0000000000000001", "LEI0000000000000002"}


def test_generate_hard_negatives_detects_master_feeder_conflict(cfg):
    # Same class of bug: "...master fund" and "...feeder fund" are different
    # legal_name_core strings; only aggressive_core strips "master"/"feeder" to
    # make them groupable.
    cfg.gleif.processed_dir.mkdir(parents=True, exist_ok=True)
    _write_entities(
        cfg,
        [
            _entity_row("LEI0000000000000001", "acme global credit master fund", is_master=True),
            _entity_row("LEI0000000000000002", "acme global credit feeder fund", is_feeder=True),
        ],
    )
    out_path = generate_hard_negatives(cfg)
    table = pq.read_table(out_path)
    assert table.num_rows == 1
    row = table.to_pylist()[0]
    assert row["conflict_type"] == "master_feeder"
    assert row["aggressive_core"] == "acme global credit fund"


def test_generate_hard_negatives_skips_short_core_names(cfg):
    cfg.gleif.processed_dir.mkdir(parents=True, exist_ok=True)
    _write_entities(
        cfg,
        [
            _entity_row("LEI0000000000000001", "acme fund"),  # 2 tokens, below min_core_tokens=3
            _entity_row("LEI0000000000000002", "acme fund"),
        ],
    )
    out_path = generate_hard_negatives(cfg)
    table = pq.read_table(out_path)
    assert table.num_rows == 0


def test_generate_hard_negatives_skips_unique_core_names(cfg):
    cfg.gleif.processed_dir.mkdir(parents=True, exist_ok=True)
    _write_entities(
        cfg,
        [
            _entity_row("LEI0000000000000001", "acme global opportunities fund"),
            _entity_row("LEI0000000000000002", "totally different management company"),
        ],
    )
    out_path = generate_hard_negatives(cfg)
    table = pq.read_table(out_path)
    assert table.num_rows == 0


def test_generate_positives_joins_on_isin_bridge(cfg):
    cfg.gleif.processed_dir.mkdir(parents=True, exist_ok=True)
    _write_entities(
        cfg,
        [
            _entity_row("LEI0000000000000001", "acme global opportunities fund"),
            _entity_row("LEI0000000000000002", "no isin entity"),
        ],
    )
    _write_isin_lei(
        cfg,
        [
            {"isin": "US1234567890", "lei": "LEI0000000000000001"},
            {"isin": "US1234567891", "lei": "LEI0000000000000001"},
        ],
    )
    out_path = generate_positives(cfg)
    table = pq.read_table(out_path)
    assert table.num_rows == 1
    row = table.to_pylist()[0]
    assert row["lei"] == "LEI0000000000000001"
    assert row["isin_count"] == 2
