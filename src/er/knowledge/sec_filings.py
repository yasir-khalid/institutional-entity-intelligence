"""SEC EDGAR full-text search over filing text.

The entity agent already has structured SEC data (13F, 13D/G, N-PORT, XBRL),
but not narrative 10-K/10-Q/8-K text. This module queries EDGAR's public
full-text search, then fetches the matching filing and returns a cited passage
around the query. It does not ingest or index filing text locally; the SEC is
the source of record and the result keeps the filing URL, accession, form and
filing date.

Limits: EDGAR full-text search covers filings from 2001; it is a search index,
not a complete exhibit list. Character offsets are into the extracted text,
not PDF pages. Amended filings can restate an earlier document.
"""

from __future__ import annotations

import html
import re
from typing import Any
from urllib.parse import urlencode

import httpx
from lxml import html as lxml_html

from er.config import AppConfig

FTS_URL = "https://efts.sec.gov/LATEST/search-index"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
FILING_WARNING = (
    "EDGAR full-text search covers filings from 2001 and is a search index, not a "
    "complete exhibit list. Passage offsets are into extracted text, not PDF pages. "
    "An amended filing can restate an earlier document."
)
MAX_DOC_BYTES = 3_000_000


def _text_from_html(raw: str) -> str:
    try:
        doc = lxml_html.fromstring(raw)
        text = doc.text_content()
    except (ValueError, TypeError):
        text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _passage(text: str, query: str, radius: int = 700) -> tuple[str, int, int]:
    q = query.strip().strip('"')
    if not q:
        return text[: radius * 2], 0, min(len(text), radius * 2)
    lower = text.lower()
    pos = lower.find(q.lower())
    if pos < 0:
        terms = [t for t in re.split(r"\W+", q.lower()) if len(t) > 2]
        candidates = [(lower.find(t), lower.count(t), t) for t in terms if lower.find(t) >= 0]
        if candidates:
            # The rarest term is the most informative anchor; "value" appears
            # everywhere, "residual" does not.
            pos = min(candidates, key=lambda item: (item[1], item[0]))[0]
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    return text[start:end], start, end


def _filing_url(cik: str | None, adsh: str | None, file_name: str | None) -> str | None:
    if not adsh:
        return None
    accession = adsh.replace("-", "")
    if cik:
        try:
            cik_int = int(str(cik).lstrip("0"))
        except ValueError:
            cik_int = None
        if cik_int is not None:
            return f"{ARCHIVES}/{cik_int}/{accession}/{file_name or ''}"
    return f"https://www.sec.gov/Archives/edgar/data/{accession}/{file_name or ''}"


def _cik_param(cik: str | None) -> str | None:
    if not cik:
        return None
    raw = str(cik).strip()
    return raw.zfill(10) if raw.isdigit() else raw


def _query_url(query: str, forms: list[str] | None, cik: str | None) -> str:
    params: dict[str, str] = {"q": query}
    if forms:
        params["forms"] = ",".join(forms)
    if cik:
        params["ciks"] = _cik_param(cik) or cik
    return f"{FTS_URL}?{urlencode(params)}"


def search_filings(
    cfg: AppConfig,
    query: str,
    *,
    cik: str | None = None,
    forms: list[str] | None = None,
    limit: int = 5,
    client: httpx.Client | None = None,
) -> dict[str, Any]:
    """Search EDGAR full-text and return cited filing passages."""
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    limit = max(1, min(int(limit), 10))
    forms = [f.strip().upper() for f in (forms or ["10-K", "10-Q", "8-K"]) if f.strip()]
    headers = {"User-Agent": cfg.sec_xbrl.user_agent, "Accept": "application/json, text/html"}
    own_client = client is None
    client = client or httpx.Client(timeout=25, follow_redirects=True)
    try:
        response = client.get(FTS_URL, params={
            "q": query,
            **({"forms": ",".join(forms)} if forms else {}),
            **({"ciks": _cik_param(cik)} if cik else {}),
        }, headers=headers)
        response.raise_for_status()
        payload = response.json()
        raw_hits = (payload.get("hits") or {}).get("hits") or []
        hits: list[dict[str, Any]] = []
        warnings: list[str] = []
        for hit in raw_hits[:limit]:
            src = hit.get("_source") or {}
            ciks = src.get("ciks") or []
            hit_cik = str(ciks[0]) if ciks else (str(cik) if cik else None)
            adsh = src.get("adsh")
            file_name = (hit.get("_id") or "").split(":")[-1] or src.get("file_type")
            url = _filing_url(hit_cik, adsh, file_name)
            passage, start, end = "", 0, 0
            if url and (file_name or "").lower().endswith((".htm", ".html", ".txt")):
                try:
                    doc = client.get(url, headers={"User-Agent": cfg.sec_xbrl.user_agent})
                    doc.raise_for_status()
                    raw = doc.text[:MAX_DOC_BYTES]
                    text = _text_from_html(raw)
                    passage, start, end = _passage(text, query)
                except (httpx.HTTPError, ValueError) as exc:
                    warnings.append(f"Could not read {url}: {type(exc).__name__}")
            hits.append({
                "form": src.get("form"),
                "filing_date": src.get("file_date"),
                "cik": hit_cik,
                "accession_number": adsh,
                "file_name": file_name,
                "file_type": src.get("file_type"),
                "file_description": src.get("file_description"),
                "is_exhibit": str(src.get("file_type") or "").startswith("EX-"),
                "url": url,
                "issuer_names": src.get("display_names") or [],
                "passage": passage,
                "char_start": start,
                "char_end": end,
            })
        if any(h.get("is_exhibit") for h in hits):
            warnings.append(
                "Some hits are exhibits attached to the filing, not the primary 10-K/10-Q/8-K document; "
                "check file_type/file_description before treating a passage as management disclosure."
            )
        return {
            "found": bool(hits),
            "query": query,
            "cik": cik,
            "forms": forms,
            "hits": hits,
            "warnings": [FILING_WARNING, *warnings],
            "source_uri": _query_url(query, forms, cik),
            "result_count": len(hits),
        }
    finally:
        if own_client:
            client.close()
