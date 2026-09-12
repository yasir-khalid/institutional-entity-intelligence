"""Parquet schemas for GLEIF's four raw files. Source-specific - lives here, not in
er.datasources.common, so a schema change in GLEIF's data can never leak into
another source's pipeline.
"""

from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS

ENTITY_SCHEMA = pa.schema(
    [
        ("lei", pa.string()),
        ("legal_name", pa.string()),
        ("legal_name_norm", pa.string()),
        ("legal_name_core", pa.string()),
        ("aliases", pa.list_(pa.string())),
        ("aliases_norm", pa.list_(pa.string())),
        ("entity_status", pa.string()),
        ("entity_category", pa.string()),
        ("jurisdiction", pa.string()),
        ("legal_form_code", pa.string()),
        ("legal_form_other", pa.string()),
        ("registration_authority_id", pa.string()),
        ("registration_id", pa.string()),
        ("registration_id_norm", pa.string()),
        ("registration_status", pa.string()),
        ("legal_address_line1", pa.string()),
        ("legal_city", pa.string()),
        ("legal_region", pa.string()),
        ("legal_postcode", pa.string()),
        ("legal_country", pa.string()),
        ("legal_address_norm", pa.string()),
        ("hq_address_line1", pa.string()),
        ("hq_city", pa.string()),
        ("hq_region", pa.string()),
        ("hq_postcode", pa.string()),
        ("hq_country", pa.string()),
        ("hq_address_norm", pa.string()),
        ("entity_creation_date", pa.string()),
        ("initial_registration_date", pa.string()),
        ("last_update_date", pa.string()),
        ("next_renewal_date", pa.string()),
        ("name_tokens", pa.list_(pa.string())),
        ("postcode_prefix", pa.string()),
        ("fund_number", pa.int32()),
        ("is_master", pa.bool_()),
        ("is_feeder", pa.bool_()),
        ("is_offshore", pa.bool_()),
        ("is_domestic", pa.bool_()),
        *PROVENANCE_FIELDS,
    ]
)

RELATIONSHIP_SCHEMA = pa.schema(
    [
        ("start_node_id", pa.string()),
        ("start_node_id_type", pa.string()),
        ("end_node_id", pa.string()),
        ("end_node_id_type", pa.string()),
        ("relationship_type", pa.string()),
        ("relationship_status", pa.string()),
        ("start_date", pa.string()),
        ("end_date", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)

RELATIONSHIP_EXCEPTION_SCHEMA = pa.schema(
    [
        ("lei", pa.string()),
        ("exception_category", pa.string()),
        ("exception_reason", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)

ISIN_LEI_SCHEMA = pa.schema(
    [
        ("isin", pa.string()),
        ("lei", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)
