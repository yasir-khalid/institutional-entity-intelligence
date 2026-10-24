# Institutional Entity Intelligence — Web workspace

A Next.js frontend over the existing FastAPI entity-resolution and MCP agent
boundaries. The web never reads Parquet or OpenSearch directly.

## Run

```bash
make publish             # root: populate serving, decisions and measured coverage
make api                 # root: FastAPI on localhost:8000
cd web
npm ci
npm run dev
```

Copy `.env.local.example` to `.env.local` if the API URL needs changing.
`OPENROUTER_API_KEY` in the root environment is required for research, but
not for entity/profile/review/coverage reads. Keep this shared, unauthenticated
workspace localhost-only.

## Routes

- `/`: start research and browse saved investigations.
- `/research/{id}`: saved conversation, sourced answers, progress, rename,
  follow-ups, stop/retry and developer trace. Server persistence survives a
  browser reload; interrupted workers recover via leases.
- `/entities?q=...&type=name|lei|cusip&country=GB`: URL-backed search with an
  adjustable results/inspector split on desktop and stacked panes on mobile.
- `/entities/{LEI}?tab=overview|relationships|holdings|resolution`: shareable
  dossier with identifiers, accounting tree, typed ownership/control,
  latest reported 13F/N-PORT activity and immutable match-decision evidence.
- `/reviews`: paginated SEC 13F crosswalk queue with append-only human reviews.
- `/coverage`: published source counts, observed dates, schemas/quarantine
  information and serving generations.
- `/how-it-works`: existing architecture explanation.

Reviews take effect in graph links only after `make pull-reviews`, graph
rebuild and publication. An unmatched record is not silently promoted to an LEI.
Reported activity retains its source-specific exclusions and dates. Saved
answers retain citations, addressed facts, formula inputs and verification;
no second agent or matching implementation was added.
Developer trace collection is explicitly opt-in before starting a question or
follow-up. The source rail preserves each answer's own fact/evidence maps.

## Components and visual system

`WorkspaceShell` owns the responsive shadcn sidebar and Cmd/Ctrl-K palette.
`EntityWorkspace`, `EntityPage`, `InvestigationView` and `ReviewQueue` own
their route-level interactions. `useResource` cancels stale HTTP reads and
polls only active saved jobs. Research mutations carry retry-safe operation IDs.

The official shadcn Radix registry is configured in `components.json`;
primitives live in `src/components/ui/`. Existing domain-specific presentation
(`EntityProfile`, `EntityTreeView`, `EvidenceLayer`, `FactValues`,
`Markdown`, `VerificationBadge` and `DeveloperPanel`) is retained.
The design keeps Geist, tabular figures, square corners, white surfaces,
hairline borders and the blue accent. shadcn roles map onto those semantic
tokens. Secondary workspace/evidence labels meet contrast checks; sidebar
navigation, dialogs and tabs provide keyboard/mobile behavior.

## Checks

```bash
npm run lint
npm run build
npx playwright install chromium
npm run test:e2e
```

Browser tests launch an isolated real FastAPI app with MemoryStore and a
substituted model/MCP boundary on 8100, plus Next on 3100. No paid model or live
OpenSearch writes occur. Desktop/mobile checks exercise saved research,
reload/follow-up/rename, stop/retry, entity tabs, reviews, coverage, command
navigation, axe accessibility and horizontal overflow. Screenshots/traces are
written under gitignored `test-results/`.
If another local application uses the defaults, select free ports without reusing
or stopping its servers:

```bash
ER_E2E_WEB_PORT=3137 ER_E2E_API_PORT=8137 npm run test:e2e
```

The harness still refuses occupied endpoints; port overrides do not enable server reuse.

See [workspace operations](../docs/workspace.md) for publication/rollback,
research backups, recovery semantics and deployment limitations.

## Design history

Three tree visualizations were tried, in order, each replaced for a concrete
reason found by testing against real data (not aesthetic preference alone) -
see `docs/phases.md` Phases 13-15 for the full account:

1. `react-d3-tree` (SVG tree) - cycle-protected duplicate nodes produced
   overlapping, badly-fonted labels.
2. `react-force-graph-2d` (canvas, force-directed/DAG) - became unreadable for
   a real entity with 40+ funds, and `dagMode` rejected perfectly valid GLEIF
   data as an "invalid DAG" whenever a relationship was independently
   rediscovered from both ends.
3. `@xyflow/react` + `dagre` (canvas org chart, auto-layout) - closer to how
   tools like Moody's Orbis present ownership, but still a full graph-diagram
   library (pan/zoom/drag/minimap) for what is, in this product, always
   fundamentally a tree.

The current version drops the graph-diagram paradigm entirely: a plain
indented list (`EntityTreeView.tsx`), no canvas, no diagramming library. It
scales to a large fan-out by simple scroll/collapse and needs no extra
dependency. Every version was built on the same spanning-tree fix (one parent
edge per entity, first-discovery wins) - without it, collapsing one node could
transitively hide unrelated siblings reached through a GLEIF cross-reference
(confirmed live: ~35 of ~47 top-level entities disappeared on one real
entity's tree until this was fixed).
