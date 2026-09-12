"""Brand-core extraction and family-membership classification.

Legal-entity resolution (er.matching) and brand/family discovery (this package) are
deliberately different operations: resolution asks "which ONE legal entity is this?"
and correctly abstains when a query is a brand rather than a legal name; discovery
asks "which SET of legal entities make up this institution?" and should never force
a single winner.

The gap this module fills: `legal_name_core` (er.normalisation.names) only strips
legal-form suffixes (LP/LLC/...) - it deliberately does NOT strip the generic
business words or location qualifiers that separate a brand from its
country-specific legal vehicles, because those matter for legal-entity matching
(a Fund II is not a Fund III) but are exactly the noise that hides a shared brand
identity (Point72 Hong Kong Limited and Point72 Japan Limited share nothing in
`legal_name_core` despite obviously being the same brand). Verified against real
GLEIF data before settling on this approach - see tests/test_brand.py for the
full worked examples (Point72, North Rock Capital, and the near-miss distractors
that must NOT be pulled in: North Park Rock, North Wall Capital, Rolling Rock
Capital, Cedar Rock Capital).
"""

from __future__ import annotations

from er.normalisation.names import normalize_name, strip_legal_suffix

# Generic business words that sit between a brand and its legal suffix. Deliberately
# non-exhaustive (same philosophy as COUNTRY_ALIASES) - cover what actually shows up,
# extend as gaps surface. Real sub-brand words (credit, lending, ...) are NOT here on
# purpose - stripping them would over-merge genuinely distinct business lines.
GENERIC_BUSINESS_TERMS = {
    "capital",
    "management",
    "partners",
    "group",
    "holdings",
    "advisors",
    "advisers",
    "associates",
    "asset",
    "assets",
    "investment",
    "investments",
    "fund",
    "funds",
    "gp",
    "lp",
    "pte",
    "sdn",
    "bhd",
}

# Location/jurisdiction words that show up as a trailing qualifier on a brand's
# country-specific legal vehicles (e.g. "Point72 Hong Kong Limited"). Also
# deliberately non-exhaustive.
LOCATION_TOKENS = {
    "uk",
    "us",
    "usa",
    "eu",
    "hk",
    "sg",
    "jp",
    "ch",
    "de",
    "fr",
    "ie",
    "lu",
    "ky",
    "bvi",
    "je",
    "gg",
    "ae",
    "difc",
    "dubai",
    "london",
    "europe",
    "asia",
    "international",
    "global",
    "america",
    "japan",
    "hong",
    "kong",
    "united",
    "kingdom",
    "states",
    "emirates",
    "arab",
    "cayman",
    "islands",
    "virgin",
    "british",
    "singapore",
    "switzerland",
}

_STRIP_TAIL = GENERIC_BUSINESS_TERMS | LOCATION_TOKENS

# Fallback role heuristic (see plan: entity_category is the clean GLEIF signal but
# isn't in the OpenSearch index today, so this proxies it from fields that are).
_FUND_VEHICLE_KEYWORDS = {"fund", "spc", "trust", "icav"}


def extract_brand_core(name: str) -> str:
    """Strip legal suffix + trailing generic-business/location tokens, iteratively
    (handles e.g. "...(SG) PTE. LTD." where a location token sits before the legal
    suffix - stripping "ltd" first exposes "pte" as newly-trailing, itself stripped
    next, and so on).

    Never strips the last remaining token, even if it's in the stoplist - a brand
    whose own name IS a generic-sounding word or phrase ("Capital Group", "Asset
    Management Inc") must not be hollowed out to an empty string. Verified this was
    a real gap: without the guard, both examples above stripped to "".
    """
    tokens = strip_legal_suffix(normalize_name(name)).split()
    while len(tokens) > 1 and tokens[-1] in _STRIP_TAIL:
        tokens.pop()
        stripped = strip_legal_suffix(" ".join(tokens)).split()
        tokens = stripped if stripped else tokens
    return " ".join(tokens)


def classify_tier(query_brand_core: str, candidate_brand_core: str) -> str | None:
    """HIGH: exact brand-core match. POSSIBLE: candidate's core extends the query's
    core with more tokens (a real sub-brand, e.g. "point72 credit" extends
    "point72"). None: excluded - shares no more than superficial word overlap.
    """
    if not query_brand_core or not candidate_brand_core:
        return None
    if candidate_brand_core == query_brand_core:
        return "high"
    query_tokens = query_brand_core.split()
    candidate_tokens = candidate_brand_core.split()
    if candidate_tokens[: len(query_tokens)] == query_tokens and len(candidate_tokens) > len(query_tokens):
        return "possible"
    return None


def guess_role(candidate: dict) -> str:
    """Fallback proxy for GLEIF's own entity_category=FUND (not yet in the
    OpenSearch index - see plan). Swap to entity_category directly if/when a
    reindex happens for other reasons."""
    if candidate.get("fund_number") is not None or candidate.get("is_master") or candidate.get("is_feeder"):
        return "fund"
    name_tokens = set((candidate.get("legal_name_norm") or "").split())
    if name_tokens & _FUND_VEHICLE_KEYWORDS:
        return "fund"
    return "management"
