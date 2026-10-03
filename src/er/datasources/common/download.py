from __future__ import annotations

import hashlib
from pathlib import Path

import httpx


SEC_USER_AGENT = "institutional-entity-intelligence/0.1 research@example.com"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_if_missing(url: str, path: Path, *, user_agent: str = SEC_USER_AGENT) -> Path:
    if path.exists():
        return path

    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    with httpx.stream(
        "GET",
        url,
        headers={"User-Agent": user_agent},
        follow_redirects=True,
        timeout=120,
    ) as response:
        response.raise_for_status()
        with partial.open("wb") as stream:
            for chunk in response.iter_bytes():
                stream.write(chunk)
    partial.replace(path)
    return path
