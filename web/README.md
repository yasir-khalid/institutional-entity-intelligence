# Institutional Entity Intelligence - Web UI

A Next.js frontend over the Python entity-resolution engine, via a thin FastAPI
backend (`src/er/api/app.py`, in the repo root). This app owns no
entity-resolution logic itself - it searches, shows an entity profile, and
streams agent answers with their evidence.

## Run it

Two processes, both from the **repo root** unless noted:

```bash
make api                 # FastAPI backend on http://localhost:8000
cd web && npm run dev    # Next.js dev server (picks 3000, or the next free port)
```

Copy `.env.local.example` to `.env.local` first if `NEXT_PUBLIC_API_URL` needs
to point somewhere other than `http://localhost:8000`.

Requires live OpenSearch (see the root `README.md`'s Quickstart) - this UI is a
view over the same serving data, not a separate pipeline. The optional Form ADV
PDF endpoint also needs access to its locally mounted source ZIPs.

## How to use it

The page is one composer with two modes, **Search** and **Agent**, plus a few
suggested queries until you run one.

**Search** resolves a name through the matcher and lists the candidates with
their jurisdiction, LEI and decision (Resolved / Review / Candidate). The raw
retrieval score is deliberately not shown: it is an unnormalised BM25 value
and the list is already ordered by it. Opening a candidate loads its **entity
profile** (`EntityProfile.tsx`) below the list:

- **Identifiers**, and the records in other sources linked to this LEI (a
  13F CIK, an FFIEC RSSD, a Companies House number).
- **How other records were linked**: each crosswalk decision with its score,
  gap to the runner-up (clickable), per-feature points and matching config
  fingerprint, plus its human reviews and a Confirm / Reject form
  (`POST /api/reviews`). A review is stored as its own row, never an edit, and
  changes the graph link on the next `make build-knowledge-graph`.
- **Ownership & control** from the knowledge graph, one group per kind of
  claim: Schedule 13D/G beneficial owners, FFIEC NIC bank control, Companies
  House PSC, Forms 3/4/5 insiders and LEI successions. 13D/G and insider rows
  link to the filing on EDGAR. A succeeded LEI shows a "Succeeded by" link.
- **Latest reported 13F holdings**, with the coverage caveat and warnings for
  quarantined filings or values that look like thousands. Opening a holding
  loads its position across recent reports (`GET /api/positions/{cik}/{cusip}`).
  Each total and change has a formula toggle that unfolds to the filed
  information-table rows and their EDGAR filing.
- **Latest N-PORT report**, when the entity is a registered fund series: net
  assets, holding count and the ten largest holdings by USD value with their
  share of net assets, linked to the filing on EDGAR. N-PORT covers the whole
  portfolio but is a dated snapshot made public 60 days late, and says so.

The GLEIF hierarchy shows as parent and child counts only. The indented tree
(`EntityTreeView.tsx`, below) is kept but not mounted since the restyle.

**Agent** streams from `POST /api/ask/stream` (SSE). While the model works the
page shows a live research feed - one line per step, e.g. "Searching name
for …" - and replaces it with the answer, rendered as Markdown with clickable
`[n]` citations. The **Sources & method** rail lists every evidence record the
answer cites: source, criteria, record count, as-of date, and the addressed
values it supplied, with a link to the original filing when there is one. A
calculated value shows its formula and inputs down to the filed rows. Each
answer closes with Jev's verification badge. Follow-up questions keep the
conversation. Requires `OPENROUTER_API_KEY` in the repo root's `.env`; without
it the request fails with a clear error rather than silently.

The **Developer** toggle in the header opens a trace of the last agent run:
one span per model call, tool call, submission attempt and verifier pass, with
arguments, payload previews, token usage and why a submission was rejected.
Its open state survives reloads.

## Structure

```
src/
├── app/
│   ├── layout.tsx             # loads Inter + JetBrains Mono as CSS variables
│   ├── globals.css            # Tailwind v4 @theme tokens, .tabular, .scroll-thin
│   └── page.tsx               # the only route - query composer (Search/Agent),
│                                streaming agent answer, results, entity profile
├── components/
│   ├── ui.tsx                 # shared primitives: SectionLabel, Badge, Mono,
│   │                            Field/FieldGrid - the single source of truth
│   │                            for type scale, badge colours and label style
│   ├── SearchBar.tsx          # query composer + Search/Agent mode switch
│   ├── EntityProfile.tsx      # the entity profile: identifiers, link
│   │                            decisions + reviews, ownership & control,
│   │                            13F holdings with position history
│   ├── FactValues.tsx         # addressed values, formulas and their inputs
│   ├── EvidenceLayer.tsx      # the Sources & method evidence rail
│   ├── CitationChip.tsx       # inline [n] citation marker
│   ├── Markdown.tsx           # renders agent answers as Markdown (GFM) and
│   │                            turns inline [n] markers into citation links
│   ├── VerificationBadge.tsx  # Jev's verdict and per-check meters
│   ├── DeveloperPanel.tsx     # trace tree of the last agent run
│   └── EntityTreeView.tsx     # spanning-tree GLEIF hierarchy as an indented
│                                list - not mounted since the restyle
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
