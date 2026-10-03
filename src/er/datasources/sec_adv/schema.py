from __future__ import annotations

import pyarrow as pa

from er.datasources.common.parquet_writer import PROVENANCE_FIELDS


BROCHURE_SCHEMA = pa.schema(
    [
        ("firm_name", pa.string()),
        ("sec_number", pa.string()),
        ("crd_number", pa.string()),
        ("filing_id", pa.string()),
        ("brochure_name", pa.string()),
        ("brochure_id", pa.string()),
        ("brochure_version", pa.string()),
        ("date_filed", pa.string()),
        ("pdf_file_name", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)

DOCUMENT_SCHEMA = pa.schema(
    [
        ("crd_number", pa.string()),
        ("brochure_id", pa.string()),
        ("pdf_file_name", pa.string()),
        ("content_hash", pa.string()),
        ("page_count", pa.int32()),
        ("extraction_error", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)

PAGE_SCHEMA = pa.schema(
    [
        ("crd_number", pa.string()),
        ("brochure_id", pa.string()),
        ("pdf_file_name", pa.string()),
        ("page_number", pa.int32()),
        ("text", pa.string()),
        ("content_hash", pa.string()),
        *PROVENANCE_FIELDS,
    ]
)
