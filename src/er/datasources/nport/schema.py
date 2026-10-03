from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


FUND_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("filing_date", pa.string()),
        ("report_date", pa.string()),
        ("cik", pa.string()),
        ("registrant_name", pa.string()),
        ("registrant_lei", pa.string()),
        ("series_id", pa.string()),
        ("series_name", pa.string()),
        ("series_lei", pa.string()),
        ("total_assets", pa.float64()),
        ("total_liabilities", pa.float64()),
        ("net_assets", pa.float64()),
        *PROVENANCE_FIELDS,
    ]
)

HOLDING_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("holding_id", pa.string()),
        ("issuer_name", pa.string()),
        ("issuer_lei", pa.string()),
        ("issuer_title", pa.string()),
        ("issuer_cusip", pa.string()),
        ("isin", pa.string()),
        ("ticker", pa.string()),
        ("balance", pa.float64()),
        ("unit", pa.string()),
        ("currency_code", pa.string()),
        ("currency_value", pa.float64()),
        ("exchange_rate", pa.float64()),
        ("percentage", pa.float64()),
        ("payoff_profile", pa.string()),
        ("asset_category", pa.string()),
        ("issuer_type", pa.string()),
        ("investment_country", pa.string()),
        ("fair_value_level", pa.string()),
        ("derivative_category", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)
