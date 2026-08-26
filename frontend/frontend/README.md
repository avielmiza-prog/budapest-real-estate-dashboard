# Budapest Apartments — Deal Analysis & Underwriting Platform (frontend)

Next.js 16 (App Router) + TypeScript + Tailwind CSS v4 + shadcn/ui (hand-written
components) dashboard for the FastAPI backend in `../backend`.

## What's here

- **KPI row** — total listings tracked, average Budapest €/sqm, and how many
  "top undervalued" deals were found.
- **Table / Cards / Split view** — the view toggle now includes **Split**:
  deals ranked by Deal Score on the left, an interactive Leaflet/OpenStreetMap
  view on the right with color-coded pins (green/yellow/red = high/fair/low
  score). Clicking a pin highlights and scrolls to its card and vice versa.
- **Currency & live FX** — a HUF/EUR toggle in the top bar, backed by an
  editable rate pre-filled from the backend's `GET /fx-rate` (frankfurter.app/
  ECB, refreshable) — every price in the app respects it.
- **Deal Score badge** — a 0–100 composite (discount vs. benchmark, ROI,
  layout efficiency) shown on every card/row and as the map pin color.
- **Favorites & pipeline status** — a star toggle and a "New → Archived"
  status dropdown on every card/row and in the detail modal, persisted via
  `PATCH /properties/{id}`.
- **Deal Detail Modal** — photo gallery, asking price vs. district benchmark,
  full acquisition/exit cost breakdown (illeték, legal fee, renovation,
  5% safety buffer), rental yield, and an **editable custom renovation
  €/sqm input** that recalculates every metric instantly client-side
  (`lib/financial-calc.ts` mirrors the backend's formulas).
- **PDF exports** — "Contractor Spec Sheet" (for a contractor's on-site quote)
  and "Export Investment Memo" (a one-page underwriting summary, reflecting
  whatever custom renovation cost is currently entered) — both plain
  `<a href>` downloads, no JS fetch/blob handling.

These are all backed by `GET /dashboard/stats`, `GET /deals`, `GET /fx-rate`,
`PATCH /properties/{id}`, `GET /properties/{id}/spec-sheet`, and
`GET /properties/{id}/investment-memo` — see `../backend/README.md`.

## Setup

```bash
cd frontend
npm install
cp .env.local.example .env.local   # adjust NEXT_PUBLIC_API_BASE_URL if needed
npm run dev
```

Requires the backend running too (`cd ../backend && uvicorn app.main:app --reload`) —
the dashboard fetches from it directly and shows an inline error banner if it
can't be reached.

## Verified

`npm install`, `npx tsc --noEmit`, and `npm run build` all pass cleanly, and
the app has been driven end-to-end in a real browser against a live backend:
split view + map pins + click-to-highlight, currency toggle, live FX rate,
favorite/pipeline-status persistence (confirmed round-tripping through the
API), the custom renovation input's live recalculation, and both PDF exports
(confirmed the Investment Memo PDF reflects the exact custom renovation cost
entered in the modal). `npm run lint` currently fails on an unrelated
ESLint/`@eslint/eslintrc` circular-config-serialization bug in this dependency
set (not something introduced here) — `tsc`/`next build`'s own type-checking
is what actually gates correctness.

Leaflet needs `window`, so `components/dashboard/deal-map.tsx` is loaded via
`next/dynamic(..., { ssr: false })` from `split-view.tsx` — don't import it
directly into anything that renders during SSR/static generation.

## Assumptions worth knowing about

- **"Top undervalued deals found today"** compares each listing's price/sqm
  against its district's `avg_price_sqm_raw` (or `avg_price_sqm_renovated` if
  the listing's `condition` text suggests it's already renovated) — see
  `backend/app/dashboard.py::_reference_price_sqm`.
- **Min ROI % filtering** uses each listing's *best* renovation tier.
- A listing with no district benchmark on file yet still shows up (with "No
  benchmark" instead of an ROI badge, and no Deal Score) but is excluded
  whenever a Min ROI % filter is set, since there's nothing to compare it
  against.
- Listing photos are rendered with `next/image`'s `unoptimized` flag, since
  they're hotlinked from whatever portal they were scraped from.
- The favorite/pipeline-status PATCH response is a bare `PropertyOut` (no
  `analysis`/`deal_score`/etc.) — components merge just the changed field(s)
  into the existing `Deal` object rather than replacing it wholesale; see
  `components/dashboard/deal-actions.tsx`.

## Structure

```
app/                  Next.js App Router pages + global styles
components/ui/        Hand-written shadcn-style primitives (button, card, dialog, select, ...)
components/dashboard/ KPI cards, filters/top bar, table/card/split views, map, detail modal
lib/                  api.ts, types.ts, format.ts, financial-calc.ts, constants.ts, utils.ts
hooks/                use-dashboard-data.ts (deals/filters), use-fx-rate.ts (live rate)
```
