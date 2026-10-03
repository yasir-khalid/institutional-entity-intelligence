from er.datasources.sec_adv.search import search_pages
from er.serving.store import ADV_PAGES, MemoryStore


def test_adv_search_returns_the_published_pdf_page_and_exact_text_offset():
    text = "Item 5\nAssets under management: 125,000,000 dollars.\nItem 6"
    store = MemoryStore(
        {
            ADV_PAGES: {
                "old:6:archive.zip:older.pdf": {
                    "crd_number": "12345",
                    "brochure_id": "788",
                    "pdf_file_name": "older.pdf",
                    "page_number": 6,
                    "text": text,
                    "content_hash": "old",
                    "source_file": "archive.zip:older.pdf",
                    "snapshot_date": "2025-03-31",
                },
                "abc:7:archive.zip:brochure.pdf": {
                    "crd_number": "12345",
                    "brochure_id": "789",
                    "pdf_file_name": "brochure.pdf",
                    "page_number": 7,
                    "text": text,
                    "content_hash": "abc",
                    "source_file": "archive.zip:brochure.pdf",
                    "snapshot_date": "2026-03-31",
                }
            }
        }
    )

    match, older_match = search_pages(store, "125,000,000", crd_number="12345")

    assert match["pdf_file_name"] == "brochure.pdf"
    assert match["page_number"] == 7
    assert text[match["match_start"] : match["match_end"]] == "125,000,000"
    assert older_match["pdf_file_name"] == "older.pdf"
