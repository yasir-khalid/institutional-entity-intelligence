"""Integration test against the live OpenSearch index. Skipped if the index isn't
populated yet (run er.datasources.gleif.ingest + er.indexing.opensearch_index first)."""

import pytest

from er.config import load_config
from er.indexing.opensearch_index import get_client
from er.retrieval.candidates import search_candidates


@pytest.fixture(scope="module")
def client():
    cfg = load_config()
    c = get_client(cfg)
    if not c.indices.exists(index=cfg.opensearch.index_name):
        pytest.skip("gleif_entities_v1 index not created yet")
    count = c.count(index=cfg.opensearch.index_name)["count"]
    if count == 0:
        pytest.skip("gleif_entities_v1 index is empty")
    return c


def test_search_returns_ranked_candidates(client):
    cfg = load_config()
    results = search_candidates(client, cfg, "Apple Inc")
    assert results
    assert results[0]["rank"] == 1
    assert results == sorted(results, key=lambda r: r["score"], reverse=True)
