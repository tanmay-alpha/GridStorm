# GridStorm design system

The frontend uses a restrained engineering interface: compact panels, explicit units, flat surfaces, and no ornamental gradients. Implementation source: `apps/web/src/styles/index.css` and `src/components/ui`.

## Tokens

Semantic CSS variables `--gs-*` map to Tailwind v4 utilities. Light canvas/surface are `#f4f5f7` / `#ffffff`; dark canvas/surface are `#0e1218` / `#151b23`. Text, borders, accent, focus, success, warning and danger all have theme-specific tokens. Change themes with `html[data-theme]`; the accessible header toggle persists the choice. System sans and monospace fallback stacks require no external font service. Default body text is 14 px; technical annotations use 11–12 px with tabular numerals.

## Components and interaction

Shared components include Button, Badge, Panel, PageHeader, MetricCard, KeyValue, native labelled fields, DataTable, Legend, Chart and loading/error/empty states. Radix Dialog powers keyboard-accessible search and mobile navigation. Visible focus outlines and a skip link support keyboard users. Inputs retain native semantics; validation errors remain text, not colour alone. Long tables paginate and support sorting; units are included in headings and metric labels.

MapLibre renders network assets, with OpenFreeMap/OSM attribution for geographic datasets. Schematic datasets use an unlabelled background and a persistent “Schematic layout — not geographic” badge. Voltage colours, loading percentages and signed loading differences use separate legends. Asset identities combine component type and id. Mobile explorer controls occupy a scrollable bottom sheet below the map.

ECharts displays real result series. Missing data is an em dash or an explicit empty state, not zero. Job execution uses stages, never invented percentages. Single-run energy not supplied is “Unserved energy (MWh)”, not EENS. Timezone-naive simulation labels retain their model clock without a timezone suffix; explicitly zoned timestamps are converted to UTC.

## Verification

Vitest covers API error mapping, formatting, scales, legends and validation. Playwright uses the real local backend through the Vite preview proxy, performs canvas clicks, edits and validates scenarios, runs simulations and exports reports. Real screenshots are written to `docs/audit/screenshots/`. Run `npm run build`, `npm run lint`, `npm run typecheck`, `npm test`, then `npm run e2e` with the local API available at port 8010 (or `GRIDSTORM_API_PROXY` overridden).
