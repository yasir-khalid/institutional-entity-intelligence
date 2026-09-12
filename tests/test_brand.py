from er.family.brand import classify_tier, extract_brand_core, guess_role

# Every example validated live against real GLEIF data before this module was written.
POINT72_HIGH = [
    "Point72 Asset Management, L.P.",
    "Point72 Capital Management, LLC",
    "POINT72 EUROPE (LONDON) LLP",
    "Point72 Hong Kong Limited",
    "Point72 Japan Limited",
]
POINT72_POSSIBLE = [
    "Point72 Credit, LLC",
    "POINT72 LENDING CORP.",
]

NORTH_ROCK_HIGH = [
    "NORTH ROCK CAPITAL MANAGEMENT, LLC",
    "NORTH ROCK CAPITAL MANAGEMENT (UK) LLP",
    "North Rock Capital Management (HK) Limited",
    "North Rock Capital Management (SG) PTE. LTD.",
    "North Rock Capital Management (DIFC) Limited",
    "NORTH ROCK FUND, LIMITED",
    "North Rock, L.P.",  # bare brand + legal suffix only - correctly HIGH, not POSSIBLE
]
NORTH_ROCK_POSSIBLE = [
    "NORTH ROCK SPC",  # "spc" isn't a generic/location token - stays as an extra token
]
NORTH_ROCK_EXCLUDED = [
    "NORTH PARK ROCK LTD",
    "NORTH WALL CAPITAL LLP",
    "ROLLING ROCK CAPITAL LIMITED",
    "CEDAR ROCK CAPITAL LIMITED",
]


def test_point72_high_confidence_examples_collapse_to_brand():
    for name in POINT72_HIGH:
        assert extract_brand_core(name) == "point72", name


def test_point72_possible_examples_extend_the_brand_core():
    for name in POINT72_POSSIBLE:
        core = extract_brand_core(name)
        assert classify_tier("point72", core) == "possible", (name, core)


def test_north_rock_high_confidence_examples_collapse_to_brand():
    for name in NORTH_ROCK_HIGH:
        assert extract_brand_core(name) == "north rock", name


def test_north_rock_possible_examples_extend_the_brand_core():
    for name in NORTH_ROCK_POSSIBLE:
        core = extract_brand_core(name)
        assert classify_tier("north rock", core) == "possible", (name, core)


def test_north_rock_lookalikes_are_excluded():
    for name in NORTH_ROCK_EXCLUDED:
        core = extract_brand_core(name)
        assert classify_tier("north rock", core) is None, (name, core)


def test_classify_tier_exact_match_is_high():
    assert classify_tier("point72", "point72") == "high"


def test_classify_tier_empty_inputs_return_none():
    assert classify_tier("", "point72") is None
    assert classify_tier("point72", "") is None


def test_extract_brand_core_never_strips_to_empty():
    # A brand whose own name IS a generic-sounding word/phrase (a real firm,
    # "The Capital Group Companies", inspired this) must not be hollowed out to ""
    # just because every one of its tokens happens to be in the stoplist.
    assert extract_brand_core("Capital Group") == "capital"
    assert extract_brand_core("Asset Management Inc") == "asset"


def test_extract_brand_core_handles_location_before_legal_suffix():
    # The tricky case that motivated the iterative strip: "(SG) PTE. LTD." has a
    # location token (pte, arguably) sitting where a naive single-pass strip of
    # only the legal suffix ("ltd") would leave "sg pte" dangling.
    assert extract_brand_core("North Rock Capital Management (SG) PTE. LTD.") == "north rock"


def test_guess_role_fund_via_fund_number():
    assert guess_role({"fund_number": 2, "legal_name_norm": "acme fund ii"}) == "fund"


def test_guess_role_fund_via_master_feeder_flag():
    assert guess_role({"is_master": True, "legal_name_norm": "acme master fund"}) == "fund"


def test_guess_role_fund_via_name_keyword():
    assert guess_role({"legal_name_norm": "north rock spc"}) == "fund"


def test_guess_role_defaults_to_management():
    assert guess_role({"legal_name_norm": "point72 asset management"}) == "management"
