"""Unit tests for SEC 13F models/row-boolean parsing - no live data needed."""

from er.datasources.sec_13f.ingest import _row_bool
from er.datasources.sec_13f.models import Sec13FFiling, Sec13FHolding


def test_row_bool_parses_sec_y_n_convention():
    assert _row_bool("Y") is True
    assert _row_bool("y") is True
    assert _row_bool("N") is False
    assert _row_bool(None) is False
    assert _row_bool("") is False


def test_filing_model_accepts_minimal_required_fields():
    filing = Sec13FFiling(accession_number="0001-26-000001", cik="0000123456", filer_name="Acme Capital LLC")
    assert filing.is_amendment is False
    assert filing.filer_name_norm == ""


def test_holding_model_accepts_minimal_required_fields():
    holding = Sec13FHolding(accession_number="0001-26-000001", name_of_issuer="ACME CORP")
    assert holding.value is None
