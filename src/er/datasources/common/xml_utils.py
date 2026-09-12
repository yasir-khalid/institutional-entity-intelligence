"""Generic streaming XML helpers, shared across any XML-based data source.

Source-agnostic - no GLEIF (or any other source's) schema knowledge here. A
future XML-based source (e.g. an FCA or Companies House bulk XML export) would
reuse these directly; anything that needs to know a specific tag/namespace
belongs in that source's own folder instead (see er.datasources.gleif.fields for
the GLEIF-specific equivalent).
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from lxml import etree


def open_zip_member(zip_path: Path):
    """Stream the (single) member of a zip file without extracting it to disk -
    essential for multi-GB source files."""
    zf = zipfile.ZipFile(zip_path)
    (name,) = zf.namelist()
    return zf.open(name)


def clear_element(elem: etree._Element) -> None:
    """Free a fully-processed element (and now-unneeded preceding siblings) during
    streaming iterparse, so memory stays bounded regardless of file size."""
    elem.clear()
    while elem.getprevious() is not None:
        del elem.getparent()[0]


def element_text(elem: etree._Element | None) -> str | None:
    if elem is None:
        return None
    text = elem.text
    return text.strip() if text else None
