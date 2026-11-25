from __future__ import annotations

import base64

from er.serving.store import ADV_PAGES, ADV_PDFS, Store


def load_document(store: Store, pdf_file_name: str) -> bytes | None:
    document = store.get(ADV_PDFS, pdf_file_name, fields=("content",)) if pdf_file_name else None
    return base64.b64decode(document["content"]) if document else None


def search_pages(store: Store, query: str, crd_number: str | None = None, limit: int = 10) -> list[dict]:
    rows = store.search_text(
        ADV_PAGES,
        query,
        field="text",
        where={"crd_number": crd_number} if crd_number else None,
        sort=(("snapshot_date", "desc"), ("pdf_file_name", "asc"), ("page_number", "asc")),
        size=limit,
    )
    matches = []
    for row in rows:
        text = row["text"]
        start = text.casefold().find(query.casefold())
        if start < 0:
            continue
        # Most of the context comes after the match, so a section heading
        # arrives with the section it introduces.
        left = max(start - 180, 0)
        right = min(start + len(query) + 900, len(text))
        matches.append(
            {
                "crd_number": row["crd_number"],
                "brochure_id": row["brochure_id"],
                "pdf_file_name": row["pdf_file_name"],
                "page_number": row["page_number"],
                "snippet": text[left:right],
                "snippet_start": left,
                "match_start": start,
                "match_end": start + len(query),
                "content_hash": row["content_hash"],
                "source_file": row["source_file"],
                "snapshot_date": row["snapshot_date"],
            }
        )
    return matches
