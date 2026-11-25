from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


OFFERING_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("file_number", pa.string()),
        ("filing_date", pa.string()),
        ("submission_type", pa.string()),
        ("is_amendment", pa.bool_()),
        ("previous_accession_number", pa.string()),
        ("issuer_cik", pa.string()),
        ("issuer_name", pa.string()),
        ("street1", pa.string()),
        ("city", pa.string()),
        ("state", pa.string()),
        ("state_description", pa.string()),
        ("postal_code", pa.string()),
        ("phone", pa.string()),
        ("jurisdiction", pa.string()),
        ("entity_type", pa.string()),
        ("year_of_incorporation", pa.string()),
        ("co_issuer_count", pa.int64()),
        ("industry_group", pa.string()),
        ("fund_type", pa.string()),
        ("is_fund", pa.bool_()),
        ("is_40_act", pa.bool_()),
        ("revenue_range", pa.string()),
        ("nav_range", pa.string()),
        ("exemptions", pa.list_(pa.string())),
        ("first_sale_date", pa.string()),
        ("first_sale_yet_to_occur", pa.bool_()),
        ("more_than_one_year", pa.bool_()),
        ("minimum_investment", pa.float64()),
        ("total_offering", pa.float64()),
        ("offering_indefinite", pa.bool_()),
        ("total_sold", pa.float64()),
        ("total_remaining", pa.float64()),
        ("investor_count", pa.int64()),
        ("non_accredited_count", pa.int64()),
        ("sales_commission", pa.float64()),
        ("finders_fee", pa.float64()),
        *PROVENANCE_FIELDS,
    ]
)

PERSON_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("person_index", pa.string()),
        ("name", pa.string()),
        ("city", pa.string()),
        ("state", pa.string()),
        ("relationships", pa.list_(pa.string())),
        ("clarification", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)

RECIPIENT_SCHEMA = pa.schema(
    [
        ("accession_number", pa.string()),
        ("recipient_index", pa.string()),
        ("name", pa.string()),
        ("crd_number", pa.string()),
        ("broker_dealer_name", pa.string()),
        ("broker_dealer_crd", pa.string()),
        ("states", pa.list_(pa.string())),
        ("foreign_solicitation", pa.bool_()),
        *PROVENANCE_FIELDS,
    ]
)
