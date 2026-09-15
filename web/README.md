# Institutional Entity Intelligence - Web UI

A Next.js frontend over the Python entity-resolution engine, via a thin FastAPI
backend (`src/er/api/app.py`, in the repo root). This app owns no
entity-resolution logic itself - it only searches, renders a relationship
tree, and shows a details panel for whatever node is clicked.

## Run it

Two processes, both from the **repo root** unless noted:

```bash
make api                 # FastAPI backend on http://localhost:8000
cd web && npm run dev    # Next.js dev server (picks 3000, or the next free port)
```

Copy `.env.local.example` to `.env.local` first if `NEXT_PUBLIC_API_URL` needs
to point somewhere other than `http://localhost:8000`.

Requires the same live OpenSearch + processed Parquet data the CLIs need (see
the root `README.md`'s Quickstart) - this UI is a view over the same data, not
a separate pipeline.

## How to use it

1. The landing page is search-first, like a search engine homepage - a
   centered search bar and a short "How it works" step flow, nothing else,
   until you actually search. Type a query and pick what it is: **Name**,
   **LEI**, or **Security ID (CUSIP)**.
2. A single unambiguous result (or a confident `AUTO_MATCH`) jumps straight to
   the relationship tree. Otherwise the results take the whole screen as an
   aligned table - name, jurisdiction, LEI, decision - so ten near-identical
   legal names can be compared one column at a time. Every row renders every
   cell, including an empty decision cell, so one badged row never pushes its
   neighbours' columns out of line. The raw retrieval score is
   deliberately not shown: it is an unnormalised BM25 value that means nothing
   to a reader, and the list is already ordered by it.
3. Picking a result opens the workspace: the results collapse to a capped
   strip at the top, and the tree and details panes appear side by side as two
   cards with identical header bars. When the strip has more rows than fit, a
   scroll control appears on its bottom edge and disappears once you reach the
   end.
4. The tree renders as a plain indented list - deliberately not a
   node-and-edge graph - one full-width row per entity with a continuous
   indent guide per level. An upward green arrow marks a parent/manager, a
   downward violet arrow a fund/subsidiary, and a filled indigo dot the root.
   Only the root's direct neighbours are expanded on first load; every row
   with children has a chevron to expand or collapse just that branch. The
   originally-searched entity carries a **QUERY** badge; the selected row is
   filled indigo with a left accent bar.
5. Click any row to load its full profile into the right-hand panel -
   overview, GLEIF lineage timeline, identifiers (click one to expand its
   provenance), and, when the entity resolves as a filer, its latest SEC 13F
   reported holdings. Every loading state shows a skeleton that mirrors the
   real layout's geometry rather than a blank screen or a spinner.

The landing page also carries a floating **Why this matters** button, which
opens a drawer explaining what entity resolution, identifiers, hierarchy,
lineage and provenance each buy you when an agent is consuming this data -
with the measured before/after numbers from `experiments/` rather than
assertions.

## Structure

```
src/
├── app/
│   ├── layout.tsx             # loads Inter + JetBrains Mono as CSS variables
│   ├── globals.css            # Tailwind v4 @theme tokens, .tabular, .scroll-thin
│   └── page.tsx               # the only route - landing search page, then
│                                full-screen results, then tree + details
├── components/
│   ├── ui.tsx                 # shared primitives: SectionLabel, Badge, Mono,
│   │                            Field/FieldGrid - the single source of truth
│   │                            for type scale, badge colours and label style
│   ├── SearchBar.tsx          # query input + Name/LEI/CUSIP segmented control
│   ├── HowItWorks.tsx         # landing-page connected step flow
│   ├── WhyItMatters.tsx       # floating trigger + explainer drawer: why an
│   │                            entity layer matters for agent context
│   ├── ResultsList.tsx        # ambiguous-search result picker (aligned columns)
│   ├── EntityTreeView.tsx     # rebuilds the API tree into a proper spanning
│   │                            tree, renders it as a plain indented list
│   │                            with per-branch collapse state
│   ├── LineageTimeline.tsx    # four-point GLEIF identity timeline
│   ├── ScrollPane.tsx         # height-capped scroller + "more below" control
│   ├── Skeletons.tsx          # loading placeholders that mirror real geometry
│   └── DetailsPanel.tsx       # renders EntityDetail JSON
└── lib/api.ts                 # typed fetch client - mirrors src/er/api/schemas.py exactly
```

## Design system

Deliberately small, so the UI stays coherent without a component library:

- **Type**: one superfamily - IBM Plex Sans for UI, IBM Plex Mono for
  identifiers (LEI, CIK, CUSIP). They were drawn together and share vertical
  metrics, so an identifier sits on the same baseline as the label beside it,
  and Plex was designed for dense technical interfaces rather than being a
  default. Every figure a reader might compare down a column - dates, counts,
  dollar values, IDs - carries `.tabular` (`font-variant-numeric: tabular-nums`)
  so digits line up.
- **Colour**: named tokens in `globals.css`, not per-component slates. Text is
  a four-step ramp - `ink` (headings, values), `ink-muted` (body), `ink-subtle`
  (labels, identifiers), `ink-faint` (decoration only, never text) - and every
  text step clears WCAG AA on `surface`. One accent (indigo) carries selection,
  focus and the query marker; two semantic hues mean direction, not decoration
  (`upward` = parent/manager, `downward` = subsidiary/fund); amber and rose are
  reserved for caveats and errors.
- **Icons**: `lucide-react` throughout - no emoji anywhere in the UI.
- **Loading**: motion lives in exactly one place - a 2px indeterminate line at
  the top of the pane. The placeholders under it never animate and reproduce
  the real geometry column for column (same 44px rows, same jurisdiction /
  identifier / decision widths, same tree indent depths), so a load previews
  the layout that is arriving instead of decorating the wait.
- **Alignment**: the tree and details panes are cards with identical 44px
  header bars, so their frames, headings and content start on the same
  baseline; label/value pairs use one shared `FieldGrid` column width. The
  details pane is fluid (`clamp(25rem, 30vw, 34rem)`) so a wide screen gives it
  real room rather than stranding it at a fixed width beside a mostly-empty
  tree.

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
