"""CLI: python -m er.search --name "Albacore Partners I Master Fund" --country IE"""

from __future__ import annotations

import argparse

from er.config import load_config
from er.indexing.opensearch_index import get_client
from er.retrieval.candidates import search_candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Search GLEIF candidate entities")
    parser.add_argument("--name", required=True)
    parser.add_argument("--country", default=None, help="ISO alpha-2, e.g. IE")
    parser.add_argument("--size", type=int, default=None)
    args = parser.parse_args()

    cfg = load_config()
    client = get_client(cfg)
    results = search_candidates(client, cfg, args.name, args.country, args.size)

    if not results:
        print("No candidates found.")
        return

    for r in results:
        print(
            f"{r['rank']:>2}. {r['legal_name']}\n"
            f"    LEI: {r['lei']}  jurisdiction: {r['jurisdiction']}  "
            f"country: {r['legal_country']}  score: {r['score']:.2f}"
        )


if __name__ == "__main__":
    main()
