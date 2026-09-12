from er.matching.features import build_query_record, compute_features


def _candidate(
    legal_name="Acme Global Opportunities Fund II LP",
    legal_name_norm="acme global opportunities fund ii lp",
    legal_name_core="acme global opportunities fund ii",
    legal_country="IE",
    jurisdiction="IE",
    legal_postcode=None,
    legal_city=None,
    registration_id=None,
    fund_number=2,
    is_master=False,
    is_feeder=False,
):
    return {
        "legal_name": legal_name,
        "legal_name_norm": legal_name_norm,
        "legal_name_core": legal_name_core,
        "legal_country": legal_country,
        "jurisdiction": jurisdiction,
        "legal_postcode": legal_postcode,
        "legal_city": legal_city,
        "registration_id": registration_id,
        "fund_number": fund_number,
        "is_master": is_master,
        "is_feeder": is_feeder,
    }


def test_name_exact_true_for_identical_normalized_name():
    q = build_query_record("Acme Global Opportunities Fund II, L.P.")
    c = _candidate()
    f = compute_features(q, c)
    assert f["name_exact"] is True
    assert f["name_core_exact"] is True
    assert f["name_ratio"] == 1.0


def test_name_ratio_perfect_when_query_is_token_subset_of_candidate():
    # token_set_ratio (not plain Levenshtein ratio) is what makes an abbreviated
    # query - missing only the trailing legal-form suffix - score as a perfect
    # name match rather than being penalized for the raw length difference.
    q = build_query_record("Acme Global Opportunities Fund II")
    c = _candidate(legal_name_norm="acme global opportunities fund ii lp")
    f = compute_features(q, c)
    assert f["name_ratio"] == 1.0


def test_name_ratio_partial_for_genuinely_different_names():
    q = build_query_record("Acme Global Opportunities Fund")
    c = _candidate(legal_name_norm="beta international holdings fund")
    f = compute_features(q, c)
    assert 0.0 < f["name_ratio"] < 0.8


def test_name_ratio_favors_true_match_over_same_length_distractor():
    # Regression test for the real North Rock Capital bug: plain fuzz.ratio scored
    # an abbreviated true match WORSE than an unrelated same-length distractor,
    # purely because of raw string length difference. token_set_ratio must not.
    q = build_query_record("North Rock Capital")
    true_match = _candidate(legal_name_norm="north rock capital management uk llp")
    distractor = _candidate(legal_name_norm="north moor capital ltd")
    true_ratio = compute_features(q, true_match)["name_ratio"]
    distractor_ratio = compute_features(q, distractor)["name_ratio"]
    assert true_ratio > distractor_ratio


def test_fund_number_conflict_detected():
    q = build_query_record("Acme Global Opportunities Fund III")
    c = _candidate(fund_number=2)
    f = compute_features(q, c)
    assert f["fund_number_conflict"] is True
    assert f["fund_number_exact"] is False


def test_fund_number_no_conflict_when_either_side_missing():
    q = build_query_record("Acme Capital Management")  # no fund number
    c = _candidate(fund_number=2)
    f = compute_features(q, c)
    assert f["fund_number_conflict"] is False
    assert f["fund_number_exact"] is None


def test_master_feeder_conflict_detected():
    q = build_query_record("Acme Global Credit Master Fund")
    c = _candidate(is_master=False, is_feeder=True, legal_name_core="acme global credit feeder fund")
    f = compute_features(q, c)
    assert f["master_conflict"] is True
    assert f["feeder_conflict"] is True


def test_no_master_feeder_conflict_when_neither_side_claims_it():
    q = build_query_record("Acme Capital Management")
    c = _candidate(is_master=False, is_feeder=False)
    f = compute_features(q, c)
    assert f["master_conflict"] is False
    assert f["feeder_conflict"] is False


def test_country_exact_tolerates_subnational_jurisdiction():
    q = build_query_record("Acme Corp", country="US")
    c = _candidate(legal_country="US-DE", jurisdiction="US-DE")
    f = compute_features(q, c)
    assert f["country_exact"] is True
    # jurisdiction_exact requires an exact string match, so "US" != "US-DE"
    assert f["jurisdiction_exact"] is False


def test_country_exact_none_when_query_has_no_country():
    q = build_query_record("Acme Corp")
    c = _candidate()
    f = compute_features(q, c)
    assert f["country_exact"] is None


def test_postcode_exact_after_normalization():
    # Different raw formatting (spacing), same postcode - build_query_record
    # normalizes the query postcode the same way candidates are normalized at
    # ingestion, so this should match exactly, not just on prefix.
    q = build_query_record("Acme Corp", postcode="EC2N 4AG")
    c = _candidate(legal_postcode="EC2N4AG")
    f = compute_features(q, c)
    assert f["postcode_exact"] is True
    assert f["postcode_prefix_exact"] is True


def test_postcode_prefix_exact_without_full_match():
    # Same outward/prefix code, different full postcode - a real same-district,
    # different-building case.
    q = build_query_record("Acme Corp", postcode="EC2N 4AG")
    c = _candidate(legal_postcode="EC2N9ZZ")
    f = compute_features(q, c)
    assert f["postcode_exact"] is False
    assert f["postcode_prefix_exact"] is True


def test_registration_id_conflict():
    q = build_query_record("Acme Corp", registration_id="12345")
    c = _candidate(registration_id="99999")
    f = compute_features(q, c)
    assert f["registration_id_conflict"] is True
    assert f["registration_id_exact"] is False


def test_registration_id_exact_match():
    q = build_query_record("Acme Corp", registration_id="12345")
    c = _candidate(registration_id="12345")
    f = compute_features(q, c)
    assert f["registration_id_exact"] is True
    assert f["registration_id_conflict"] is False
