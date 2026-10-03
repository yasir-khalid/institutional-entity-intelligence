"""Unit tests for SEC 13F row parsing and filing validation - no live data needed."""

from er.datasources.sec_13f.ingest import _row_bool, validate_summary


def test_row_bool_parses_sec_y_n_convention():
    assert _row_bool("Y") is True
    assert _row_bool("y") is True
    assert _row_bool("N") is False
    assert _row_bool(None) is False
    assert _row_bool("") is False




def test_summary_validation_enforces_totals_units_and_amendment_semantics():
    provenance = {"source_file": "quarter.zip", "snapshot_date": "2026-01-01", "ingested_at": "now"}
    valid = validate_summary(
        accession_number="a",
        filing_date="14-FEB-2026",
        is_amendment=False,
        amendment_type=None,
        declared_entry_total=2,
        observed_entry_total=2,
        declared_value_total=300,
        observed_value_total=300,
        provenance=provenance,
    )
    mismatch = validate_summary(
        accession_number="b",
        filing_date="31-DEC-2022",
        is_amendment=True,
        amendment_type="RESTATEMENT",
        declared_entry_total=2,
        observed_entry_total=1,
        declared_value_total=300,
        observed_value_total=200,
        provenance=provenance,
    )

    assert valid.valid and valid.value_unit == "USD" and valid.amendment_action == "ORIGINAL"
    assert not mismatch.valid
    assert mismatch.value_unit == "USD_THOUSANDS"
    assert mismatch.amendment_action == "REPLACE"
    assert mismatch.errors == ["TABLE_ENTRY_TOTAL_MISMATCH", "TABLE_VALUE_TOTAL_MISMATCH"]
