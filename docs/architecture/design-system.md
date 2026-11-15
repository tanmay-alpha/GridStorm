# GridStorm design system

The frontend uses a restrained engineering interface: compact panels, explicit units, flat surfaces, and no ornamental gradients. Implementation source: `apps/web/src/styles/index.css` and `src/components/ui`.

## Tokens

Semantic CSS variables `--gs-*` map to Tailwind v4 utilities. Light canvas/surface are `#f4f5f7` / `#ffffff`; dark canvas/surface are `#0e1218` / `#151b23`. Text, borders, accent, focus, success, warning and danger all have theme-specific tokens. Change themes with `html[data-theme]`; the accessible header toggle persists the choice. System sans and monospace fallback stacks require no external font service. Default body text is 14 px; technical annotations use 11–12 px with tabular numerals.

The overview uses a 36–48 px display tier; workspace page headings use 20 px, section headings 14–20 px and controls 12–14 px. Spacing follows the 4 px Tailwind scale (8/12/16/24/32 px); surfaces use 8–12 px radii with restrained borders and shadows. Both themes retain the tested semantic palette instead of using decorative, low-contrast text colours. Focus remains visible independently of theme. Reduced-motion preferences disable CSS transitions/animations and map zoom animation.

## Components and interaction

Shared components include Button, Badge, Panel, PageHeader, MetricCard, KeyValue, native labelled fields, DataTable, Legend, Chart and loading/error/empty states. Radix Dialog powers keyboard-accessible search and mobile navigation. Visible focus outlines and a skip link support keyboard users. Inputs retain native semantics; validation errors remain text, not colour alone. Long tables paginate and support sorting; units are included in headings and metric labels.

Numeric fields keep editable blank text and treat non-finite required-field values as blank until validation resolves them; synchronization uses `Object.is` so `NaN` never triggers a render loop. Selected-asset cards dismiss on Escape, ignore an Escape already consumed by a nested interaction, and remove their keyboard listener on unmount.

MapLibre renders network assets, with OpenFreeMap/OSM attribution for geographic datasets. Schematic datasets use an unlabelled background and a persistent “Schematic layout — not geographic” badge. Voltage colours, loading percentages and signed loading differences use separate legends. Asset identities combine component type and id. Mobile explorer controls occupy a scrollable bottom sheet below the map.

The overview at `/` introduces Explore → Simulate → Compare → trace provenance, with a real IEEE14 outage preset CTA. Existing `/?network=…` deep links redirect to `/explore` without dropping query parameters. Workspace navigation contains Explore, Simulate, Compare and Library; Advanced research is a secondary disclosure on desktop and a labelled drawer group on mobile. Navigation, drawer close/theme controls and map zoom/reset targets are at least 44 px.

Explorer paints buses and branches from one GeoJSON query. Generator/storage layers are opt-in; search can explicitly include generation, storage and loads. Selecting an asset fetches only its canonical table, so missing electrical fields are never invented from display geometry. Session query keys include network id and dataset content hash; browser HTTP caching honours the API's ETag. The legend collapses and groups carriers by display technology without merging data. Provenance collapses while scientific quality warnings stay outside the disclosure. Fit-to-network adapts padding to the canvas; a ResizeObserver follows bottom-sheet/canvas size changes and disconnects on map cleanup. The native basemap attribution is shown once.

ECharts displays real result series. Missing data is an em dash or an explicit empty state, not zero. Job execution uses stages, never invented percentages. Single-run energy not supplied is “Unserved energy (MWh)”, not EENS. Timezone-naive simulation labels retain their model clock without a timezone suffix; explicitly zoned timestamps are converted to UTC.

## Verification

Vitest covers API error mapping, formatting, scales, legends, validation messages, research artifact parsers (fixtures copied from `data/artifacts`) and the Crisis Studio `live_execution` policy (fixtures captured from the local API, including the real HTTP 422 `live_execution_unavailable` body). Playwright runs against the real local backend through the Vite preview proxy:

- `journey.spec.ts`: canvas click on a rendered bus, every route via the main navigation, scenario validation errors, save, two live IEEE-14 runs (keyboard Enter on Run), result download, comparison with map replay and Markdown export, mobile navigation, theme switch.
- `research.spec.ts`: `/benchmarks`, `/contingency`, `/operations`, `/methods`; every expected number is read from the same `data/artifacts` files the API serves.
- `studio-live-execution.spec.ts`: on `scigrid-de` (`live_execution: false`) an unchanged preset is served from its precomputed artifact; unavailable edited scenarios are disabled before submission.
- `screenshots.spec.ts`: all routes at desktop/mobile in both themes. `landing-explorer.spec.ts` adds landing/Explorer at 1440×900, 768×1024 and 390×844, recorded in `docs/audit/screenshots/2026-11-15-after/` when run against the live API. It checks the legacy redirect, geometry-first requests, fit extent, on-demand asset details and single-map cleanup.

Single-run metrics say "Unserved energy"; "EENS" is used only for StormRisk's probability-weighted Monte Carlo estimate.

Run `npm run build`, `npm run lint`, `npm run typecheck`, `npm test`, then `npm run e2e` with the local API on port 8130 (`cd services/api && uv run uvicorn gridstorm_api.main:app --port 8130`) or `GRIDSTORM_API_PROXY` overridden.
