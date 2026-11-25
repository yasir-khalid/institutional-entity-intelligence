from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


FIRM_SCHEMA = pa.schema(
    [
        ("crd_number", pa.string()),
        ("firm_type", pa.string()),
        ("sec_number", pa.string()),
        ("cik", pa.string()),
        ("lei", pa.string()),
        ("business_name", pa.string()),
        ("legal_name", pa.string()),
        ("street1", pa.string()),
        ("street2", pa.string()),
        ("city", pa.string()),
        ("state", pa.string()),
        ("country", pa.string()),
        ("postal_code", pa.string()),
        ("phone", pa.string()),
        ("website", pa.string()),
        ("sec_status", pa.string()),
        ("latest_filing_date", pa.string()),
        ("legal_form", pa.string()),
        ("employees", pa.int64()),
        ("advisory_employees", pa.int64()),
        ("raum_discretionary", pa.float64()),
        ("raum_non_discretionary", pa.float64()),
        ("raum", pa.float64()),
        ("accounts_discretionary", pa.int64()),
        ("accounts_non_discretionary", pa.int64()),
        ("accounts", pa.int64()),
        ("raum_non_us", pa.float64()),
        ("private_fund_count", pa.int64()),
        ("private_fund_gross_assets", pa.float64()),
        ("hedge_fund_count", pa.int64()),
        ("liquidity_fund_count", pa.int64()),
        ("pe_fund_count", pa.int64()),
        ("real_estate_fund_count", pa.int64()),
        ("securitized_fund_count", pa.int64()),
        ("vc_fund_count", pa.int64()),
        ("other_fund_count", pa.int64()),
        *PROVENANCE_FIELDS,
    ]
)

CLIENT_TYPE_SCHEMA = pa.schema(
    [
        ("crd_number", pa.string()),
        ("client_type", pa.string()),
        ("client_count", pa.int64()),
        ("fewer_than_five", pa.bool_()),
        ("raum", pa.float64()),
        *PROVENANCE_FIELDS,
    ]
)
