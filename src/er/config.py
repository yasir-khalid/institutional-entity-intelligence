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


class Sec13FScaleCheck(BaseModel):
    # A filing is flagged when the median of its rows' implied price / the
    # cross-filer median for that CUSIP falls in this band (i.e. ~1/1000).
    thousands_ratio_low: float = 0.0005
    thousands_ratio_high: float = 0.002
    min_rows: int = 5
    min_filers_per_cusip: int = 5


class Sec13FConfig(BaseModel):
    raw_dir: Path
    processed_dir: Path
    batch_size: int = 50_000
    scale_check: Sec13FScaleCheck = Sec13FScaleCheck()


class SecSubmissionsConfig(BaseModel):
    raw_dir: Path = Path("data/raw/sec_submissions")
    processed_dir: Path = Path("data/processed")
    source_url: str = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
    source_file: str = "submissions.zip"
    batch_size: int = 25_000


class SecSeriesClassConfig(BaseModel):
    raw_dir: Path = Path("data/raw/sec_series_class")
    processed_dir: Path = Path("data/processed")
    source_url: str = (
        "https://www.sec.gov/files/investment/data/other/"
        "investment-company-series-class-information/"
        "investment-company-series-class-2026.csv"
    )
    source_file: str = "investment-company-series-class-2026.csv"
    batch_size: int = 25_000


class OpenFigiConfig(BaseModel):
    raw_dir: Path = Path("data/raw/openfigi")
    processed_dir: Path = Path("data/processed")
    api_url: str = "https://api.openfigi.com/v3/mapping"
    batch_size_without_key: int = 10
    batch_size_with_key: int = 100


class NPortConfig(BaseModel):
    raw_dir: Path = Path("data/raw/nport")
    processed_dir: Path = Path("data/processed")
    batch_size: int = 50_000


class SecInsidersConfig(BaseModel):
    raw_dir: Path = Path("data/raw/sec_insiders")
    processed_dir: Path = Path("data/processed")
    source_url: str = (
        "https://www.sec.gov/files/datastandardsinnovation/data/"
        "insider-transactions-data-sets/2026q2_form345.zip"
    )
    source_file: str = "2026q2_form345.zip"
    batch_size: int = 50_000


class SecAdvConfig(BaseModel):
    raw_dir: Path = Path("data/raw/sec_adv")
    processed_dir: Path = Path("data/processed")
    batch_size: int = 5_000


class CompaniesHouseConfig(BaseModel):
    raw_dir: Path = Path("data/raw/companies_house")
    processed_dir: Path = Path("data/processed")
    batch_size: int = 50_000


class Sec13DGConfig(BaseModel):
    raw_dir: Path = Path("data/raw/sec_13dg")
    processed_dir: Path = Path("data/processed")
    quarters: list[str] = ["2026Q2"]
    max_filings: int | None = None
    requests_per_second: float = 8
    workers: int = 6
    batch_size: int = 25_000


class FfiecNicConfig(BaseModel):
    raw_dir: Path = Path("data/raw/ffiec_nic")
    processed_dir: Path = Path("data/processed")
    batch_size: int = 50_000


class ServingConfig(BaseModel):
    # Every serving index is reached through an alias "<prefix>_<name>" (see
    # er.serving.store); `make publish` builds a dated index and swaps the alias.
    prefix: str = "er"
    bulk_batch_size: int = 2000
    connections_per_group: int = 25


class EntityConfig(BaseModel):
    processed_dir: Path
    # Human match reviews (CSV: source, source_record_id, lei, outcome,
    # reviewer, reviewed_at, rationale). A review never edits the automated
    # decision - both are kept and the review takes precedence in the graph.
    review_file: Path = Path("data/reviews/match_reviews.csv")


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
    # Disabling refresh during a large bulk load and restoring it after is a
    # standard OpenSearch/Elasticsearch optimization - exposed here rather than
    # hardcoded so it can be tuned (or disabled by setting both to the same value)
    # without touching code.
    refresh_interval_during_bulk: str = "-1"
    refresh_interval_after_bulk: str = "1s"


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


class VerifierConfig(BaseModel):
    """Post-answer verification with TypeSafe's Jev - see er.agent.verifier.

    `decisions_url` is a full URL rather than a suffix on
    `AgentConfig.openrouter_base_url` because the Decisions API sits on a
    different path prefix (/api/alpha/decisions) from chat completions
    (/api/v1/chat/completions), so it is not derivable from that base.

    The thresholds below are the entire badge rule. `*_min` is what a check
    must clear to count as passed; `not_contradicted_floor` is the single veto
    - below it the answer is reported as unverified no matter what else it
    scored. Tighten the badge here, never in er.agent.verifier.classify().

    The defaults are not guesses: they sit between the observed good-answer
    minimum and the observed bad-answer maximum over a 10-answer labelled set,
    measured against the live model. See
    experiments/006-jev-answer-verification.md for the readings, and re-run
    that sweep before moving any of them - notably, a *faithful* answer scores
    around 0.8 on `grounded`, not 0.95, so an intuitive-looking 0.85 bar here
    would mark almost every correct answer "partially verified".
    """

    enabled: bool = True
    model: str = "typesafe/jev-1.13"
    decisions_url: str = "https://openrouter.ai/api/alpha/decisions"
    timeout_seconds: float = 30.0
    # A Jev call that can't even connect within this is retried rather than
    # waited on for the full timeout - a ConnectTimeout blip once cost 30s and
    # a "Not checked" badge, with the next calls succeeding in ~0.3s.
    connect_timeout_seconds: float = 5.0
    retries: int = 2
    retry_backoff_seconds: float = 0.5
    # Jev's hard input limit is 32,768 tokens (measured 2026-09-28: 32,443
    # accepted, ~33.4k rejected with "max_tokens_exceeded" - not the 64k one
    # third-party write-up claims). Tool payloads here are identifier-dense
    # JSON at ~2.0 chars per token, so 50k chars is ~25k tokens, leaving
    # headroom for denser content. Characters are only a proxy, so a
    # max_tokens_exceeded reply also halves the budget and retries - see
    # er.agent.verifier.verify_answer.
    max_state_chars: int = 50_000
    grounded_min: float = 0.70
    not_contradicted_min: float = 0.87
    citations_supported_min: float = 0.70
    scope_respected_min: float = 0.75
    not_contradicted_floor: float = 0.50


class AgentConfig(BaseModel):
    # OpenRouter (https://openrouter.ai) model id - deepseek/deepseek-v4.1-flash
    # is fast/cheap and strong at structured tool-calling over data lookups
    # like these; swap here (not in code) to retune.
    openrouter_model: str = "deepseek/deepseek-v4.1-flash"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    # How the FastAPI app (and er.cli.ask) spawn the MCP server subprocess -
    # see er.agent.mcp_server. Kept as a command list, not a code path, so a
    # future deployment can point at a different interpreter/entrypoint
    # without a code change.
    mcp_server_command: list[str] = ["uv", "run", "python", "-m", "er.cli.mcp_server"]
    max_tool_turns: int = 6
    # Retries for a model call that failed *transiently*: the connection
    # dropped before any response ("Server disconnected without sending a
    # response" - seen in practice, fine again on the next call), or a
    # gateway/overload status (429/502/503/504). Never for anything else - a
    # 400 like "input exceeds 8 MB" fails identically however often it is
    # sent. Backoff doubles per attempt.
    openrouter_retries: int = 2
    openrouter_retry_backoff_seconds: float = 0.75
    # Connecting normally takes ~0.07s; see er.agent.retry.timeout.
    openrouter_connect_timeout_seconds: float = 10.0
    # Cap on each tool result's `data` as sent back to the model. Normal
    # results are far below it (search ~3k chars, profile ~1-15k); it exists
    # for the pathological ones - the full profile of CITIGROUP GLOBAL MARKETS
    # HOLDINGS INC. is ~7.6M chars because it inlines every attached
    # identifier (30,480 of them, nearly all ISINs), which OpenRouter rejects
    # outright ("total text input size exceeds 8 MB"). Over the cap, lists are trimmed shape-preserving
    # with each elision marked, and the model is told - see er.agent.orchestrator.
    max_tool_result_chars: int = 40_000
    verifier: VerifierConfig = VerifierConfig()


class AppConfig(BaseModel):
    gleif: GleifConfig
    sec_13f: Sec13FConfig
    sec_submissions: SecSubmissionsConfig = SecSubmissionsConfig()
    sec_series_class: SecSeriesClassConfig = SecSeriesClassConfig()
    openfigi: OpenFigiConfig = OpenFigiConfig()
    nport: NPortConfig = NPortConfig()
    sec_insiders: SecInsidersConfig = SecInsidersConfig()
    sec_adv: SecAdvConfig = SecAdvConfig()
    companies_house: CompaniesHouseConfig = CompaniesHouseConfig()
    sec_13dg: Sec13DGConfig = Sec13DGConfig()
    ffiec_nic: FfiecNicConfig = FfiecNicConfig()
    serving: ServingConfig = ServingConfig()
    entity: EntityConfig
    opensearch: OpenSearchConfig
    search: SearchConfig
    benchmark: BenchmarkConfig
    matching: MatchingConfig = MatchingConfig()
    family: FamilyConfig = FamilyConfig()
    agent: AgentConfig = AgentConfig()

    @property
    def opensearch_url(self) -> str:
        url = os.environ.get("OPENSEARCH_URL")
        if not url:
            raise RuntimeError(
                "OPENSEARCH_URL is not set. Copy .env.example to .env and fill it in."
            )
        return url

    @property
    def openrouter_api_key(self) -> str:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        return key

    @property
    def openfigi_api_key(self) -> str | None:
        return os.environ.get("OPENFIGI_API_KEY")

    @property
    def a2a_public_url(self) -> str:
        # Where other agents reach the API - advertised in the A2A agent card.
        return os.environ.get("A2A_PUBLIC_URL", "http://localhost:8000")

    @property
    def a2a_api_key(self) -> str | None:
        return os.environ.get("A2A_API_KEY") or None


@lru_cache
def load_config(path: str | Path = REPO_ROOT / "config" / "dev.yaml") -> AppConfig:
    raw = yaml.safe_load(Path(path).read_text())
    cfg = AppConfig.model_validate(raw)
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
        section.raw_dir = REPO_ROOT / section.raw_dir
        section.processed_dir = REPO_ROOT / section.processed_dir
    cfg.entity.processed_dir = REPO_ROOT / cfg.entity.processed_dir
    cfg.entity.review_file = REPO_ROOT / cfg.entity.review_file
    cfg.benchmark.output_dir = REPO_ROOT / cfg.benchmark.output_dir
    return cfg
