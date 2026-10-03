from __future__ import annotations

import logging
import time

from rich.console import Console

from er.config import load_config
from er.datasources.sec_adv.ingest import run_all


def main() -> None:
    # pypdf warns about every malformed cross-reference and unparsed font in
    # real-world brochures; extraction still succeeds, and failures are kept
    # per document as extraction_error.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    console = Console()
    started = time.monotonic()
    with console.status("Ingesting Form ADV brochures..."):
        counts = run_all(load_config())
    console.print(
        f"Ingested {counts['brochures']:,} brochures, {counts['documents']:,} PDFs, "
        f"and {counts['pages']:,} pages in {time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
