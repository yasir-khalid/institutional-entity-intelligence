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
3. The tree renders depth-2 GLEIF relationships (parents in green, funds/
   subsidiaries in purple) rooted at the selected entity.
4. Click any node to load its full profile - identifiers, GLEIF status, and
   (when resolved as a filer) its latest SEC 13F reported holdings - into the
   right-hand panel.

## Structure

```
src/
├── app/page.tsx              # the only route - search + tree + details, wired together
├── components/
│   ├── SearchBar.tsx          # query input + Name/LEI/CUSIP toggle
│   ├── ResultsList.tsx        # ambiguous-search result picker
│   ├── EntityTree.tsx         # react-d3-tree wrapper - renders TreeNode JSON
│   └── DetailsPanel.tsx       # renders EntityDetail JSON
└── lib/api.ts                 # typed fetch client - mirrors src/er/api/schemas.py exactly
```

Tree rendering uses [`react-d3-tree`](https://github.com/bkrem/react-d3-tree)
rather than a hand-rolled layout - per the same "don't rewrite a widely-used
capability" principle the Python side follows for libpostal/rapidfuzz/DuckDB.
