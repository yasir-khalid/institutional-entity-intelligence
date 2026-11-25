"""Vercel entrypoint for the API: Vercel looks for an `app` in a root app.py.

The package lives under src/ and reads config/ relative to the repo, so it
is imported from source rather than as an installed wheel.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from er.api.app import app  # noqa: E402

__all__ = ["app"]
