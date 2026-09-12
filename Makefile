.DEFAULT_GOAL := help

.PHONY: help ingest-gleif ingest-sec-13f index validate benchmark pipeline test evaluate crosswalk-sec-13f build-entities

help:
	@echo "Institutional Entity Intelligence - available targets:"
	@echo ""
	@echo "  Data sources (each isolated under src/er/datasources/<source>/):"
	@echo "    make ingest-gleif    Parse raw GLEIF files -> data/processed/*.parquet (~10-15 min)"
	@echo "    make ingest-sec-13f  Parse raw SEC 13F bulk data -> data/processed/*.parquet (~1-2 min)"
	@echo "    ... add ingest-<source> here as new sources are added (SEC Form ADV, FCA, ...)"
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
	@echo ""
	@echo "  Testing:"
	@echo "    make test            Unit test suite (no live services needed, ~5s)"
	@echo "    make evaluate        Score er.match against the full benchmark (needs live OpenSearch, ~7 min)"
	@echo ""
	@echo "  CLIs take runtime arguments, so they aren't Make targets - run directly, e.g.:"
	@echo "    uv run python -m er.match --name \"...\" --country XX"
	@echo "    uv run python -m er.family --name \"...\""
	@echo "    uv run python -m er.hierarchy --lei ... --depth 2"

# --- Data sources ------------------------------------------------------------
# One target per source, each running only that source's own ingest module.
# Isolated by construction: src/er/datasources/<source>/ owns its raw-file
# parsing end to end and never imports another source's code.

ingest-gleif:
	uv run python -m er.datasources.gleif.ingest

ingest-sec-13f:
	uv run python -m er.datasources.sec_13f.ingest

# ingest-sec-adv:
# 	uv run python -m er.datasources.sec_adv.ingest

INGEST_TARGETS := ingest-gleif ingest-sec-13f

# --- Shared pipeline (source-agnostic) ---------------------------------------

index:
	uv run python -m er.indexing.opensearch_index

validate:
	uv run python -m er.validation

benchmark:
	uv run python -m er.benchmark.generate

pipeline: $(INGEST_TARGETS) index validate benchmark

# --- Crosswalks (resolve another source's records to a GLEIF LEI) -----------
# Reuses er.matching.matcher.match() unchanged - needs a live, indexed OpenSearch.

crosswalk-sec-13f:
	uv run python -m er.crosswalk.sec_13f_to_gleif

# --- Canonical entity layer ---------------------------------------------------
# Rebuilds entities.parquet + entity_identifiers.parquet from GLEIF plus every
# registered source in er.entity.sources (run after ingest + any crosswalk).

build-entities:
	uv run python -m er.entity.build

# --- Testing ------------------------------------------------------------------

test:
	uv run pytest

evaluate:
	uv run python -m er.evaluation.run_benchmark
