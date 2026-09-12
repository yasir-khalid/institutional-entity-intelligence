from __future__ import annotations

import re

from unidecode import unidecode

ENTITY_SUFFIXES = {
    "limited",
    "ltd",
    "llc",
    "lp",
    "llp",
    "inc",
    "incorporated",
    "plc",
    "corp",
    "corporation",
    "co",
    "company",
    "gmbh",
    "sa",
    "sarl",
    "nv",
    "bv",
    "ag",
    "spa",
    "srl",
    "kg",
    "ab",
    "as",
    "oy",
    "aps",
    "sas",
    "sc",
    "scsp",
    "icav",
    "plc.",
}

# Never stripped - these distinguish otherwise-identical fund names.
FUND_STRUCTURE_TOKENS = {
    "master",
    "feeder",
    "offshore",
    "domestic",
    "umbrella",
}

_DROP_RE = re.compile(r"[.'’]")
_SPACE_RE = re.compile(r"[,()\[\]/\\-]")
_WS_RE = re.compile(r"\s+")

_ROMAN_MAP = {
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5,
    "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10,
    "xi": 11, "xii": 12, "xiii": 13, "xiv": 14, "xv": 15,
    "xvi": 16, "xvii": 17, "xviii": 18, "xix": 19, "xx": 20,
}


def normalize_name(name: str) -> str:
    """Lowercase, transliterate, strip punctuation, collapse whitespace."""
    if not name:
        return ""
    text = unidecode(name).lower()
    text = _DROP_RE.sub("", text)
    text = _SPACE_RE.sub(" ", text)
    text = text.replace("&", " and ")
    text = _WS_RE.sub(" ", text).strip()
    return text


def tokenize(name_norm: str) -> list[str]:
    return name_norm.split() if name_norm else []


def strip_legal_suffix(name_norm: str) -> str:
    """Remove a trailing legal-form suffix (already-normalized input)."""
    tokens = tokenize(name_norm)
    while tokens and tokens[-1] in ENTITY_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def extract_fund_structure_tokens(name_norm: str) -> dict[str, bool]:
    tokens = set(tokenize(name_norm))
    return {
        "is_master": "master" in tokens,
        "is_feeder": "feeder" in tokens,
        "is_offshore": "offshore" in tokens,
        "is_domestic": "domestic" in tokens,
    }


def extract_fund_number(name_norm: str) -> int | None:
    """Extract a trailing series/fund number from either roman or arabic numerals.

    "fund ii" -> 2, "fund 2" -> 2, "series iii" -> 3. Returns None if absent.
    """
    tokens = tokenize(name_norm)
    if not tokens:
        return None
    last = tokens[-1]
    # Fund/series numbers are small (I-XX / 1-20ish) - a long trailing digit run is a
    # registration/company number embedded in the name, not a series number.
    if last.isdigit() and len(last) <= 3:
        return int(last)
    if last in _ROMAN_MAP:
        return _ROMAN_MAP[last]
    return None


def build_name_fields(legal_name: str) -> dict:
    """Produce the full set of derived name fields for a GLEIF entity or source record."""
    name_norm = normalize_name(legal_name)
    name_core = strip_legal_suffix(name_norm)
    structure = extract_fund_structure_tokens(name_norm)
    fund_number = extract_fund_number(name_core)
    return {
        "legal_name_norm": name_norm,
        "legal_name_core": name_core,
        "name_tokens": tokenize(name_norm),
        "fund_number": fund_number,
        **structure,
    }
