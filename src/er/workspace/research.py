"""Saved investigations and durable read-only research jobs.

One versioned document owns a conversation and its pending run, so enqueuing
a question cannot save half a job. Leases and conditional writes prevent two
API workers from completing the same run. The runner is supplied by the API
and uses its existing MCP agent path; this module never performs matching.
"""
from __future__ import annotations

import asyncio
import copy
import logging
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from er.config import WorkspaceConfig
from er.serving.store import INVESTIGATIONS, Store

logger = logging.getLogger(__name__)
ACTIVE = ("queued", "running")


class ResearchConflict(ValueError):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def deadline(seconds: float) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def get_investigation(store: Store, investigation_id: str) -> dict:
    doc = store.get(INVESTIGATIONS, investigation_id)
    if doc is None:
        raise KeyError(investigation_id)
    return copy.deepcopy(doc)


def list_investigations(store: Store, limit: int = 50, offset: int = 0) -> list[dict]:
    return store.find(
        INVESTIGATIONS, sort=(("updated_at", "desc"),), size=offset + limit,
        fields=("id", "title", "entity_id", "status", "updated_at", "created_at"))[offset:]


def _save(store: Store, doc: dict, **changes) -> dict:
    updated = {**doc, **changes, "revision": doc["revision"] + 1, "updated_at": now()}
    if not store.compare_and_put(INVESTIGATIONS, doc["id"], doc["revision"], updated):
        raise ResearchConflict("This investigation changed. Refresh before trying again.")
    return updated


def enqueue(store: Store, cfg: WorkspaceConfig, question: str, request_id: str,
            investigation_id: str | None = None, entity_id: str | None = None, trace: bool = False) -> dict:
    question = question.strip()
    if not question:
        raise ValueError("Enter a research question.")
    if investigation_id is None:
        # A client-generated operation ID also makes creation retry-safe.
        investigation_id = request_id
        doc = store.get(INVESTIGATIONS, investigation_id)
        if doc is None:
            doc = {"id": investigation_id, "title": question[:120], "entity_id": entity_id,
                   "created_at": now(), "updated_at": now(), "revision": 0,
                   "status": "queued", "attempts": 0, "request_id": request_id,
                   "question": question, "trace": trace, "events": [], "error": None,
                   "lease_owner": None, "lease_until": None, "turns": []}
            if store.compare_and_put(INVESTIGATIONS, investigation_id, None, doc):
                return doc
            doc = get_investigation(store, investigation_id)
    else:
        doc = get_investigation(store, investigation_id)
    if doc.get("request_id") == request_id:
        if doc["question"] != question or doc.get("entity_id") != entity_id or doc.get("trace", False) != trace:
            raise ResearchConflict("This operation ID was already used for another question.")
        return doc
    if doc["status"] in ACTIVE or doc["status"] in ("failed", "canceled"):
        raise ResearchConflict("Finish or retry the current question before adding a follow-up.")
    if len(doc["turns"]) >= cfg.max_turns:
        raise ResearchConflict("This investigation is full. Start a new investigation.")
    if entity_id != doc.get("entity_id"):
        raise ResearchConflict("A follow-up must keep the investigation's entity context.")
    return _save(store, doc, status="queued", attempts=0, request_id=request_id,
                 question=question, trace=trace, events=[], error=None, lease_owner=None, lease_until=None)


def retry(store: Store, investigation_id: str) -> dict:
    doc = get_investigation(store, investigation_id)
    if doc["status"] not in ("failed", "canceled"):
        raise ResearchConflict("Only failed or stopped research can be retried.")
    return _save(store, doc, status="queued", attempts=0, error=None, events=[],
                 lease_owner=None, lease_until=None)


def rename(store: Store, doc: dict, title: str) -> dict:
    if not title.strip():
        raise ValueError("Enter an investigation title.")
    return _save(store, doc, title=title.strip())


def cancel(store: Store, investigation_id: str) -> dict:
    doc = get_investigation(store, investigation_id)
    if doc["status"] not in ACTIVE:
        raise ResearchConflict("This investigation has no running question.")
    return _save(store, doc, status="canceled", error=None, lease_owner=None, lease_until=None)


def claim(store: Store, cfg: WorkspaceConfig, owner: str) -> dict | None:
    candidates = store.find(INVESTIGATIONS, where={"status": list(ACTIVE)},
                            sort=(("updated_at", "asc"),), size=100)
    for candidate in candidates:
        doc = get_investigation(store, candidate["id"])
        if doc["status"] not in ACTIVE:
            continue
        if doc["status"] == "running" and (doc.get("lease_until") or "") > now():
            continue
        try:
            if doc["attempts"] >= cfg.max_attempts:
                _save(store, doc, status="failed", error="Research stopped after repeated worker interruptions. Retry when ready.",
                      lease_owner=None, lease_until=None)
                continue
            return _save(store, doc, status="running", attempts=doc["attempts"] + 1,
                         lease_owner=owner, lease_until=deadline(cfg.lease_seconds),
                         events=[], error=None)
        except ResearchConflict:
            continue
    return None


Runner = Callable[[dict, Callable[[dict], Awaitable[None]]], Awaitable[dict]]


async def execute(store: Store, cfg: WorkspaceConfig, job: dict, runner: Runner) -> None:
    """Persist progress and completion only while this run owns its lease."""
    lock = asyncio.Lock()
    owner = job["lease_owner"]

    def owned_update(changes: Callable[[dict], dict]) -> dict:
        # Rename/stop requests share the same CAS document. Retry an ordinary
        # revision race, but never write after another run acquires ownership.
        for _ in range(5):
            doc = get_investigation(store, job["id"])
            if doc["status"] != "running" or doc.get("lease_owner") != owner:
                raise asyncio.CancelledError
            try:
                return _save(store, doc, **changes(doc))
            except ResearchConflict:
                continue
        raise ResearchConflict("Investigation is being updated too frequently. Retry the question.")

    async def update(**changes) -> dict:
        async with lock:
            return await asyncio.to_thread(owned_update, lambda _: changes)

    async def on_event(event: dict) -> None:
        async with lock:
            await asyncio.to_thread(owned_update, lambda doc: {
                "events": (doc["events"] + [event])[-cfg.max_events:],
                "lease_until": deadline(cfg.lease_seconds)})

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(cfg.heartbeat_seconds)
            await update(lease_until=deadline(cfg.lease_seconds))

    task = asyncio.create_task(runner(job, on_event))
    pulse = asyncio.create_task(heartbeat())
    try:
        done, _ = await asyncio.wait((task, pulse), return_when=asyncio.FIRST_COMPLETED)
        if pulse in done:
            await pulse
        result = await task
        await update(status="succeeded", turns=job["turns"] + [
            {"question": job["question"], "result": result, "completed_at": now()}],
            lease_owner=None, lease_until=None, error=None)
    except asyncio.CancelledError:
        # Explicit stop has already changed the status. A shutdown releases only
        # this worker's lease, allowing a replacement to retry immediately.
        try:
            await update(status="queued", lease_owner=None, lease_until=None)
        except (asyncio.CancelledError, ResearchConflict):
            pass
        raise
    except Exception as exc:
        logger.exception("Saved research failed")
        try:
            await update(status="failed", error=str(exc) or type(exc).__name__,
                         lease_owner=None, lease_until=None)
        except (asyncio.CancelledError, ResearchConflict):
            pass
    finally:
        task.cancel()
        pulse.cancel()
        await asyncio.gather(task, pulse, return_exceptions=True)


async def worker(store_factory: Callable[[], Store], cfg: WorkspaceConfig, runner: Runner) -> None:
    owner = uuid.uuid4().hex
    while True:
        try:
            store = store_factory()
            job = await asyncio.to_thread(claim, store, cfg, owner)
            if job:
                try:
                    await execute(store, cfg, job, runner)
                except asyncio.CancelledError:
                    if asyncio.current_task().cancelling():
                        raise
            else:
                await asyncio.sleep(cfg.poll_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Research worker cannot reach its store; retrying")
            await asyncio.sleep(cfg.poll_seconds)
