"""Where the API, agent tools and CLIs read from at runtime. Production reads
OpenSearch (OpenSearchStore); unit tests use MemoryStore, which implements the
same small contract over dicts. Parquet stays the build-time system of record:
`make publish` (er.serving.publish) turns it into these indexes, so dropping
OpenSearch loses only runtime-authored metadata: human reviews (see
`make pull-reviews`) and saved investigations (see `er.cli.research_backup`).

The contract is deliberately narrow - exact-match filters, full-text search,
an OR group, missing fields, sort, collapse - so both implementations stay obviously
equivalent. Anything smarter is computed at publish time, not per request.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from threading import RLock
from typing import Any, Protocol

from opensearchpy import ConflictError, NotFoundError, OpenSearch, RequestError, helpers

from er.config import AppConfig


ENTITIES = "entities"
FILERS = "13f_filers"
HOLDINGS = "13f_holdings"
NPORT_FUNDS = "nport_funds"
FUND_SERIES = "fund_series"
SECURITIES = "securities"
RELATIONSHIPS = "gleif_relationships"
OWNERSHIP = "13dg_ownership"
ADV_DOCUMENTS = "sec_adv_documents"
ADV_PAGES = "sec_adv_pages"
XBRL_FACTS = "xbrl_facts"
XBRL_ISSUERS = "xbrl_issuers"
REVIEWS = "match_reviews"
COVERAGE = "coverage"
DECISIONS = "match_decisions"
INVESTIGATIONS = "investigations"


class Store(Protocol):
    """`fields`, where accepted, limits the returned document to those
    top-level fields - entity documents are large, and most reads need a name."""

    def get(self, index: str, doc_id: str, fields: tuple[str, ...] = ()) -> dict | None: ...

    def mget(self, index: str, ids: list[str], fields: tuple[str, ...] = ()) -> dict[str, dict]: ...

    def find(
        self,
        index: str,
        *,
        where: dict[str, Any] | None = None,
        either: dict[str, Any] | None = None,
        missing: tuple[str, ...] = (),
        sort: tuple[tuple[str, str], ...] = (),
        size: int = 100,
        collapse: str | None = None,
        fields: tuple[str, ...] = (),
    ) -> list[dict]: ...

    def search_text(
        self,
        index: str,
        query: str,
        *,
        field: str,
        where: dict[str, Any] | None = None,
        sort: tuple[tuple[str, str], ...] = (),
        size: int = 100,
        fields: tuple[str, ...] = (),
    ) -> list[dict]: ...

    def put(self, index: str, doc_id: str, doc: dict) -> None: ...

    def scan(self, index: str) -> Iterator[dict]: ...

    def compare_and_put(self, index: str, doc_id: str, revision: int | None, doc: dict) -> bool:
        """Create if absent, or replace only the specified document revision."""
        ...


class MissingIndexError(RuntimeError):
    pass


def _terms(field: str, value: Any) -> dict:
    return {"terms": {field: value}} if isinstance(value, list) else {"term": {field: value}}


class OpenSearchStore:
    def __init__(self, client: OpenSearch, prefix: str):
        self.client = client
        self.prefix = prefix

    def alias(self, index: str) -> str:
        return f"{self.prefix}_{index}"

    def _missing(self, index: str, exc: NotFoundError) -> MissingIndexError | None:
        if getattr(exc, "error", "") == "index_not_found_exception":
            return MissingIndexError(f"OpenSearch index {self.alias(index)} is missing - run `make publish`")
        return None

    def get(self, index: str, doc_id: str, fields: tuple[str, ...] = ()) -> dict | None:
        try:
            return self.client.get(
                index=self.alias(index), id=doc_id, _source_includes=list(fields) if fields else None
            )["_source"]
        except NotFoundError as exc:
            if index == INVESTIGATIONS:
                return None
            if error := self._missing(index, exc):
                raise error from exc
            return None

    def mget(self, index: str, ids: list[str], fields: tuple[str, ...] = ()) -> dict[str, dict]:
        if not ids:
            return {}
        try:
            response = self.client.mget(
                index=self.alias(index),
                body={"ids": list(dict.fromkeys(ids))},
                _source_includes=list(fields) if fields else None,
            )
        except NotFoundError as exc:
            raise self._missing(index, exc) or exc from exc
        return {doc["_id"]: doc["_source"] for doc in response["docs"] if doc.get("found")}

    def find(
        self, index, *, where=None, either=None, missing=(), sort=(), size=100, collapse=None, fields=()
    ) -> list[dict]:
        query: dict[str, Any] = {"filter": [_terms(field, value) for field, value in (where or {}).items()]}
        if either:
            query["should"] = [_terms(field, value) for field, value in either.items()]
            query["minimum_should_match"] = 1
        if missing:
            query["must_not"] = [{"exists": {"field": field}} for field in missing]
        body: dict[str, Any] = {"query": {"bool": query}, "size": size}
        if sort:
            body["sort"] = [{field: {"order": order}} for field, order in sort]
        if collapse:
            body["collapse"] = {"field": collapse}
        if fields:
            body["_source"] = list(fields)
        try:
            response = self.client.search(index=self.alias(index), body=body)
        except NotFoundError as exc:
            if index in (REVIEWS, INVESTIGATIONS, COVERAGE, DECISIONS):
                return []
            raise self._missing(index, exc) or exc from exc
        return [hit["_source"] for hit in response["hits"]["hits"]]

    def search_text(self, index, query, *, field, where=None, sort=(), size=100, fields=()) -> list[dict]:
        body: dict[str, Any] = {
            "query": {
                "bool": {
                    "must": [{"match_phrase": {field: query}}],
                    "filter": [_terms(name, value) for name, value in (where or {}).items()],
                }
            },
            "size": size,
        }
        if sort:
            body["sort"] = [{name: {"order": order}} for name, order in sort]
        if fields:
            body["_source"] = list(fields)
        try:
            response = self.client.search(index=self.alias(index), body=body)
        except NotFoundError as exc:
            raise self._missing(index, exc) or exc from exc
        return [hit["_source"] for hit in response["hits"]["hits"]]

    def put(self, index: str, doc_id: str, doc: dict) -> None:
        # Reviews and investigations are authored at runtime and created on first
        # write rather than by `make publish`, which must never overwrite it.
        # Strings are keywords so exact lookups (an LEI, a node id) match - a
        # dynamically mapped text field would be analysed and miss them.
        name = self.alias(index)
        self._ensure_runtime_index(index)
        self.client.index(index=name, id=doc_id, body=doc, refresh="wait_for")

    def _ensure_runtime_index(self, index: str) -> None:
        name = self.alias(index)
        if not self.client.indices.exists(index=name):
            try:
                self.client.indices.create(
                    index=name,
                    body={
                        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                        "mappings": {
                            "properties": {
                                "revision": {"type": "long"},
                                "turns": {"type": "object", "enabled": False},
                                "events": {"type": "object", "enabled": False},
                            },
                            "dynamic_templates": [
                                {"strings": {"match_mapping_type": "string", "mapping": {"type": "keyword"}}}
                            ]
                        },
                    },
                )
            except RequestError as exc:
                if exc.error != "resource_already_exists_exception":
                    raise

    def compare_and_put(self, index: str, doc_id: str, revision: int | None, doc: dict) -> bool:
        self._ensure_runtime_index(index)
        try:
            if revision is None:
                self.client.index(index=self.alias(index), id=doc_id, body=doc,
                                  op_type="create", refresh="wait_for")
            else:
                current = self.client.get(index=self.alias(index), id=doc_id)
                if current["_source"].get("revision") != revision:
                    return False
                self.client.index(index=self.alias(index), id=doc_id, body=doc,
                                  if_seq_no=current["_seq_no"], if_primary_term=current["_primary_term"],
                                  refresh="wait_for")
            return True
        except (ConflictError, NotFoundError):
            return False

    def scan(self, index: str) -> Iterator[dict]:
        try:
            for hit in helpers.scan(self.client, index=self.alias(index), query={"query": {"match_all": {}}}):
                yield hit["_source"]
        except NotFoundError:
            return


def _only(doc: dict, fields: tuple[str, ...]) -> dict:
    return {field: doc[field] for field in fields if field in doc} if fields else doc


class MemoryStore:
    """The same contract over in-process dicts - {index: {doc_id: doc}}."""

    def __init__(self, indexes: dict[str, dict[str, dict]] | None = None):
        self.indexes = {name: dict(docs) for name, docs in (indexes or {}).items()}
        self._write_lock = RLock()

    def get(self, index: str, doc_id: str, fields: tuple[str, ...] = ()) -> dict | None:
        with self._write_lock:
            doc = self.indexes.get(index, {}).get(doc_id)
        return _only(doc, fields) if doc is not None else None

    def _documents(self, index: str) -> list[dict]:
        with self._write_lock:
            return list(self.indexes.get(index, {}).values())

    def mget(self, index: str, ids: list[str], fields: tuple[str, ...] = ()) -> dict[str, dict]:
        docs = self.indexes.get(index, {})
        return {doc_id: _only(docs[doc_id], fields) for doc_id in ids if doc_id in docs}

    def find(
        self, index, *, where=None, either=None, missing=(), sort=(), size=100, collapse=None, fields=()
    ) -> list[dict]:
        def matches(doc: dict, field: str, value: Any) -> bool:
            # A term query on an array field matches any element, as in OpenSearch.
            present = doc.get(field)
            candidates = present if isinstance(present, list) else [present]
            wanted = value if isinstance(value, list) else [value]
            return any(candidate in wanted for candidate in candidates)

        hits = [
            doc
            for doc in self._documents(index)
            if all(matches(doc, field, value) for field, value in (where or {}).items())
            and (not either or any(matches(doc, field, value) for field, value in either.items()))
            and all(doc.get(field) is None for field in missing)
        ]
        # Sorted key by key, last first; documents without the field go last
        # in either direction, as in OpenSearch.
        for field, order in reversed(sort):
            present = sorted(
                (doc for doc in hits if doc.get(field) is not None),
                key=lambda doc: doc[field],
                reverse=order == "desc",
            )
            hits = present + [doc for doc in hits if doc.get(field) is None]
        if collapse:
            first: dict[Any, dict] = {}
            for doc in hits:
                first.setdefault(doc.get(collapse), doc)
            hits = list(first.values())
        return [_only(doc, fields) for doc in hits[:size]]

    def search_text(self, index, query, *, field, where=None, sort=(), size=100, fields=()) -> list[dict]:
        needle = query.casefold()
        hits = [
            doc
            for doc in self._documents(index)
            if needle in str(doc.get(field) or "").casefold()
            and all(doc.get(name) == value for name, value in (where or {}).items())
        ]
        for name, order in reversed(sort):
            present = sorted(
                (doc for doc in hits if doc.get(name) is not None),
                key=lambda doc: doc[name],
                reverse=order == "desc",
            )
            hits = present + [doc for doc in hits if doc.get(name) is None]
        return [_only(doc, fields) for doc in hits[:size]]

    def put(self, index: str, doc_id: str, doc: dict) -> None:
        with self._write_lock:
            self.indexes.setdefault(index, {})[doc_id] = doc

    def scan(self, index: str) -> Iterator[dict]:
        yield from self._documents(index)

    def compare_and_put(self, index: str, doc_id: str, revision: int | None, doc: dict) -> bool:
        with self._write_lock:
            current = self.get(index, doc_id)
            if (revision is None and current is not None) or (revision is not None and (
                current is None or current.get("revision") != revision
            )):
                return False
            self.put(index, doc_id, doc)
            return True


@lru_cache
def _cached_store(url: str, prefix: str) -> OpenSearchStore:
    from er.indexing.opensearch_index import get_client_for

    return OpenSearchStore(get_client_for(url), prefix)


def get_store(cfg: AppConfig) -> OpenSearchStore:
    return _cached_store(cfg.opensearch_url, cfg.serving.prefix)
