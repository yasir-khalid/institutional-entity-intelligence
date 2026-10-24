# Research workspace and publication operations

The Helix Foundry review informed navigation and lifecycle patterns, not the
institutional model. No Foundry source code was copied. Matching remains
deterministic, typed relationships stay distinct, and every saved answer still
passes through the existing MCP orchestrator, fact submission gate and verifier.

## Workspace

`/` starts a saved investigation; `/research/{id}` resumes it. The server owns
the questions, answers, citations, facts, derivations and bounded progress events.
Closing the browser does not cancel a run. The sidebar remembers its collapsed
state in a cookie; entity-search split sizes are an optional local preference.
The command palette (Cmd/Ctrl-K) navigates pages, finds recent investigations,
and hands entity names to the normal backend search.

`/entities?q=...&type=name|lei|cusip&country=GB` records the search in the URL.
`/entities/{LEI}?tab=overview|relationships|holdings|resolution` is shareable;
browser back/forward and reload retain the tab. Accounting hierarchy is a
plain spanning tree, kept separate from regulatory control and beneficial
ownership. Reported activity retains the 13F and N-PORT coverage caveats.

`/reviews?decision=REVIEW|AUTO_MATCH|UNMATCHED` pages through published SEC 13F
crosswalk decisions, including unmatched records not attached to any LEI.
Reviews append dated evidence; they do not rewrite the machine decision or
immediately mutate graph links. Use `make pull-reviews`, rebuild the knowledge
graph, then publish to apply reviews. Unmatched rows need candidate investigation
before a link can be reviewed. Previously reviewed machine decisions remain in
their original category with review history visible.

`/coverage` reads a single serving document. Source-table row counts, observed
dates, quarantine counts and schemas are calculated at publish time with
DuckDB. Imported does **not** mean every row is linked to a canonical entity.
Missing source/date information is explicit; no source is declared healthy just
because the application knows its name. Schema changes compare the current and
previous publication's source profiles.

## Durable research

`er.workspace.research` stores one revisioned document per investigation in
`{serving.prefix}_investigations`, separate from rebuildable source indexes.
A question and its queued job are one conditional write. Client operation IDs
make a repeated POST safe; a reused ID with a different payload returns 409.
Each API process runs one background worker. OpenSearch sequence numbers and
primary terms protect writes across workers; leases recover abandoned runs.

`workspace` in `config/dev.yaml` controls polling, lease/heartbeat intervals,
maximum interruption attempts, conversation turns and retained events. A graceful
API shutdown requeues its pending question; an ungraceful shutdown is recovered
after lease expiry. Recovery reruns the latest question, not a saved model/tool
instruction checkpoint. Tool operations are read-only; provider charges can
repeat if a process is interrupted. Provider failures become visible failed
jobs and need explicit retry. Stop is persisted immediately; an in-flight
provider call is canceled when the worker next detects loss of ownership.

Developer traces remain opt-in: enable collection before starting a question,
or enable Developer before sending a follow-up. Viewing a previously untraced
run cannot reconstruct its trace. The browser preference survives reloads.

All completed turns remain saved. Only the last four question/answer pairs are
passed as conversational context, matching the existing eight-message API bound.
Every new answer gathers its own evidence. Operational leases/revisions are not
exposed through the public JSON response.
The source rail selects one saved answer at a time; clicking a citation selects
its owning answer. Stable fact IDs are never merged across runs in a way that
could replace an earlier fact's evidence receipt.

This is the existing **shared, unauthenticated localhost workspace**, not a
multi-tenant service. Investigation URLs are identifiers, not authorization.
Do not publish it to the Internet without authentication, user isolation and
request limits. Backups may contain sensitive research questions and trace
payloads; protect them accordingly.

## Backup

```bash
uv run python -m er.cli.research_backup --export data/backups/research-snapshot.parquet
uv run python -m er.cli.research_backup --restore data/backups/research-snapshot.parquet
```

Export refuses an existing destination. Restore validates the versioned backup
and creates only missing investigations, never overwriting existing answers or
running jobs. Active restored jobs are requeued with cleared leases. Export
human reviews separately with `make pull-reviews`. Source-data rebuilds alone
cannot restore runtime-authored research or reviews.

## Publication and rollback

`make publish` stages all serving indexes under one unique generation, including
the decision queue and coverage document. It validates refreshed document counts,
checks that processed input files did not change, and records the generation's
manifest in `data/processed/serving_publications/{generation}.parquet` before
switching all aliases in one OpenSearch transaction. An earlier staging failure
leaves every live alias unchanged and removes staged indexes. A transport failure
during the alias transaction is ambiguous: inspect the active coverage generation
before retrying. Staged indexes are intentionally preserved in that case because
the transaction may have committed.

Publishers sharing the build directory serialize through a file lock. Conditional
alias removal detects a conflicting publisher elsewhere; an explicit single-write-
index constraint prevents competing first publications from making an alias point
at multiple generations. Avoid running ingestion/build commands during publication.
The source retrieval index used for matching is not part of this serving swap.
Atomic alias publication is not per-request snapshot isolation: a long-running
request making several reads across the switch can observe both generations.

```bash
uv run python -m er.cli.publish --rollback GENERATION
```

Rollback validates a complete local manifest, serving prefix, retained index
presence and counts, then atomically restores its aliases. It never touches
investigations or human reviews. Coverage shows the restored snapshot's dates
and generation, not a fabricated new publication timestamp.

`--only` remains an operator escape hatch. It is marked **partial**, does not
promise a consistent full dataset, and cannot be used as a rollback target.
No automatic retention deletion is performed: retained generations consume
disk. Keep the manifests and desired rollback indexes; prune old generations
only after checking they are not active and are no longer needed.

## Verification

```bash
make test
cd web && npm run lint && npm run build
cd web && npx playwright install chromium && npm run test:e2e
```

Python checks cover leases, interruption recovery, idempotency, backups, the
real API/worker lifecycle, publication failure/rollback, coverage dates and
immutable review evidence. Browser checks run real Next/FastAPI routes with a
MemoryStore and substituted MCP/provider boundary, on desktop and mobile:
saved research, reload/follow-up/rename, stop/retry, shared tabs, review writes,
coverage, command palette and mobile sidebar. They include axe accessibility
checks and horizontal-overflow checks, and never query live OpenSearch or a
paid model. The browser harness uses ports 3100 and 8100 and refuses occupied
servers. Set `ER_E2E_WEB_PORT` and `ER_E2E_API_PORT` to choose free alternatives
without stopping another application or reusing its server. Live OpenSearch publication still requires the actual build inputs.
