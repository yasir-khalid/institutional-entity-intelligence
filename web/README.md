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

1. Type a query into the search bar and pick what it is: **Name**, **LEI**, or
   **Security ID (CUSIP)**.
2. A single unambiguous result (or a confident `AUTO_MATCH`) jumps straight to
   the relationship tree; otherwise pick one from the results list.
3. The tree renders as a top-down org chart (rounded-corner cards, auto-laid
   out with `dagre`) - parent/manager cards have a green top border, fund/
   subsidiary cards a purple one. Parents expand one hop deeper than children
   by default (ownership chains up to an ultimate parent are usually short
   and worth seeing in full). Only the root's direct neighbors are expanded
   on first load; every card with children has a **+/−** toggle to expand or
   collapse just that branch, independent of its siblings. The originally-
   searched entity always carries a blue **QUERY** badge; whichever entity is
   currently selected (loaded in the details panel) gets a blue ring - both
   can be the same card, or different once you click into a relative.
4. Click any card to load its full profile - identifiers, GLEIF status, and
   (when resolved as a filer) its latest SEC 13F reported holdings - into the
   right-hand panel. Every loading state (search results, the tree, the
   details panel) shows a skeleton placeholder rather than a blank screen.

## Structure

```
src/
├── app/page.tsx              # the only route - search + tree + details, wired together
├── components/
│   ├── SearchBar.tsx          # query input + Name/LEI/CUSIP toggle
│   ├── ResultsList.tsx        # ambiguous-search result picker
│   ├── TreeGraph.tsx          # flattens TreeNode into a spanning tree, lays it out
│   │                            with dagre, manages per-node collapse state
│   ├── EntityNode.tsx         # the rounded-corner card React Flow renders per entity
│   ├── Skeletons.tsx          # shared loading placeholders (Bar/ResultsSkeleton/TreeSkeleton)
│   └── DetailsPanel.tsx       # renders EntityDetail JSON
└── lib/api.ts                 # typed fetch client - mirrors src/er/api/schemas.py exactly
```

Two earlier versions were tried and dropped: `react-d3-tree` (SVG tree -
cycle-protected duplicate nodes produced overlapping, badly-fonted labels) and
a plain collapsible indented list (correct and simple, but didn't match how
real corporate-structure tools like Moody's Orbis present ownership - a
top-down org chart). The current version (`@xyflow/react` + `dagre`) is
closer to that standard shape while keeping the same per-branch collapse
behavior. It also exposed a real backend bug: rendering every node as its own
DOM element up front meant a hub-heavy real entity's true fan-out (1,111
nodes at the old default) had to be capped much more aggressively than the
CLI ever needed - see `docs/phases.md` Phase 13 for the numbers.
