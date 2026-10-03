from __future__ import annotations

import zipfile

from er.config import AppConfig
from er.serving.store import ADV_DOCUMENTS, ADV_PAGES, Store


def load_document(cfg: AppConfig, store: Store, pdf_file_name: str) -> bytes | None:
    if not pdf_file_name or any(char in pdf_file_name for char in ('/', '\\', '\r', '\n', '"')):
        return None
    document = next(iter(store.find(ADV_DOCUMENTS, where={"pdf_file_name": pdf_file_name}, size=1, fields=("source_file",))), None)
    if document is None:
        return None
    archive_name, separator, member = document["source_file"].partition(":")
    archive_path = cfg.sec_adv.raw_dir / archive_name
    if not separator or not archive_path.is_file():
        return None
    with zipfile.ZipFile(archive_path) as archive:
        try:
            return archive.read(member)
        except KeyError:
            return None


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
        left = max(start - 180, 0)
        right = min(start + len(query) + 220, len(text))
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
