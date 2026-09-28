"""Shape-preserving size limits for tool payloads.

Used in two places that both need a big payload to fit a budget without
lying about what was left out: er.agent.verifier, which has to fit the tool
results into Jev's input budget, and er.agent.trace, which has to fit them
into a developer trace a browser can render. Measured on real payloads: a
search result is ~3k chars and an entity profile ~2k, but a depth-3
relationship tree is ~1.2M.
"""

from __future__ import annotations

import json
from typing import Any

# How hard to squeeze, in order. Each pass caps how many items any one list in
# the payload may keep; the first pass that fits wins.
SHRINK_PASSES: tuple[int, ...] = (200, 50, 20, 8, 3, 1)
MAX_STRING_CHARS = 2_000


def shrink(value: Any, max_items: int) -> Any:
    """Cap every list in a nested payload to `max_items`, preserving its shape.

    Breadth is what explodes - a hierarchy tree is thousands of *sibling*
    subsidiaries, a handful of levels deep - so capping list length keeps the
    parts an answer actually cites (the top of the tree, the first holdings)
    and sheds the tail. An elision is always replaced by a visible marker: a
    shortened list must never be able to read as a complete one, or the
    verifier would mark a true "no other parents are recorded" as unsupported.
    """
    if isinstance(value, dict):
        return {key: shrink(item, max_items) for key, item in value.items()}
    if isinstance(value, list):
        kept = [shrink(item, max_items) for item in value[:max_items]]
        if len(value) > max_items:
            kept.append(f"… {len(value) - max_items} more items elided to fit the size budget")
        return kept
    if isinstance(value, str) and len(value) > MAX_STRING_CHARS:
        return value[:MAX_STRING_CHARS] + "… (truncated)"
    return value


def fit(value: Any, max_chars: int) -> tuple[Any, bool]:
    """Return `value` shrunk breadth-first until its JSON fits `max_chars`, and
    whether anything was dropped. Returns None (with truncated=True) only if
    even one-item-per-list doesn't fit - the caller decides how to say so."""
    if len(json.dumps(value, default=str)) <= max_chars:
        return value, False
    for max_items in SHRINK_PASSES:
        shrunk = shrink(value, max_items)
        if len(json.dumps(shrunk, default=str)) <= max_chars:
            return shrunk, True
    return None, True
