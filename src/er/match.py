"""CLI: python -m er.match --name "Albacore Partners I Master Fund" --country IE

Unlike er.search (retrieval only - a ranked candidate list), this runs the full
retrieve -> score -> decide pipeline and prints the decision with its evidence.
"""

from __future__ import annotations

import argparse

from er.config import load_config
from er.indexing.opensearch_index import get_client
from er.matching.matcher import match


def main() -> None:
    parser = argparse.ArgumentParser(description="Match a name against GLEIF entities")
    parser.add_argument("--name", required=True)
    parser.add_argument("--country", default=None, help="ISO alpha-2, e.g. IE")
    parser.add_argument("--postcode", default=None)
    parser.add_argument("--city", default=None)
    parser.add_argument("--registration-id", default=None)
    parser.add_argument("--top", type=int, default=5, help="how many candidates to print")
    args = parser.parse_args()

    cfg = load_config()
    client = get_client(cfg)
    result = match(
        client,
        cfg,
        args.name,
        args.country,
        args.postcode,
        args.city,
        args.registration_id,
    )

    print(f"Decision: {result.decision.value}")
    if result.lei:
        print(f"LEI: {result.lei}  score: {result.score:.2f}  gap: {result.gap if result.gap is None else round(result.gap, 2)}")
        print("Evidence:")
        for k, v in sorted(result.evidence.items(), key=lambda kv: -abs(kv[1])):
            print(f"  {k}: {v:+.2f}")
    else:
        print("No confident candidate.")

    print(f"\nTop {min(args.top, len(result.candidates))} candidates:")
    for c in result.candidates[: args.top]:
        print(f"  {c.rank:>2}. {c.legal_name}  LEI: {c.lei}  score: {c.score:.2f}")


if __name__ == "__main__":
    main()
