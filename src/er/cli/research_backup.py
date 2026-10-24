"""Export or restore saved research; restore never overwrites existing jobs."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from rich.console import Console

from er.config import load_config
from er.serving.store import get_store
from er.workspace.backup import export_investigations, restore_investigations


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--export", type=Path, metavar="FILE.parquet")
    group.add_argument("--restore", type=Path, metavar="FILE.parquet")
    args = parser.parse_args()
    console = Console()
    start = time.perf_counter()
    with console.status("Backing up saved investigations…" if args.export else "Restoring missing investigations…"):
        store = get_store(load_config())
        result = ({"exported": export_investigations(store, args.export)} if args.export
                  else restore_investigations(store, args.restore))
    console.print(result)
    console.print(f"Fetched in {time.perf_counter() - start:.2f}s")


if __name__ == "__main__":
    main()
