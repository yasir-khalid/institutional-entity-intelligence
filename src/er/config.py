from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(REPO_ROOT / ".env")


class GleifConfig(BaseModel):
    raw_dir: Path
    processed_dir: Path
    entities_zip: str
    relationships_zip: str
    exceptions_zip: str
    isin_lei_zip: str
    batch_size: int = 50_000


class BenchmarkConfig(BaseModel):
    output_dir: Path
    seed: int = 42
    eval_sample_size: int = 5000
    min_core_tokens: int = 3
    max_confusable_group_size: int = 10


class OpenSearchConfig(BaseModel):
    index_name: str
    number_of_shards: int = 2
    number_of_replicas: int = 0
    bulk_batch_size: int = 2000


class SearchConfig(BaseModel):
    default_size: int = 20


class MatchingWeights(BaseModel):
    name_exact: float = 100
    name_core_exact: float = 60
    name_ratio: float = 40
    jurisdiction_exact: float = 25
    country_exact: float = 15
    postcode_exact: float = 35
    postcode_prefix_exact: float = 15
    city_exact: float = 10
    fund_number_exact: float = 20
    registration_id_exact: float = 250


class MatchingPenalties(BaseModel):
    fund_number_conflict: float = 100
    master_conflict: float = 80
    feeder_conflict: float = 80
    registration_id_conflict: float = 250


class MatchingDecisionThresholds(BaseModel):
    auto_match_min_score: float = 140
    auto_match_min_gap: float = 30
    review_min_score: float = 90
    # Candidates within this many points of the top score are considered "tied" -
    # i.e. the query doesn't contain enough information to distinguish them (e.g.
    # "North Rock Capital" alone can't tell apart 5 same-named entities across 5
    # countries). Used only to build a human-readable reason, not in decide() itself.
    tie_tolerance: float = 5.0


class MatchingConfig(BaseModel):
    candidate_pool_size: int = 20
    weights: MatchingWeights = MatchingWeights()
    penalties: MatchingPenalties = MatchingPenalties()
    decision: MatchingDecisionThresholds = MatchingDecisionThresholds()


class FamilyConfig(BaseModel):
    candidate_pool_size: int = 100


class AppConfig(BaseModel):
    gleif: GleifConfig
    opensearch: OpenSearchConfig
    search: SearchConfig
    benchmark: BenchmarkConfig
    matching: MatchingConfig = MatchingConfig()
    family: FamilyConfig = FamilyConfig()

    @property
    def opensearch_url(self) -> str:
        url = os.environ.get("OPENSEARCH_URL")
        if not url:
            raise RuntimeError(
                "OPENSEARCH_URL is not set. Copy .env.example to .env and fill it in."
            )
        return url


@lru_cache
def load_config(path: str | Path = REPO_ROOT / "config" / "dev.yaml") -> AppConfig:
    raw = yaml.safe_load(Path(path).read_text())
    raw["gleif"]["raw_dir"] = REPO_ROOT / raw["gleif"]["raw_dir"]
    raw["gleif"]["processed_dir"] = REPO_ROOT / raw["gleif"]["processed_dir"]
    raw["benchmark"]["output_dir"] = REPO_ROOT / raw["benchmark"]["output_dir"]
    return AppConfig.model_validate(raw)
