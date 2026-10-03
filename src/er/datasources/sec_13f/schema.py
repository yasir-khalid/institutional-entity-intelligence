"""Parquet schemas for SEC Form 13F bulk data. Source-specific - lives here, not in
er.datasources.common, following the same per-source convention as GLEIF.
"""

from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS

FILING_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("filing_date", pa.string()),
        ("submission_type", pa.string()),
        ("cik", pa.string()),
        ("period_of_report", pa.string()),
        ("is_amendment", pa.bool_()),
        ("amendment_no", pa.string()),
        ("amendment_type", pa.string()),
        ("filer_name", pa.string()),
        ("filer_name_norm", pa.string()),
        ("filer_name_core", pa.string()),
        ("filer_street1", pa.string()),
        ("filer_street2", pa.string()),
        ("filer_city", pa.string()),
        ("filer_state_or_country", pa.string()),
        ("filer_zipcode", pa.string()),
        ("report_type", pa.string()),
        ("form13f_file_number", pa.string()),
        ("crd_number", pa.string()),
        ("sec_file_number", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)

HOLDING_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("infotable_sk", pa.string()),
        ("name_of_issuer", pa.string()),
        ("title_of_class", pa.string()),
        ("cusip", pa.string()),
        ("figi", pa.string()),
        ("value", pa.int64()),
        ("shares_or_principal_amount", pa.float64()),
        ("shares_or_principal_type", pa.string()),
        ("put_call", pa.string()),
        ("investment_discretion", pa.string()),
        ("other_manager", pa.string()),
        ("voting_auth_sole", pa.int64()),
        ("voting_auth_shared", pa.int64()),
        ("voting_auth_none", pa.int64()),
        *PROVENANCE_FIELDS,
    ]
)

VALIDATION_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("declared_entry_total", pa.int64()),
        ("observed_entry_total", pa.int64()),
        ("declared_value_total", pa.int64()),
        ("observed_value_total", pa.int64()),
        ("value_unit", pa.string()),
        ("row_count_matches", pa.bool_()),
        ("value_total_matches", pa.bool_()),
        ("amendment_action", pa.string()),
        ("valid", pa.bool_()),
        ("errors", pa.list_(pa.string())),
        *PROVENANCE_FIELDS,
    ]
)

OTHER_MANAGER_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("other_manager_sk", pa.string()),
        ("cik", pa.string()),
        ("form13f_file_number", pa.string()),
        ("crd_number", pa.string()),
        ("sec_file_number", pa.string()),
        ("name", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)
