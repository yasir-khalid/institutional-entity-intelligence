# Trust architecture: what makes an answer's numbers checkable

This note records how the two research reports on trustworthy financial RAG
(Kepler; "the model writes the sentence, code produces every number") map onto
this repository, what was missing, and what was built. It exists so a later
change doesn't quietly remove the guarantees below - each one is a decision, not
an accident.

## The claim we are backing

An answer is trustworthy here in a specific, narrow sense: every number in it is
a *fact* that was produced by a tool from source data, is addressed back to the
record it came from, and - when it was computed - was computed by a registered
formula from other such facts and is re-checked before it is allowed into an
answer. We do **not** ask a model to rate its own confidence: a model that is
fluent and wrong scores itself highly. Instead the pipeline fails closed on
arithmetic and provenance, and a separate decision model (Jev) is asked only to
judge the finished text against the tool results.

## Report idea -> where it lives (or now lives)

| Report idea | Repo location | State before | State now |
| --- | --- | --- | --- |
| "The model writes the sentence, code produces every number" | `er.agent.facts` (submission gate: the model writes `{{f:fact_id}}`, never a literal number) | Present - literals rejected, placeholders rendered from re-run tools | Unchanged; extended with gates below |
| A fact-reference abstraction (not text the model retypes) | `Fact`, `FactAddress`, `Derivation` (`er.agent.models`) | Present - facts carry a source address (document + locator + field) | Added `Fact.provenance_class` (SOURCE_FACT / DERIVED_FACT) |
| Computed values are first-class and cited, never retyped | `er.knowledge.formulas` + `_derive()` (`er.agent.tools`) | Present - `sum`, `difference`, `percent_change` | Rewritten to be **unit-aware** (`input_units`, `unit_error`, `output_unit`); added `ratio`, `percent_of` |
| Validation gates, not confidence scores | `er.agent.gates` (new) | Absent - only the literal/placeholder gate existed | Added: addressed, dated, derivation_inputs, provenance, units, recomputes - run before an answer may be submitted |
| Conflict / restatement preservation | ingest + serving | Per-source only | XBRL keeps every dated observation and its filing, so a 10-K/A restates a period instead of overwriting it |
| Bitemporal / point-in-time | `Fact.as_of`; XBRL `period_end` vs `filed` | Partial - facts carried `as_of` but no source had a knowledge time | `er.entity.xbrl.known_on()` answers "as filed on or before a date" |
| Provenance back to a document, not just a tool | `FactAddress` + `Evidence.source_uri` | Present | XBRL facts address the exact accession and a companyconcept URL |

## The deterministic preconditions (`er.agent.gates`)

Six pure gates run on the facts and derivations an answer actually used, in a
fixed order. Any failure rejects the submission and hands the model a typed
reason; it never lowers a score and lets the answer through.

1. **addressed** - every fact has source + document_id + locator.
2. **dated** - every measured value (USD, shares, percent, ratio, points) has an
   `as_of`. A bare count is deliberately exempt: it belongs to the response.
3. **derivation_inputs** - every derivation's input facts are present.
4. **provenance** - a fact labelled DERIVED_FACT has a derivation, and a
   derivation's fact is labelled DERIVED_FACT.
5. **units** - a derivation's inputs are unit-compatible and its output unit
   matches the formula's declared output.
6. **recomputes** - every derived value equals the formula applied to its inputs
   (within tolerance).

These are unit-tested in `tests/test_gates.py`, independent of any service.

## New data source: SEC XBRL company facts

Chosen because it is the only source here whose records are *numbers with both a
period and a knowledge time*, keyed by a CIK the platform already attaches to
entities (13F, 13D/G, Forms 3/4/5). That makes it the natural place to prove the
arithmetic gates and point-in-time reads end to end, and it needs **no fuzzy
crosswalk** - the CIK is the join key.

- Ingest: `er.datasources.sec_xbrl` (models/schema/ingest), CLI
  `er.cli.ingest_sec_xbrl`, `make ingest-sec-xbrl`. Fetches
  `companyfacts/CIK{cik}.json` for a bounded issuer set (derived from the 13D/G
  and Forms 3/4/5 tables when `ciks` is empty), filters to the configured
  us-gaap tags, and writes `sec_xbrl_facts.parquet` + `sec_xbrl_issuers.parquet`.
- Serving: indexes `xbrl_facts` (per CIK+concept+unit, all observations) and
  `xbrl_issuers` (name, tickers, former names), published by
  `er.serving.publish`. Runtime reads these, never Parquet.
- Read side: `er.entity.xbrl` (resolve by CIK/ticker/name, point-in-time
  selection, the `Assets = LiabilitiesAndStockholdersEquity` identity).
- Tool: `get_issuer_financials(identifier, id_type, tag, as_of, periods)` in
  `er.agent.tools`, registered in `er.agent.mcp_server`, described in the
  orchestrator system prompt. Derived outputs (a period change, a current ratio,
  a balance residual) travel as facts with a Derivation, so they satisfy the
  gates like any other number.

XBRL is deliberately **not** wired into `er.entity.sources.py`: attaching a CIK
as an entity identifier would claim a crosswalk the source does not perform.

## Verification

- `make test` - 248 unit tests, no live services.
- `make ingest-sec-xbrl` then `python -m er.cli.publish --only xbrl_facts --only
  xbrl_issuers` - live ingest + partial publish.
- `make evaluate-agent` - live hard-path + Jev, cases in
  `config/agent_eval_cases.yaml`.

Latest live run (8 cases): 7/8 pass the hard path; the four XBRL cases all pass
(Jev: verified, verified, partial, verified). The one hard-path failure,
`latest-13f`, is **flaky**, not a regression: re-running the identical question
in isolation returns the expected `sec_13f.latest_period_of_report` and
`sec_13f.reported_security_count` facts, cited, and Jev-verified. A 13F answer
that omits those facts still fails the answered checks, but the model does not
always take the profile path - a case worth stabilising (pin the tool sequence,
or accept the alternate cited phrasing) rather than a numbers-trust failure.

## The chain, made visible in the web UI

The deterministic layer above is only trustworthy if a reader can walk it. Two
surfaces in `web/` render exactly the artifacts the backend already produces -
neither invents a score, and neither re-derives a number:

- `web/src/components/LineageChain.tsx` - per value, Kepler's seven-step chain:
  **source -> stable address -> typed fact -> transformation -> derived proof ->
  rendered number -> citation**, closed by an audit ledger (provenance class,
  unit, fact id, query hash). A computed value embeds its `DerivationDetail`
  inputs at steps 04-05, so every branch ends at a filed row. It reads only
  `Fact`/`Derivation`/`Evidence` from `er.api.schemas`.
- `web/src/components/AuditTrail.tsx` - per answer, Kepler's seven layers
  counted from the payload (sources, addresses, typed facts, formulas, derived
  proofs, rendered numbers, citations) plus the passed/failed
  `er.agent.gates.GateCheck` list, served as `AskResponse.gates`. A failed gate
  renders as a hard failure, never a low score.

The theme is a Linear-derived light palette (Inter with `cv01`+`ss03`, indigo
accent). Linear's brand indigo `#5e6ad2` is deepened to `#4f5ac2` because
`#5e6ad2` fails WCAG AA (white-on-indigo ~4.4:1); the change is required by the
`web/` accessibility test, not cosmetic preference. Verified by
`cd web && npm run test:e2e` (6/6, including the Axe scan) and `npm run build`.
