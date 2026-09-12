"""Isolated per-source ETL pipelines. Each source (er.datasources.<name>) owns its
raw-file parsing and any source-specific quirks (schema, dedup rules, snapshot-date
extraction, ...) end to end, and writes its own Parquet output - nothing here talks
to another source's raw files or code. Common, source-agnostic plumbing (the
streaming batched Parquet writer) lives in er.datasources.common so it's shared
without coupling sources to each other.

This isolation is what makes debugging tractable as more sources are added (SEC
Form ADV, FCA, Companies House, ...): a problem in one source's ETL can never be a
problem in another's, and each can be run/tested/reasoned about independently (see
the Makefile at the repo root for per-source and combined pipeline targets).
"""
