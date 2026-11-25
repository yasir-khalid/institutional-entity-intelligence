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
`OPENROUTER_API_KEY` (the model and the Jev verifier)
in the root environment is required for research, but
not for entity/profile/review/coverage reads. Keep this shared, unauthenticated
workspace localhost-only.

## Routes

- `/`: start research. Past investigations are not listed (the site is public);
  each one is reachable only by its `/research/{id}` link.
- `/research/{id}`: saved conversation, sourced answers, progress,
  follow-ups, stop/retry and developer trace. Server persistence survives a
  browser reload; interrupted workers recover via leases.
- `/entities?q=...&type=name|lei|cusip&country=GB`: URL-backed search with an
  adjustable results/inspector split on desktop and stacked panes on mobile.
- `/entities/{LEI}?tab=overview|relationships|holdings|resolution`: shareable
  dossier with identifiers, accounting tree, typed ownership/control,
  latest reported 13F/N-PORT activity and immutable match-decision evidence.
- `/explore`: one query across advisers, private raises and securities.
- `/advisers` and `/advisers/{CRD}`: Form ADV directory and firm profile with
  regulatory AUM, clients, private funds and identifiers.
- `/raises` and `/raises/{accession}`: Form D fund/company raises and a single
  offering with amount sold, offering size, investors and related persons.
- `/securities` and `/securities/{CUSIP|ticker}`: 13F ownership, short sale
  volume and fails-to-deliver, with a largest-holder ledger.
- `/reviews`: paginated SEC 13F crosswalk queue with append-only human reviews.
- `/coverage`: published source counts, observed dates, schemas/quarantine
  information and serving generations.
- `/how-it-works`: the long-form architecture guide.

Reviews take effect in graph links only after `make pull-reviews`, graph
rebuild and publication. An unmatched record is not silently promoted to an LEI.
Reported activity retains its source-specific exclusions and dates. Saved
answers retain citations, addressed facts, formula inputs and verification;
no second agent or matching implementation was added.
Developer trace collection is explicitly opt-in before starting a question or
follow-up. The source rail preserves each answer's own fact/evidence maps.

## Components and visual system

`WorkspaceShell` owns the responsive shadcn sidebar and Cmd/Ctrl-K palette,
and mounts `OnboardingTour`: a three-step dialog shown once per browser (the
`iei-onboarding-v1` localStorage key; clear it to see the tour again). Its
illustrations play once per step and rest on their final frame under reduced
motion.
`EntityWorkspace`, `EntityPage`, `InvestigationView` and `ReviewQueue` own
their route-level interactions. `useResource` cancels stale HTTP reads and
polls only active saved jobs. Research mutations carry retry-safe operation IDs.

The official shadcn Radix registry is configured in `components.json`;
primitives live in `src/components/ui/`. Existing domain-specific presentation
(`EntityProfile`, `EntityTreeView`, `EvidenceLayer`, `FactValues`,
`Markdown`, `VerificationBadge` and `DeveloperPanel`) is retained. Charts are
shadcn Chart (Recharts) in `src/components/charts.tsx`, coloured by the
`--chart-*` tokens in `globals.css`; generative answer blocks are parsed as
OpenUI Lang but drawn by the same components (`src/lib/openui/library.tsx`).

The visual system is the **default shadcn/ui theme** on a neutral light
palette: a near-white canvas, white cards, zinc borders, near-black primary
actions and normal sentence-case labels. The only accent is a single muted
violet, used for links, focus rings and the first chart series; data deltas use
the conventional green/red. This follows the monochrome discipline of the Warp
reference (`styles.refero.design/style/d4c51049-58eb-404a-9fcb-f195928b1c99`)
without inventing a new visual language: the components keep their standard
shadcn radii, sizes and variants. Inter is the UI face and Geist Mono is used
only for code, payloads and technical identifiers.
`PageHeader` gives every route its eyebrow/title/actions rhythm; the shared
split layouts put a sticky record rail beside the reading column on entity,
adviser, security, offering and research pages.

**A metric carries its methodology, not a separate page.** Every figure that
could be misread is rendered with `MetricCard` (or a `ChartCard` with
`explain={...}`), which puts a small (i) beside the number. It opens
`MetricInfo`, a right-hand sheet with the definition, calculation, filed field,
as-of date, caveats and a link to the public source. A new metric supplies a
`MetricDefinition`; it never links to a standalone "how this was calculated"
route. The sheet is the sidebar pattern, and `FactValues` keeps the
answer-level evidence rail compact by collapsing long fact lists behind a
count.

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
reload/follow-up, stop/retry, entity tabs, reviews, coverage, command
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
