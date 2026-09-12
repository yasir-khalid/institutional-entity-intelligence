"""CLI: python -m er.cli.index [--recreate] (or `make index`)

Creates/bulk-loads the GLEIF OpenSearch candidate-retrieval index. All index
management logic lives in er.indexing.opensearch_index - this module only
parses arguments, sets up logging, and prints the final index stats.
"""

from __future__ import annotations

import argparse
import logging

from er.config import load_config
from er.indexing.opensearch_index import bulk_load, create_index, get_client

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create/bulk-load the GLEIF OpenSearch index")
    parser.add_argument(
        "--recreate", action="store_true", help="drop and recreate the index first (needed after a mapping change)"
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config()
    client = get_client(cfg)
    create_index(client, cfg, recreate=args.recreate)
    bulk_load(client, cfg)
    stats = client.cat.indices(index=cfg.opensearch.index_name, format="json")
    logger.info("index stats: %s", stats)


if __name__ == "__main__":
    main()
