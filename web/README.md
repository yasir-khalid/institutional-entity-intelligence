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
3. The tree renders as a collapsible, indented list (like a JSON/file-tree
   viewer) - parents shown with a green dot, funds/subsidiaries with a purple
   one. Parents expand one hop deeper than children by default (ownership
   chains up to an ultimate parent are usually short and worth seeing in
   full; a manager's fund/subsidiary fan-out can be large, so it starts
   collapsed past the first two levels). The originally-searched entity
   always carries a blue **QUERY** badge; whichever entity is currently
   selected (loaded in the details panel) is shaded blue - both can be the
   same row, or different once you click into a relative.
4. Click any row to load its full profile - identifiers, GLEIF status, and
   (when resolved as a filer) its latest SEC 13F reported holdings - into the
   right-hand panel.

## Structure

```
src/
├── app/page.tsx              # the only route - search + tree + details, wired together
├── components/
│   ├── SearchBar.tsx          # query input + Name/LEI/CUSIP toggle
│   ├── ResultsList.tsx        # ambiguous-search result picker
│   ├── TreeExplorer.tsx       # collapsible indented tree list - renders TreeNode JSON,
│   │                            highlights the query root and the selected row
│   └── DetailsPanel.tsx       # renders EntityDetail JSON
└── lib/api.ts                 # typed fetch client - mirrors src/er/api/schemas.py exactly
```

An earlier version rendered the tree on a force-directed/DAG canvas
(`react-d3-tree`, then `react-force-graph-2d`) - dropped in favor of a plain
collapsible list once real entities with 40+ funds made a canvas layout
unwieldy and hard to keep readable. The plain-list approach scales to a large
fan-out far more predictably (just scroll/collapse) and needed no additional
dependency.
