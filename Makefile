.DEFAULT_GOAL := help

.PHONY: help ingest-gleif ingest-sec-13f ingest-sec-submissions ingest-sec-series-class ingest-openfigi ingest-nport ingest-sec-insiders ingest-sec-adv ingest-companies-house ingest-sec-13dg ingest-ffiec-nic index validate benchmark pipeline test evaluate crosswalk-sec-13f build-entities build-knowledge-graph evaluate-agent publish pull-reviews

help:
	@echo "Institutional Entity Intelligence - available targets:"
	@echo ""
	@echo "  All CLIs live under er.cli (python -m er.cli.<name>) - a strict separation from"
	@echo "  the core ETL/entity-resolution packages, which never import argparse or rich."
	@echo ""
	@echo "  Data sources (each isolated under src/er/datasources/<source>/):"
	@echo "    make ingest-gleif    Parse raw GLEIF files -> data/processed/*.parquet (~10-15 min)"
	@echo "    make ingest-sec-13f  Parse raw SEC 13F bulk data -> data/processed/*.parquet (~1-2 min)"
	@echo "    make ingest-sec-submissions  Download/parse SEC company submissions metadata"
	@echo "    make ingest-sec-series-class Download/parse SEC fund series and share classes"
	@echo "    make ingest-openfigi Enrich 13F CUSIPs with cached OpenFIGI mappings"
	@echo "    make ingest-nport   Parse the latest downloaded SEC N-PORT quarterly archive"
	@echo "    make ingest-sec-insiders Download/parse SEC Forms 3, 4, and 5"
	@echo "    make ingest-sec-adv Parse downloaded Form ADV brochure maps and PDF archives"
	@echo "    make ingest-companies-house Parse downloaded company and PSC snapshots"
	@echo "    make ingest-sec-13dg Download/parse structured Schedule 13D/G filings (~40 min a quarter)"
	@echo "    make ingest-ffiec-nic Parse downloaded FFIEC NIC bank hierarchy CSVs"
	@echo ""
	@echo "  Shared pipeline (source-agnostic - runs after any/all ingest-* targets):"
	@echo "    make index           Bulk-load GLEIF entities into OpenSearch (~20 min)"
	@echo "    make validate        Data-quality checks over the processed tables"
	@echo "    make benchmark       Regenerate the auto-labeled benchmark (~1s, DuckDB)"
	@echo "    make pipeline        Full pipeline: all ingest-* -> index -> validate -> benchmark"
	@echo ""
	@echo "  Crosswalks (resolve another source's records to a GLEIF LEI, needs live OpenSearch):"
	@echo "    make crosswalk-sec-13f  Resolve unique SEC 13F filers -> GLEIF LEI (~5-10 min, ~10.7k filers)"
	@echo ""
	@echo "  Canonical entity layer (one entity, identifiers from every source attached):"
	@echo "    make build-entities  Rebuild entities.parquet + entity_identifiers.parquet"
	@echo "                         (run after ingest + any crosswalk; add a source in er/entity/sources.py)"
	@echo "    make build-knowledge-graph  Build typed nodes, edges, identifiers, and facts"
	@echo ""
	@echo "  Serving (what the API reads - run after any rebuild above):"
	@echo "    make publish         Load processed Parquet into the OpenSearch serving indexes"
	@echo "    make pull-reviews    Copy API-written match reviews down for build-knowledge-graph"
	@echo ""
	@echo "  Testing:"
	@echo "    make test            Unit test suite (no live services needed, ~5s)"
	@echo "    make evaluate        Score the matcher against the full benchmark (needs live OpenSearch, ~7 min)"
	@echo "    make evaluate-agent  Hard-path checks on live agent answers + JUnit XML (needs OPENROUTER_API_KEY)"
	@echo ""
	@echo "  CLIs take runtime arguments, so they aren't Make targets - run directly, e.g.:"
	@echo "    uv run python -m er.cli.match --name \"...\" --country XX"
	@echo "    uv run python -m er.cli.family --name \"...\""
	@echo "    uv run python -m er.cli.hierarchy --lei ... --depth 2"
	@echo "    uv run python -m er.cli.entity --name \"...\" --country XX"

# --- Data sources ------------------------------------------------------------
# One target per source, each running only that source's own ingest module.
# Isolated by construction: src/er/datasources/<source>/ owns its raw-file
# parsing end to end and never imports another source's code.

ingest-gleif:
	uv run python -m er.cli.ingest_gleif

ingest-sec-13f:
	uv run python -m er.cli.ingest_sec_13f

ingest-sec-submissions:
	uv run python -m er.cli.ingest_sec_submissions

ingest-sec-series-class:
	uv run python -m er.cli.ingest_sec_series_class

ingest-openfigi:
	uv run python -m er.cli.ingest_openfigi

ingest-nport:
	uv run python -m er.cli.ingest_nport

ingest-sec-insiders:
	uv run python -m er.cli.ingest_sec_insiders

ingest-sec-adv:
	uv run python -m er.cli.ingest_sec_adv

ingest-companies-house:
	uv run python -m er.cli.ingest_companies_house

ingest-sec-13dg:
	uv run python -m er.cli.ingest_sec_13dg

ingest-ffiec-nic:
	uv run python -m er.cli.ingest_ffiec_nic

INGEST_TARGETS := ingest-gleif ingest-sec-13f

# --- Shared pipeline (source-agnostic) ---------------------------------------

index:
	uv run python -m er.cli.index

validate:
	uv run python -m er.cli.validate

benchmark:
	uv run python -m er.cli.benchmark

pipeline: $(INGEST_TARGETS) index validate benchmark

# --- Crosswalks (resolve another source's records to a GLEIF LEI) -----------
# Reuses er.matching.matcher.match() unchanged - needs a live, indexed OpenSearch.

crosswalk-sec-13f:
	uv run python -m er.cli.crosswalk_sec_13f

# --- Canonical entity layer ---------------------------------------------------
# Rebuilds entities.parquet + entity_identifiers.parquet from GLEIF plus every
# registered source in er.entity.sources (run after ingest + any crosswalk).

build-entities:
	uv run python -m er.cli.build_entities

build-knowledge-graph:
	uv run python -m er.cli.build_knowledge_graph

publish:
	uv run python -m er.cli.publish

pull-reviews:
	uv run python -m er.cli.pull_reviews

# --- Testing ------------------------------------------------------------------

test:
	uv run pytest

evaluate:
	uv run python -m er.cli.evaluate

evaluate-agent:
	uv run python -m er.cli.evaluate_agent --junit data/evaluation/agent-eval.xml

# --- Web ----------------------------------------------------------------------
# Backend API for the Next.js frontend (web/) - a thin translation layer only,
# see src/er/api/app.py. Run alongside `cd web && npm run dev`.

api:
	uv run uvicorn er.api.app:app --reload --port 8000
