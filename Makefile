.DEFAULT_GOAL := help

.PHONY: help ingest-gleif index validate benchmark pipeline test evaluate

help:
	@echo "Institutional Entity Intelligence - available targets:"
	@echo ""
	@echo "  Data sources (each isolated under src/er/datasources/<source>/):"
	@echo "    make ingest-gleif    Parse raw GLEIF files -> data/processed/*.parquet (~10-15 min)"
	@echo "    ... add ingest-<source> here as new sources are added (SEC Form ADV, FCA, ...)"
	@echo ""
	@echo "  Shared pipeline (source-agnostic - runs after any/all ingest-* targets):"
	@echo "    make index           Bulk-load GLEIF entities into OpenSearch (~20 min)"
	@echo "    make validate        Data-quality checks over the processed tables"
	@echo "    make benchmark       Regenerate the auto-labeled benchmark (~1s, DuckDB)"
	@echo "    make pipeline        Full pipeline: all ingest-* -> index -> validate -> benchmark"
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

# ingest-sec-adv:
# 	uv run python -m er.datasources.sec_adv.ingest

INGEST_TARGETS := ingest-gleif

# --- Shared pipeline (source-agnostic) ---------------------------------------

index:
	uv run python -m er.indexing.opensearch_index

validate:
	uv run python -m er.validation

benchmark:
	uv run python -m er.benchmark.generate

pipeline: $(INGEST_TARGETS) index validate benchmark

# --- Testing ------------------------------------------------------------------

test:
	uv run pytest

evaluate:
	uv run python -m er.evaluation.run_benchmark
