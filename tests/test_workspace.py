"""Durable job ownership, interruption recovery and portable conversation state."""
import asyncio
import copy

import pytest
from opensearchpy import ConflictError, NotFoundError

from er.config import WorkspaceConfig
from er.serving.store import INVESTIGATIONS, MemoryStore, OpenSearchStore
from er.workspace import research
from er.workspace.backup import export_investigations, restore_investigations


def test_create_is_retry_safe_and_followups_do_not_replace_prior_answers(tmp_path):
    store = MemoryStore()
    cfg = WorkspaceConfig()
    first = research.enqueue(store, cfg, "Who owns Acme?", "request-first", entity_id="LEI1")
    assert research.enqueue(store, cfg, "Who owns Acme?", "request-first", entity_id="LEI1") == first
    with pytest.raises(research.ResearchConflict):
        research.enqueue(store, cfg, "A different question", "request-first", entity_id="LEI1")
    with pytest.raises(research.ResearchConflict):
        research.enqueue(store, cfg, "And its parent?", "request-second", first["id"], "LEI1")

    async def answer(job, on_event):
        await on_event({"type": "tool_result", "evidence_ids": ["ev1"]})
        return {"answer": "Acme Parent [1]", "evidence": {"ev1": {"source": "gleif"}}}

    job = research.claim(store, cfg, "worker-a")
    asyncio.run(research.execute(store, cfg, job, answer))
    saved = research.get_investigation(store, first["id"])
    assert saved["status"] == "succeeded"
    assert saved["turns"][0]["result"]["evidence"]["ev1"]["source"] == "gleif"
    followup = research.enqueue(store, cfg, "And its parent?", "request-second", first["id"], "LEI1")
    assert followup["status"] == "queued"
    assert followup["turns"] == saved["turns"]
    path = tmp_path / "research.parquet"
    assert export_investigations(store, path) == 1
    with pytest.raises(ValueError, match="already exists"):
        export_investigations(store, path)
    restored = MemoryStore()
    assert restore_investigations(restored, path) == {"restored": 1, "skipped_existing": 0}
    research.rename(restored, research.get_investigation(restored, first["id"]), "My research")
    assert restore_investigations(restored, path) == {"restored": 0, "skipped_existing": 1}
    assert research.get_investigation(restored, first["id"])["title"] == "My research"
    assert research.get_investigation(restored, first["id"])["turns"] == saved["turns"]


def test_expired_worker_cannot_complete_a_run_owned_by_its_replacement():
    store = MemoryStore()
    cfg = WorkspaceConfig(max_attempts=2)
    doc = research.enqueue(store, cfg, "Question", "request-first")
    old = research.claim(store, cfg, "worker-a")
    assert research.claim(store, cfg, "worker-b") is None
    store.put(INVESTIGATIONS, doc["id"], {**old, "lease_until": "2000-01-01T00:00:00+00:00"})
    replacement = research.claim(store, cfg, "worker-b")

    async def answer(job, on_event):
        return {"answer": job["lease_owner"]}

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(research.execute(store, cfg, old, answer))
    assert research.get_investigation(store, doc["id"])["lease_owner"] == "worker-b"
    asyncio.run(research.execute(store, cfg, replacement, answer))
    result = research.get_investigation(store, doc["id"])
    assert [turn["result"]["answer"] for turn in result["turns"]] == ["worker-b"]
    assert result["attempts"] == 2


@pytest.mark.parametrize("explicit_stop", [False, True])
def test_shutdown_requeues_but_an_explicit_stop_remains_stopped(explicit_stop):
    async def run():
        store = MemoryStore()
        cfg = WorkspaceConfig()
        doc = research.enqueue(store, cfg, "Question", "request-first")
        entered = asyncio.Event()
        async def runner(job, on_event):
            await on_event({"type": "status", "message": "Reading records"})
            entered.set()
            await asyncio.Event().wait()
        task = asyncio.create_task(research.execute(store, cfg, research.claim(store, cfg, "a"), runner))
        await entered.wait()
        if explicit_stop:
            research.cancel(store, doc["id"])
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        return research.get_investigation(store, doc["id"])

    doc = asyncio.run(run())
    assert doc["status"] == ("canceled" if explicit_stop else "queued")
    assert doc["turns"] == []
    assert doc["lease_owner"] is None


def test_interruption_retries_are_bounded_and_a_failed_question_can_be_retried():
    store = MemoryStore()
    cfg = WorkspaceConfig(max_attempts=1)
    doc = research.enqueue(store, cfg, "Question", "request-first")
    job = research.claim(store, cfg, "a")
    store.put(INVESTIGATIONS, doc["id"], {**job, "lease_until": "2000-01-01T00:00:00+00:00"})
    assert research.claim(store, cfg, "b") is None
    assert research.get_investigation(store, doc["id"])["status"] == "failed"
    assert research.retry(store, doc["id"])["status"] == "queued"
    assert research.claim(store, cfg, "b")["attempts"] == 1


def test_opensearch_conditional_write_rejects_an_interleaving_writer():
    """The adapter must use the storage version, not just compare JSON locally."""
    class Client:
        def __init__(self):
            self.indices = self
            self.document = None
            self.sequence = 0
            self.interrupt = False

        def exists(self, **kwargs):
            return True

        def get(self, **kwargs):
            if self.document is None:
                raise NotFoundError(404, "document_missing_exception", {})
            snapshot = {"_source": copy.deepcopy(self.document), "_seq_no": self.sequence, "_primary_term": 1}
            if self.interrupt:
                self.document = {"revision": 1, "title": "Concurrent winner"}
                self.sequence += 1
            return snapshot

        def index(self, *, body, op_type=None, if_seq_no=None, if_primary_term=None, **kwargs):
            if (op_type == "create" and self.document is not None) or (
                if_seq_no is not None and (if_seq_no != self.sequence or if_primary_term != 1)
            ):
                raise ConflictError(409, "version_conflict_engine_exception", {})
            self.document = copy.deepcopy(body)
            self.sequence += 1

    client = Client()
    store = OpenSearchStore(client, "fixture")
    assert store.compare_and_put(INVESTIGATIONS, "request-first", None, {"revision": 0, "title": "Original"})
    assert not store.compare_and_put(INVESTIGATIONS, "request-first", None, {"revision": 0, "title": "Duplicate"})
    client.interrupt = True
    assert not store.compare_and_put(INVESTIGATIONS, "request-first", 0, {"revision": 1, "title": "Stale writer"})
    assert client.document["title"] == "Concurrent winner"
