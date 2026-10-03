from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


COMPANY_SCHEMA = pa.schema(
    [
        ("company_number", pa.string()),
        ("company_name", pa.string()),
        ("company_status", pa.string()),
        ("company_category", pa.string()),
        ("country_of_origin", pa.string()),
        ("incorporation_date", pa.string()),
        ("dissolution_date", pa.string()),
        ("address_line1", pa.string()),
        ("locality", pa.string()),
        ("region", pa.string()),
        ("postal_code", pa.string()),
        ("sic_codes", pa.list_(pa.string())),
        ("previous_names", pa.list_(pa.string())),
        *PROVENANCE_FIELDS,
    ]
)

PSC_SCHEMA = pa.schema(
    [
        ("psc_id", pa.string()),
        ("company_number", pa.string()),
        ("psc_type", pa.string()),
        ("name", pa.string()),
        ("country_of_residence", pa.string()),
        ("nationality", pa.string()),
        ("registration_number", pa.string()),
        ("legal_authority", pa.string()),
        ("legal_form", pa.string()),
        ("natures_of_control", pa.list_(pa.string())),
        ("notified_on", pa.string()),
        ("ceased_on", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)
