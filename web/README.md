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

1. The landing page is search-first, like a search engine homepage - just a
   centered search bar, nothing else, until you actually search for
   something. Type a query and pick what it is: **Name**, **LEI**, or
   **Security ID (CUSIP)**.
2. A single unambiguous result (or a confident `AUTO_MATCH`) jumps straight to
   the relationship tree; otherwise pick one from the results list that
   appears below the search bar.
3. The tree renders as a simple indented list - deliberately not a
   node-and-edge graph - with rounded chip cards connected by plain vertical
   guide lines, closer to a file-explorer tree than a diagramming tool.
   Parent/manager cards have a green left border, fund/subsidiary cards a
   purple one. Only the root's direct neighbors are expanded on first load;
   every card with children has a **▾/▸** toggle to expand or collapse just
   that branch, independent of its siblings. The originally-searched entity
   always carries a blue **QUERY** badge; whichever entity is currently
   selected (loaded in the details panel) gets a blue ring - both can be the
   same card, or different once you click into a relative.
4. Click any card to load its full profile - identifiers, GLEIF status, and
   (when resolved as a filer) its latest SEC 13F reported holdings - into the
   right-hand panel. Every loading state (search results, the tree, the
   details panel) shows a skeleton placeholder rather than a blank screen.

## Structure

```
src/
├── app/page.tsx              # the only route - landing search page, then
│                                search + tree + details once you've searched
├── components/
│   ├── SearchBar.tsx          # query input + Name/LEI/CUSIP toggle
│   ├── ResultsList.tsx        # ambiguous-search result picker
│   ├── EntityTreeView.tsx     # rebuilds the API tree into a proper spanning
│   │                            tree, renders it as a plain indented list
│   │                            with per-branch collapse state
│   ├── Skeletons.tsx          # shared loading placeholders (Bar/ResultsSkeleton/TreeSkeleton)
│   └── DetailsPanel.tsx       # renders EntityDetail JSON
└── lib/api.ts                 # typed fetch client - mirrors src/er/api/schemas.py exactly
```

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
