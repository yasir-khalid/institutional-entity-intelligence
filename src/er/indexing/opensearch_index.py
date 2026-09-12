"""OpenSearch index management + bulk loading for the GLEIF candidate-retrieval index.

Elasticsearch is used only for candidate retrieval, never as the system of record -
the canonical data lives in Parquet (see er.ingestion.gleif). This module builds a
deliberately narrow retrieval projection: only the fields candidate search needs.
"""

from __future__ import annotations

import logging
import time

import pyarrow.parquet as pq
from opensearchpy import OpenSearch, helpers

from er.config import AppConfig, load_config

logger = logging.getLogger(__name__)

# Fields copied from the Parquet canonical store into the retrieval index.
# Full provenance (dates, aliases raw casing, etc.) stays in Parquet only.
RETRIEVAL_FIELDS = [
    "lei",
    "legal_name",
    "legal_name_norm",
    "legal_name_core",
    "aliases_norm",
    "jurisdiction",
    "registration_id",
    "legal_city",
    "legal_postcode",
    "legal_country",
    "fund_number",
    "is_master",
    "is_feeder",
    "is_offshore",
    "is_domestic",
    "entity_status",
]

MAPPING = {
    "properties": {
        "lei": {"type": "keyword"},
        "legal_name": {"type": "text"},
        "legal_name_norm": {"type": "text"},
        "legal_name_core": {"type": "text"},
        "aliases_norm": {"type": "text"},
        "jurisdiction": {"type": "keyword"},
        "registration_id": {"type": "keyword"},
        "legal_city": {"type": "keyword"},
        "legal_postcode": {"type": "keyword"},
        "legal_country": {"type": "keyword"},
        "fund_number": {"type": "integer"},
        "is_master": {"type": "boolean"},
        "is_feeder": {"type": "boolean"},
        "is_offshore": {"type": "boolean"},
        "is_domestic": {"type": "boolean"},
        "entity_status": {"type": "keyword"},
    }
}


def get_client(cfg: AppConfig) -> OpenSearch:
    return OpenSearch(hosts=[cfg.opensearch_url], use_ssl=cfg.opensearch_url.startswith("https"))


def create_index(client: OpenSearch, cfg: AppConfig, recreate: bool = False) -> None:
    name = cfg.opensearch.index_name
    if client.indices.exists(index=name):
        if not recreate:
            logger.info("index %s already exists, skipping create", name)
            return
        client.indices.delete(index=name)

    body = {
        "settings": {
            "number_of_shards": cfg.opensearch.number_of_shards,
            "number_of_replicas": cfg.opensearch.number_of_replicas,
            "refresh_interval": "1s",
        },
        "mappings": {"dynamic": "strict", **MAPPING},
    }
    client.indices.create(index=name, body=body)
    logger.info("created index %s", name)


def _row_to_doc(row: dict) -> dict:
    return {field: row.get(field) for field in RETRIEVAL_FIELDS}


def bulk_load(client: OpenSearch, cfg: AppConfig) -> int:
    name = cfg.opensearch.index_name
    parquet_path = cfg.gleif.processed_dir / "gleif_entities.parquet"
    pf = pq.ParquetFile(parquet_path)

    client.indices.put_settings(index=name, body={"index": {"refresh_interval": "-1"}})

    started = time.monotonic()
    total = 0
    try:
        for batch in pf.iter_batches(batch_size=cfg.opensearch.bulk_batch_size, columns=RETRIEVAL_FIELDS):
            rows = batch.to_pylist()
            actions = (
                {"_index": name, "_id": row["lei"], "_source": _row_to_doc(row)}
                for row in rows
                if row.get("lei")
            )
            success, errors = helpers.bulk(client, actions, raise_on_error=False)
            total += success
            if errors:
                logger.warning("bulk load: %d errors in batch (showing first)", len(errors))
                logger.warning(errors[0])
            if total % (cfg.opensearch.bulk_batch_size * 20) == 0:
                elapsed = time.monotonic() - started
                logger.info("indexed %d docs (%.0fs, %.0f/s)", total, elapsed, total / elapsed)
    finally:
        client.indices.put_settings(index=name, body={"index": {"refresh_interval": "1s"}})
        client.indices.refresh(index=name)

    logger.info("bulk load complete: %d docs indexed into %s", total, name)
    return total


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    client = get_client(cfg)
    create_index(client, cfg)
    bulk_load(client, cfg)
    stats = client.cat.indices(index=cfg.opensearch.index_name, format="json")
    logger.info("index stats: %s", stats)


if __name__ == "__main__":
    main()
