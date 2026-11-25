# Running it

## Setup

```bash
brew install libpostal   # macOS; ships its own trained model data
CFLAGS="-I/opt/homebrew/include" LDFLAGS="-L/opt/homebrew/lib" uv sync
cp .env.example .env     # fill in OPENSEARCH_URL (OPENROUTER_API_KEY only needed for `er.cli.ask`/the web "Ask" section)
```

## Data pipeline

Once, or after refreshing raw source files:

```bash
make pipeline        # ingest the core GLEIF + 13F sources, then index/validate/benchmark
# or step by step:
make ingest-gleif     # GLEIF XML/CSV -> data/processed/*.parquet (~10-15 min)
make ingest-sec-13f   # every 13F window in config/dev.yaml -> one set of tables (~3 min for four)
make ingest-sec-series-class
make ingest-sec-submissions   # downloads SEC's submissions.zip itself (~1.5 GB, ~6 min)
make ingest-sec-insiders
make ingest-sec-adv           # monthly adv-brochures-*.zip in data/raw/sec_adv (each carries its mapping CSV)
make ingest-companies-house   # BasicCompanyDataAsOneFile-*.zip + PSC snapshot zip in data/raw/companies_house
make ingest-nport             # a quarterly *_nport.zip in data/raw/nport (~1 min)
make ingest-openfigi          # maps 13F CUSIPs; ~3 h without OPENFIGI_API_KEY, minutes with one (cached, resumable)
make ingest-sec-13dg          # structured Schedule 13D/G from EDGAR (~40 min a quarter;
                              # --quarter 2026Q1 / --limit N via python -m er.cli.ingest_sec_13dg)
make ingest-ffiec-nic         # expects the NIC CSV zips in data/raw/ffiec_nic (FFIEC blocks scripted downloads)
make ingest-sec-adv-firms     # Form ADV Part 1A monthly extracts listed in config/dev.yaml (~15 MB each)
make ingest-sec-form-d        # Form D quarterly data sets listed in config/dev.yaml
make ingest-finra-short-volume  # FINRA Reg SHO daily files for the last lookback_days
make ingest-sec-ftd           # SEC fails-to-deliver half-month files listed in config/dev.yaml
make build-knowledge-graph    # typed legal-entity/fund/class/security/owner graph
make index            # entities -> OpenSearch (~20 min)
make validate         # sanity-check the processed tables
make benchmark        # data/benchmark/*.parquet (~1 sec, DuckDB)
make publish          # Parquet -> OpenSearch serving indexes the API reads (~10 min)
```

Raw files some ingests can't fetch themselves are listed in [`data-sources.md`](data-sources.md#getting-the-raw-files).

## Where data lives

Parquet in `data/processed` is the build store: every
ingest, crosswalk and graph build writes it. The API, agent tools and CLIs
read only OpenSearch: the `gleif_entities_v1` search index for name matching,
plus the serving indexes `make publish` builds. Each serving index sits behind
an alias and is swapped in only when fully loaded.

| Alias | One document per | Used for |
|---|---|---|
| `er_entities` | LEI: identity, lineage, identifiers (≤200 per type), GLEIF exceptions, match decisions, cross-source connections | profiles, LEI search, hierarchy names |
| `er_gleif_relationships` | GLEIF relationship | hierarchy traversal, family confirmation |
| `er_13f_filers` | 13F filer (CIK): latest-period summary, top holdings, quarantine and scale flags, LEI link | 13F activity, CUSIP search |
| `er_13f_holdings` | effective information-table row | position history, CUSIP search |
| `er_13dg_ownership` | 13D/G reporting person per filing | beneficial owners |
| `er_nport_funds` | fund series LEI: latest N-PORT report, net assets, top 10 holdings by USD value | fund profiles, agent facts |
| `er_sec_adv_pages` | extracted Form ADV PDF page | brochure full-text search |
| `er_sec_adv_pdfs` | one brochure PDF (base64) | the brochure viewer |
| `er_sec_adv_documents` | Form ADV PDF metadata + source archive member | brochure provenance |
| `er_match_reviews` | human review, written by the API | reviews (`make pull-reviews` copies them back for `build-knowledge-graph`) |
| `er_adv_firms` | adviser (CRD): latest Form ADV Part 1A, AUM history, client types | adviser pages, `get_adviser_profile` |
| `er_form_d_offerings` | Form D filing, with related persons and recipients | raises feed, `search_private_offerings` |
| `er_security_ownership` | CUSIP: 13F holders per period, largest holders with prior-period shares | security pages, `get_security_ownership` |
| `er_short_volume` / `er_fails_to_deliver` | symbol / CUSIP: daily series | security pages, `get_short_activity` |

### Fitting a small cluster

The hosted demo cluster (Aiven free tier) allows 20 shards and 5 are Aiven's
own. Replicas are already 0 everywhere, so the shard count is the limit, not
disk (everything is about 3.5 GB). `config/dev.yaml` therefore:

- packs the small read indexes listed under `serving.packed` into one physical
  index, `er_packed`. Each document keeps its id behind a `<name>:` prefix and a
  `serving_kind` field; `er.serving.store.OpenSearchStore` adds the filter, so
  no reader changes. Serving then takes 4 shards: `er_entities`,
  `er_13f_holdings`, `er_packed` and `er_coverage`.
- sets `serving.keep_previous_generation: false`, so a publish deletes the
  generation it replaced instead of retaining it for `--rollback`.
- builds `gleif_entities_v1` with one shard (`make index` after deleting it).
  Over a slow link the load takes about 12 minutes; if the connection drops,
  run it again - documents are keyed by LEI, so it overwrites, never duplicates.

That is 7 shards live (with `er_investigations` and `er_match_reviews`) and
11 while a publish stages its replacement. On a cluster without the limit,
empty `serving.packed` and set `keep_previous_generation: true` to get one
index per read and rollback back. Switching layout is a normal publish: the
old per-index aliases are dropped in the same alias transaction.

So a deployed API needs `OPENSEARCH_URL` (and `OPENROUTER_API_KEY` for
the agent and its Jev verifier), not the Parquet files or `data/raw`. Rebuild order after new data: ingest →
crosswalk → `make pull-reviews` → `make build-entities` →
`make build-knowledge-graph` → `make publish`. Form ADV brochures are served
from OpenSearch too: publish copies each PDF out of its SEC monthly ZIP into
`er_sec_adv_pdfs`, so only the machine that publishes needs the ZIPs.

### Vercel

Two Vercel projects, both deployed with the CLI:

- **API** (`finance-api`, repo root): `vercel.json` sets the FastAPI preset
  and `app.py` is the entrypoint. `.vercelignore` keeps `data/`, `web/` and
  tests out of the bundle; libpostal is an ingest-only extra, so the build
  never needs the native library. Environment: `OPENSEARCH_URL`,
  `OPENROUTER_API_KEY`, `CORS_ORIGINS` (fixed web origins,
  comma-separated, e.g. the custom domain), `CORS_ORIGIN_REGEX` (origins that
  change per deploy - set to any `*.vercel.app`), `A2A_PUBLIC_URL`,
  `A2A_API_KEY`. Deploy with
  `vercel deploy --prod` from the repo root.
- **Web** (`finance`, `web/`): `NEXT_PUBLIC_API_URL` points at the API and is
  baked in at build time. Deploy with `vercel deploy --prod` from `web/`.

The MCP server runs as a subprocess of the API function, and the research
worker runs inside it while requests keep the instance alive - a page polling
an investigation does that. A run whose instance is frozen mid-way is picked
up again when its lease expires. Runs are capped at the function's 300s.

## Day-to-day usage

```bash
# Raw candidate search - "what does OpenSearch think this could be"
uv run python -m er.cli.search --name "Sampo Oyj" --country FI

# Full resolution - retrieve + score + decide, with evidence
uv run python -m er.cli.match --name "North Rock Capital" --country GB

# The canonical entity profile - identity + every attached identifier (LEI,
# ISIN, SEC CIK, ...) + GLEIF relationships + SEC 13F activity, all one view
uv run python -m er.cli.entity --name "Fred Alger Management" --country US

# Relationship hierarchy - who manages it, what it's a sub-fund of
uv run python -m er.cli.hierarchy --name "Albacore Partners I Master Fund" --country IE --depth 2

# Brand/family discovery - which SET of legal entities make up this institution
uv run python -m er.cli.family --name "Point72"

# Crosswalk SEC 13F filers to GLEIF LEIs, then rebuild the canonical entity layer
make crosswalk-sec-13f
make build-entities

# Ask the agent; every number in the answer is a cited, re-checked fact
# (see agent.md). Requires OPENROUTER_API_KEY (model and Jev) in .env.
uv run python -m er.cli.ask --entity-id 254900ESP1ZKG7UNS007 --question "What is its registration status?"
```

## Reviewing match decisions

Every crosswalk decision is kept with its
score, runner-up, per-feature contributions and matching config fingerprint,
and `make build-knowledge-graph` turns those into citable facts. To overrule
one, add a row to `data/reviews/match_reviews.csv`:

```csv
node_id,lei,outcome,reviewer,reviewed_at,rationale
cik:0001234567,5493001KJTIIGC8Y1R12,REJECTED,ana,2026-10-03,different fund series
```

`CONFIRMED` adds the link and `REJECTED` removes the automated one. The
reviewer's latest outcome for a pair wins. The automated decision is never
edited, so both stay in the facts table.

## Web UI

A Next.js frontend (`web/`) over a thin FastAPI backend
(`src/er/api/`). Search for an entity and open its profile: identifiers and
linked records, how each linked record was matched (score, runner-up,
per-feature points) with a Confirm / Reject review form, ownership and control
(13D/G, FFIEC NIC, PSC, insiders, successors), and latest reported 13F
holdings with a per-holding position history whose formulas unfold to the
filed rows. Agent mode answers with citations, and each source card lists the
exact values it supplied and where they came from. See
[`web/README.md`](../web/README.md). Same core logic, a different view:

```bash
make api                 # FastAPI backend on :8000
cd web && npm run dev    # Next.js dev server
```

The explore pages read the serving indexes `adv_firms`, `form_d_offerings`,
`security_ownership`, `short_volume` and `fails_to_deliver` through
`/api/explore`, `/api/advisers`, `/api/offerings` and `/api/securities`; the
agent reaches the same data through `get_adviser_profile`,
`search_private_offerings`, `get_security_ownership` and `get_short_activity`.

Run `make help` for the full target list. All CLIs support `--country` (ISO
alpha-2 or a common alias like `UK`/`Cayman Islands`) and `--country-mode
soft|strict`.

## Testing

```bash
make test               # unit tests, no live services, ~5s
make evaluate            # scores the matcher against the full benchmark (~7 min,
                         # needs live OpenSearch) -> evaluation_report.json
make evaluate-agent      # runs config/agent_eval_cases.yaml through the live agent
                         # -> data/evaluation/agent-eval.xml (JUnit), needs OPENROUTER_API_KEY
```

`make evaluate-agent` is the deterministic half of a double-entry check on
answers: did the answer submit, does every citation resolve, is every fact it
used cited, did it use the facts the case expects, and (with `--baseline`)
have any of those values moved since an earlier `--save`. Jev's verdict is
reported next to it, and cases where the two disagree are flagged.

`make test` covers every pure function (normalization, matcher features/scoring/
decisions, query construction, benchmark generation, graph traversal, brand-core
extraction) against synthetic fixtures — no live services required.
`run_benchmark` is the integration-level check against real data; a `make test`
pass alone doesn't confirm the live system behaves correctly.
