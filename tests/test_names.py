from er.normalisation.names import (
    build_name_fields,
    extract_fund_number,
    extract_fund_structure_tokens,
    normalize_name,
    strip_legal_suffix,
)


def test_normalize_name_punctuation():
    assert normalize_name("Acme Capital Management, L.P.") == normalize_name(
        "ACME CAPITAL MANAGEMENT LP"
    )


def test_normalize_name_collapses_whitespace_and_case():
    assert normalize_name("  Acme   Global  Fund  ") == "acme global fund"


def test_strip_legal_suffix():
    assert strip_legal_suffix(normalize_name("Acme Capital Management LP")) == "acme capital management"
    assert strip_legal_suffix(normalize_name("Acme Ltd")) == "acme"


def test_strip_legal_suffix_keeps_fund_structure_tokens():
    core = strip_legal_suffix(normalize_name("Acme Global Master Fund II LP"))
    assert "master" in core.split()


def test_fund_number_roman_vs_arabic():
    assert extract_fund_number(normalize_name("Acme Fund II")) == 2
    assert extract_fund_number(normalize_name("Acme Fund 2")) == 2
    assert extract_fund_number(normalize_name("Acme Fund III")) == 3


def test_fund_number_distinguishes_conflicting_series():
    two = extract_fund_number(normalize_name("Acme Fund II"))
    three = extract_fund_number(normalize_name("Acme Fund III"))
    assert two != three


def test_fund_number_absent():
    assert extract_fund_number(normalize_name("Acme Capital Management")) is None


def test_master_feeder_conflict_flags():
    master = extract_fund_structure_tokens(normalize_name("Acme Global Master Fund II LP"))
    feeder = extract_fund_structure_tokens(normalize_name("Acme Global Feeder Fund II LP"))
    assert master["is_master"] and not master["is_feeder"]
    assert feeder["is_feeder"] and not feeder["is_master"]


def test_build_name_fields_end_to_end():
    fields = build_name_fields("ACME GLOBAL OPPORTUNITIES FUND II, L.P.")
    assert fields["legal_name_norm"] == "acme global opportunities fund ii lp"
    assert fields["legal_name_core"] == "acme global opportunities fund ii"
    assert fields["fund_number"] == 2
    assert fields["is_master"] is False
