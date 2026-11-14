# UI reference audit

## Open Infrastructure Map

Sources: [live map](https://openinframap.org/), [about](https://openinframap.org/about), [repository](https://github.com/openinframap/openinframap). Read-only clone: `upstream/openinframap`; inspected upstream commit `780e6b96d9d465d9e8cd751db7ebcfc80230bfd6`.

Lessons: quiet basemap, engineering voltage colours, independent asset layers, and a compact asset detail panel make a dense infrastructure map legible. The threshold/colour table and voltage step-expression idea from `web/src/style/style_oim_power.ts` were adapted in `apps/web/src/lib/scales.ts`, with an attribution header. Upstream web code is BSD-3-Clause; the complete notice is retained in root `THIRD_PARTY_NOTICES.md`. Other UI code is original. OSM data licensing is distinct from software licensing; basemap attribution remains visible.

## Electricity Maps

Sources: [site](https://www.electricitymaps.com/), [map](https://app.electricitymaps.com/map/live/fifteen_minutes). Its distinction between layers, production/consumption, geography and time informed separate metric panels, carrier legends and snapshot controls. No code, branding, imagery or data was copied; this is design inspiration only, with no software-license reliance.

## PyPSA-Eur map viewer

Sources: [live explorer](https://oalles.github.io/pypsa-eur-map-viewer/), [baseline audit](pypsa-explorer-baseline.md). Network exploration and separating filters from the map are conceptual references. No source code was copied or adapted: the referenced project has no verified software licence. GridStorm's React, MapLibre and API implementation is original.

## Grid2viz

Sources: [repository](https://github.com/Grid2op/grid2viz), [detailed local audit](grid2viz-audit.md). Episode comparison, explicit action timelines, loading/rho traces and survival KPIs informed the Operations page. Upstream is MPL-2.0; no source files or UI code were copied. GridStorm consumes its own generated replay artifacts and labels simulation assumptions rather than presenting a live control system.

The references do not supply GridStorm test or production data. Unit fixtures come from repository canonical datasets or captured responses from the real local API; browser tests call that API directly through the preview proxy.
