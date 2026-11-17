# GridStorm design system

The frontend uses a restrained engineering interface — an energy-system control room crossed with a scientific research application: compact panels, explicit units, flat surfaces, no ornamental gradients, glass effects or decorative numbers. Implementation source: `apps/web/src/styles/index.css` and `src/components/ui`.

## Tokens

Semantic CSS variables `--gs-*` map to Tailwind v4 utilities (`bg-surface`, `text-fg-muted`, `border-line`, …). Change themes with `html[data-theme]`; the accessible header toggle persists the choice. System sans and monospace fallback stacks require no external font service.

| Group | Tokens (light / dark) | Use |
| --- | --- | --- |
| Surface layers | `canvas` `#f3f5f8` / `#0d1117` < `surface` `#ffffff` / `#151b23` < `surface-2` < `surface-3` | Page < panels < inset rows and hover < pressed and skeletons. |
| Lines | `line`, `line-strong` (decorative separators); `control-border` `#838d9b` / `#6b7686` | `control-border` bounds inputs (`.gs-input`): ≥ 3:1 on canvas, surface and surface-2 (WCAG 1.4.11). |
| Text | `fg`, `fg-muted`, `fg-subtle` | All ≥ 4.5:1 on every surface layer, every `*-soft` tint and `map-bg`. |
| Accent / focus | `accent`, `accent-fg`, `accent-soft`, `focus` | Primary actions, selection; `focus` ≥ 3:1 on every page and panel background. |
| Status | `ok`, `warn`, `danger`, `info` + `*-soft` tints | Badges and notices; each colour ≥ 4.5:1 as text on its own tint, surface, surface-2 and canvas. Status is never colour-only. |
| Network drawings | `map-bg` `#f7f8fa` / `#0b0f14`, `map-grid`, `map-ink` | Near-white (near-black) drafting sheet with a faint dot grid; `map-ink` (≥ 3:1 on `map-bg`) draws strokes with no voltage information. |
| Chart series | `chart-1` … `chart-8` | ECharts default categorical palette (`ui/Chart.tsx`); each ≥ 3:1 on surface. Series with a meaningful colour (carriers, loading scale) keep it. |
| Elevation | `shadow-panel`, `shadow-overlay` (`.gs-panel`, `.gs-overlay`) | Panels sit flat with a 1 px shadow; floating layers over a map (legend, asset drawer, view controls) use the overlay shadow. |

Every pair above is asserted by `styles/contrast.test.ts` for both themes; add a test when you add a token pair.

Type scale: 11 px annotations (`text-2xs`, `.gs-label` for small-caps section labels), 12 px small text and controls, 14 px body, 16 px section headings, 20 px page headings, 30–48 px display (overview only). Numbers use tabular numerals (`.tabular`). Spacing follows the 4 px Tailwind scale (8/12/16/24/32 px); surfaces use 8–12 px radii. Motion is limited to state feedback (hover, disclosure chevrons, skeleton shimmer); `prefers-reduced-motion` disables CSS transitions/animations and map zoom animation, and simulated flows are never animated as if measured.

## Components and interaction

Shared components include Button, Badge, Panel (optional leading `icon`), PageHeader, MetricCard (`size: 'md' | 'lg'`; a `tone` adds a coloured left rule as well as value colour), KeyValue, native labelled fields, DataTable, Legend, Chart and loading/error/empty states (`EmptyState` accepts an `icon`). Radix Dialog powers keyboard-accessible search, mobile navigation and drawers. Visible focus outlines and a skip link support keyboard users. Inputs retain native semantics; validation errors remain text, not colour alone. Long tables paginate and support sorting; units are included in headings and metric labels.

### Data and layout primitives (`components/ui`, 3.2)

These APIs are shared with the Data Observatory and workflow pages; change them additively only.

| Primitive | Props | Use |
| --- | --- | --- |
| `DatasetCard` | `title`, `to`, `id?`, `badges?`, `summary?`, `facts?: {label, value}[]`, `footer?`, `headingLevel? = 'h3'`, `testId?` | One dataset. The title link is stretched over the card (one tab stop, name = title); `footer` links stay separately clickable. Facts are pre-formatted values with units, `—` when missing (never 0). |
| `ProvenanceDisclosure` | `provenance?`, `rows: [label, value][]`, `summary? = 'Source, licence and provenance'`, `children?`, `defaultOpen?`, `testId?` | Native `<details>` with the provenance badge in the summary line and source, version, licence, attribution and checksums inside. Warnings stay outside. |
| `Drawer` | `open?`, `onOpenChange?`, `title`, `description?`, `trigger?`, `children`, `footer?`, `testId?` | Radix dialog: right-hand panel from `md`, bottom sheet on phones; focus trap, Escape and focus return. For secondary detail that needs room (dataset source, manifests). |
| `Legend` | `title`, `items`, `collapsible?`, `defaultOpen?` | Colour key; `collapsible` renders a disclosure with a ≥ 24 px summary for long keys (carrier groups). |

### Scientific-status primitives (`components/ui`, 3.0)

Use these instead of ad-hoc badges or coloured boxes, so status reads the same on every page:

| Primitive | Props | Use |
| --- | --- | --- |
| `ExecutionBadge` | `value: 'live' \| 'precomputed' \| 'unavailable' \| 'checking'`, `testId?` | Forecast of how this deployment would serve a scenario *before* submission. A finished job's actual mode stays `ExecutionModeBadge`. |
| `CostBasisBadge` | `basis: CostBasis \| null`, `testId?` | `<money_unit> · <kind>` (currency / benchmark / illustrative / unknown). A button opens a popover with money/price unit, currency (or “none — not a currency”), provenance, assumptions and penalty terms. All text comes from `lib/money.ts`; an undeclared basis is “cost units (basis unknown)”, never EUR. |
| `ProvenanceLabel` | `value`, `label?`, `describe? = true`, `testId?` | Provenance class with its meaning written out (works on touch and with screen readers). `ProvenanceBadge` remains the compact form for table cells (meaning in `title`). |
| `ScientificNotice` | `kind: 'warning' \| 'assumption' \| 'limitation'`, `title`, `children?`, `testId?` | Caveat next to the numbers it qualifies; `role="note"`, the kind is printed as a label. Never put one inside a collapsed disclosure. |
| `ScenarioCard` | `title`, `network`, `category`, `summary?`, `question?`, `execution?`, `badges?`, `selected?`, `onSelect`, `details?`, `selectAttributes?` | Compact selectable scenario. The select button is labelled by the title (rest via `aria-describedby`, `aria-pressed` for selection); a separate “Details & ids” button (`aria-expanded`/`aria-controls`) reveals long description and technical ids. |
| `Disclosure` | `summary`, `children`, `defaultOpen?`, `testId?` | Native `<details>` with the shared look; optional detail only (advanced settings, JSON). |
| `InfoPopover` | `trigger`, `label`, `children` | Radix popover for supporting detail; Escape closes and returns focus. |
| `Modal` | `open`, `onOpenChange`, `title`, `description?`, `footer?` | Radix dialog for confirmations (e.g. discarding Studio edits). |
| `LoadingState` | `label`, `rows?`, `slowAfterMs? = 6000` | Labelled skeleton; after the delay it explains that a hosted API waking from idle can take 30–60 s. `ErrorState` treats status 0/502/503/504 as “unreachable or waking up”. |

`TextField`/`NumberField` accept `error`: the message is rendered under the field, the input gets `aria-invalid` and the message joins `aria-describedby`.

### Crisis Studio

Four steps (grid → crisis → review → run) with a stepper whose buttons are disabled until earlier answers exist, and a Back/Next bar that is sticky at the bottom of the viewport below `lg`. A user-initiated step change moves focus to the step region (`role="region"`, “Step N of 4: …”). The grid list is an ARIA radio group (one Tab stop, arrow keys select, Enter continues). Grid cards show execution policy and cost basis; preset cards are `ScenarioCard`s with event category, the question derived from the events and mitigation switches (`features/studio/presentation.ts`, no result claims), and an `ExecutionBadge`. Scenario id, StormSpec hash, network id, event list and the full description sit behind “Details & ids”. Step 1 offers the recommended start (guided-demo preset when its grid is solved live, else the smallest live grid's first runnable crisis).

Validation issues name the field in words (“Event 2 · factor”, “Value of lost load (VOLL)”), keep the exact API path and code, attach to the field where possible and link to the step that fixes them. VOLL is labelled in the dataset's price unit and described as a penalty parameter. Unsaved edits persist in `localStorage` (`gridstorm-studio-draft/v1`): reopened automatically for the same preset/grid, offered (Restore/Discard) elsewhere, cleared by a confirmed Discard or a successful save. Edited scenarios that the deployment cannot serve are still blocked before any POST.

Guided demo: Home's primary CTA opens `/studio?network=pglib-case14-ieee&preset=pglib-case14-ieee-gen-1-outage&guide=1`. The guide panel reads the outaged generator's bus, carrier and capacity, the remaining installed capacity and the peak load from the API (generator table, network summary), states the investigated question and runs the preset; the run page opens as `/runs/<id>?guide=1`. Editing the scenario pauses the guide.

Numeric fields keep editable blank text and treat non-finite required-field values as blank until validation resolves them; synchronization uses `Object.is` so `NaN` never triggers a render loop. Selected-asset cards dismiss on Escape, ignore an Escape already consumed by a nested interaction, and remove their keyboard listener on unmount.

MapLibre renders geographic network assets, with OpenFreeMap/OSM attribution. Schematic datasets are drawn by the SVG schematic (`components/map/schematic`): IEC-style single-line symbols on the `map-bg` drafting sheet with a dot grid that follows pans. Buses are rings coloured by nominal voltage with 12 px tabular ids on a halo; branches follow the Open Infrastructure Map voltage scale, thicker for higher levels, except the scale's lowest band (< 10 kV or unknown — e.g. PGLib IEEE 14 stores 1 kV) which uses the theme's `map-ink` so the drawing is not washed-out grey; the legend shows the same colours. Transformers are two overlapping windings at the branch midpoint, generators a circle with a sine wave filled with a tint of the carrier colour and stroked with the carrier colour mixed toward the text colour (pale carriers stay visible in both themes), storage a circle with battery plates, loads an arrowhead in `map-ink`. Selection draws an accent ring and dims unrelated assets to 28 %. Voltage colours, loading percentages and signed loading differences use separate legends; raw dataset views draw no loading colours, congestion marks or flow animation. Asset identities combine component type and id.

The overview at `/` introduces Explore → Simulate → Compare → trace provenance; its primary CTA starts the guided demo, with Explorer and a plain Crisis Studio entry as secondary links. The guided-demo card shows the real IEEE 14-bus drawing (same schematic renderer and API queries as the Explorer, lazy-loaded into a fixed-height, inert slot so it adds no focus stops, no wheel capture and no layout shift; MapLibre, ECharts and KaTeX are not loaded on `/`). Dataset cards (`DatasetCard`) list every network from `GET /api/v1/networks` with counts exactly as reported, link to the Explorer and to the Data Observatory (`/data`); the evidence section links Methods, Benchmarks and the Research Workbench and spells out the provenance vocabulary. Existing `/?network=…` deep links redirect to `/explore` without dropping query parameters. Workspace navigation contains Explore, Simulate, Compare and Library; Advanced research is a secondary disclosure on desktop and a labelled drawer group on mobile. Navigation, drawer close/theme controls and map zoom/reset targets are at least 44 px.

Explorer layout: a 320 px sidebar (bottom sheet below `md`) grouped into Network (select, kind/provenance/licence badges, description, “Source, licence and assumptions” drawer), Find an asset (Ctrl/⌘ K palette), Layers and filters (per-layer counts; layers whose dataset total is 0 are not offered; one-tap voltage-level filters when the dataset stores ≥ 2 levels; carriers and countries collapse) and the manifest's scientific warnings, which always stay visible. Above the canvas a fixed-height bar labels the coordinate kind (“Schematic layout — not geographic” / “Geographic layout — OSM basemap”), the network name, whole-dataset totals from the network list and the data provenance class. The legend floats bottom-left (top-left for geographic maps on phones, clear of the attribution); the asset inspection drawer docks right (left of the zoom controls from `lg`) or as a bottom sheet on phones. Everything that arrives late reserves its final size (dataset block, layer list skeleton, canvas bar), so loading does not shift the controls.

Explorer paints buses and branches from one GeoJSON query. Generator/storage layers are opt-in on geographic networks; search can explicitly include generation, storage and loads. Selecting an asset fetches only its canonical table, so missing electrical fields are never invented from display geometry. Session query keys include network id and dataset content hash; browser HTTP caching honours the API's ETag. The legend collapses and groups carriers by display technology without merging data; the geographic legend lists only the voltage bands present. Fit-to-network adapts padding to the canvas and to which overlays float over it; a ResizeObserver follows bottom-sheet/canvas size changes and disconnects on map cleanup. The native basemap attribution is shown once.

ECharts displays real result series. Missing data is an em dash or an explicit empty state, not zero. Job execution uses stages, never invented percentages. Single-run energy not supplied is “Unserved energy (MWh)”, not EENS. Timezone-naive simulation labels retain their model clock without a timezone suffix; explicitly zoned timestamps are converted to UTC.

## Verification

Vitest covers API error mapping, formatting, scales, legends, validation messages, research artifact parsers (fixtures copied from `data/artifacts`) and the Crisis Studio `live_execution` policy (fixtures captured from the local API, including the real HTTP 422 `live_execution_unavailable` body). Playwright runs against the real local backend through the Vite preview proxy:

- `journey.spec.ts`: canvas click on a rendered bus, every route via the main navigation, scenario validation errors, save, two live IEEE-14 runs (keyboard Enter on Run), result download, comparison with map replay and Markdown export, mobile navigation, theme switch.
- `research.spec.ts`: `/benchmarks`, `/contingency`, `/operations`, `/methods`; every expected number is read from the same `data/artifacts` files the API serves.
- `studio-live-execution.spec.ts`: on `scigrid-de` (`live_execution: false`) an unchanged preset is served from its precomputed artifact; unavailable edited scenarios are disabled before submission.
- `studio-guided-demo.spec.ts`: Home CTA → guided Studio at 1440×900 and 390×844 (generator facts compared with the API's generator table, run lands on `/runs/<id>?guide=1`), preset details by keyboard, keyboard-only grid → crisis → review → run, no horizontal overflow of the document or `main`.
- `studio-design-screenshots.spec.ts` (opt-in, `GRIDSTORM_CAPTURE_3_0=before|after`): Home and the four Studio steps at 1440×900 and 390×844 in both themes into `docs/audit/screenshots/3.0/<phase>/`.
- `screenshots.spec.ts`: all routes at desktop/mobile in both themes. `landing-explorer.spec.ts` adds landing/Explorer at 1440×900, 768×1024 and 390×844, recorded in `docs/audit/screenshots/2026-11-15-after/` when run against the live API. It checks the legacy redirect, geometry-first requests, fit extent, on-demand asset details, single-map cleanup and, on the overview, that dataset cards and their count match `GET /api/v1/networks`, the preview draws all 14 IEEE buses and no map/chart canvas is loaded. `explorer-schematic.spec.ts` also checks the canvas-bar totals against the API, the source drawer and the 345 kV quick filter on IEEE 118 against the GeoJSON.
- `scripts/visual-matrix.mjs` (not a test): screenshot + CLS + horizontal-overflow matrix (5 viewports × 2 themes, `--full` for the whole page) used for `docs/audit/screenshots/3.2-before|after/`.

Single-run metrics say "Unserved energy"; "EENS" is used only for StormRisk's probability-weighted Monte Carlo estimate.

Run `npm run build`, `npm run lint`, `npm run typecheck`, `npm test`, then `npm run e2e` with the local API on port 8130 (`cd services/api && uv run uvicorn gridstorm_api.main:app --port 8130`) or `GRIDSTORM_API_PROXY` overridden.
