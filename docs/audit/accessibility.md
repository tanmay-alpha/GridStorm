# Live accessibility audit (axe-core + keyboard)

> Historical audit (2026-11-14). Superseded by the fixes in TODO P6-12 (contrast, ARIA, target size, run-page map crash) and the GridStorm 3.0 axe re-audit (TODO G3-14); see [TODO.md](../../TODO.md) for the current state.

Audited: 2026-11-14 22:14–22:30 UTC against the live deployment <https://gridstorm.vercel.app>
(API `git_sha 887d217`). Light theme (default) only. Nothing in the app was changed for this audit.

## Method

- Tooling in a throwaway directory outside the repo: Playwright 1.65.1 (headless Chromium 159.0.8154.6),
  `@axe-core/playwright` 4.14.0 (axe-core 4.14.0).
- Rule tags: `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa, best-practice`.
- Each page: `goto` (load) → `networkidle` (≤20 s) → 1.5 s settle → `AxeBuilder.analyze()`.
- Profiles: **desktop** 1440×900; **mobile** Playwright `Pixel 7` device (412×839 viewport, touch, DPR 2.625).
- Routes (10): `/`, `/studio`, `/runs/<id>`, `/compare`, `/library`, `/contingency`, `/operations`,
  `/benchmarks`, `/methods`, and an unknown path (`/no-such-page`, the 404 route).
- `/runs/<id>` uses job `ac207ce7-a300-48d8-89b0-1ab393badb18` (`ac-dc-meshed-baseline`, submitted via
  `POST /api/v1/simulations`, `status=completed`, `reused=true`).

Not covered: dark theme, screen-reader output (NVDA/VoiceOver), 200 %/400 % zoom and reflow,
keyboard use on the mobile layout, and the interactive states of dialogs, charts and maps beyond initial load.

## Results by route

Violation counts are axe *rules* (affected nodes in parentheses). "Needs review" are axe `incomplete`
results (mostly text over gradients/canvas that axe cannot resolve), not confirmed failures.

| Route | Desktop violations | Mobile violations | Needs review (desktop / mobile) |
|---|---|---|---|
| `/` | serious: `label-content-name-mismatch` (1), `target-size` (5) | same | color-contrast 18 / 41 |
| `/studio` | none | none | — |
| `/runs/<id>` | none when the page renders; **2 of 6 desktop loads crash** (see M1) and axe then reports moderate `landmark-one-main` (1) | none | — / color-contrast 7 |
| `/compare` | none | none | — |
| `/library` | none | none | — / color-contrast 143 |
| `/contingency` | serious: `color-contrast` (3); moderate: `heading-order` (1) | same + serious: `scrollable-region-focusable` (1) | — / color-contrast 156 |
| `/operations` | serious: `color-contrast` (6) | same | color-contrast 14 / 30 |
| `/benchmarks` | serious: `color-contrast` (3) | same + serious: `scrollable-region-focusable` (1) | — / color-contrast 222 |
| `/methods` | serious: `aria-prohibited-attr` (9), `link-in-text-block` (3) | same | color-contrast 73 / 113 |
| `/no-such-page` | none | none | — |

No critical-impact axe violations on any route.

## Violations by impact

### Serious

1. **`color-contrast`** (WCAG 1.4.3) — `/contingency` 3, `/operations` 6, `/benchmarks` 3 nodes, both profiles.
   All are `text-fg-subtle` (`--gs-fg-subtle: #6b7686`, `apps/web/src/styles/index.css:22`) at 11–12 px on
   `surface-2`: 4.22:1 on `#f4f5f7`, 4.10:1 on `#f0f2f5` (needs 4.5:1). Selectors include
   `label[for="_r_5_"] > .gs-label`, `[data-testid="artifact-meta"] .text-fg-subtle.font-mono`,
   `.gap-1.inline-flex.items-center:nth-child(3) > .text-fg-subtle`.
2. **`aria-prohibited-attr`** (WCAG 4.1.2) — `/methods`, 9 nodes: `div[aria-label="DC power flow"]`,
   `div[aria-label="Unserved energy"]`, `div[aria-label="Curtailment"]`, `div[aria-label="Line loading"]`,
   `article[aria-labelledby="eq-ptdf"] > .overflow-x-auto`, … `aria-label` on a role-less `div`; source is
   `features/research/components/TeX.tsx:8`. The equations therefore have no reliable accessible name.
3. **`link-in-text-block`** (WCAG 1.4.1) — `/methods`, 3 reference links (`ol > li > a.hover:underline`):
   link `#1d5fb8` vs text `#18202b` is 2.64:1 (needs 3:1) and links have no underline until hover.
4. **`label-content-name-mismatch`** (WCAG 2.5.3) — `/`, 1 node `.text-left`: the asset-search trigger
   (`features/explorer/AssetSearch.tsx:46-54`) shows "Search assets… Ctrl K" but is named
   `aria-label="Search assets (Ctrl+K)"`; speech-input users saying the visible text will not match.
5. **`target-size`** (WCAG 2.5.8, 2.2 AA) — `/`, 5 nodes `#_r_8_ … #_r_c_`: 14×14 px targets with 16 px safe
   spacing (needs 24 px). The size matches the layer-toggle checkboxes `size-3.5` in
   `features/explorer/LayerControls.tsx:23-24` (mapping by size and count, not by DOM dump).
6. **`scrollable-region-focusable`** (WCAG 2.1.1) — mobile only: `/contingency`
   `section[aria-label="Baselines"] > .min-w-0 > .overflow-x-auto` and `/benchmarks`
   `.lg:grid-cols-2 > .min-w-0:nth-child(1) > .overflow-x-auto`. Horizontally scrolling tables with no
   focusable content cannot be scrolled from the keyboard. Likely the `DataTable` wrapper
   (`components/ui/DataTable.tsx:68`) [inference from the class name].

### Moderate

7. **`heading-order`** — `/contingency`, `div:nth-child(3) > h4` ("Overloaded branches" / "Voltage violations",
   `features/research/pages/ContingencyPage.tsx:82,94`) skips a level.
8. **`landmark-one-main`** / **`page-has-heading-one`** on `/runs/<id>` — only in the failure states:
   the route-error screen ("Something went wrong") has no `<main>` (M1), and for a job id the API returns
   404 for (pre-restart job `d813df71-…`) the page still showed only a loading skeleton with no heading
   after networkidle + 3 s (3 GET retries, each 404).

## Manual findings

- **M1 — `/runs/<id>` intermittently crashes on desktop (functional, blocks all content).** 2 of 6 fresh desktop
  loads of the completed job ended on "Something went wrong" (0 of 6 on mobile). Console:
  `Error: Style is not done loading. at gA._checkLoaded … at gA.setLayoutProperty` (MapLibre, bundled in
  `SchematicBadge-*.js`), caught by React Router. In both crashing loads MapLibre fired `load` 23–24 ms after
  the first map was created (vs 2.0–4.5 s in the healthy loads), suggesting the map is re-created
  (coordinate kind/theme change) and the layer-visibility effect (`components/map/NetworkMap.tsx:279-294`)
  runs with a stale `ready === true` against the new, not-yet-loaded map [inference from code + timings].
- **M2 — non-descriptive titles** (WCAG 2.4.2): `/runs/<id>` and the 404 page are titled just "GridStorm";
  `AppLayout.tsx:93-96` only maps nav routes.
- **M3 — skeleton never resolves for a missing job** (see 8): no error message or heading is exposed to
  assistive tech while the query retries.

## Keyboard-only check (desktop, `/studio`)

| Check | Result |
|---|---|
| First Tab | focuses "Skip to main content" — visible at (8, 8), 128×21 px, `outline: solid 2px rgb(29,95,184)` |
| Enter on skip link | URL → `/studio#main`; focus moves to `<main tabindex="-1">` |
| Next Tab after skip | first control inside `<main>` (scenario preset button "SciGRID Germany — wind lull …") |
| Tab order to **Run simulation** | reached on Tab **36** (1 skip link, 1 home link, 8 nav links, theme toggle, 11 preset buttons, then the scenario form: network select, id/name/inputs, event row, toggles, numeric inputs) — order follows visual order |
| Focus visible | all 36 stops matched `:focus-visible` and had a 2 px outline; none were off-screen or zero-size |
| Enter on Run simulation | submitted and navigated to `/runs/0c854dc7-72a2-45b1-9280-d96354742c60` |

`<main>` itself shows no outline when focused by the skip link (`outline-style: none`); acceptable for a
programmatic focus target.

## Observation: job failures during the audit

Between ~22:13 and ~22:20 UTC every `ac-dc-meshed` job failed with `error.code = memory_limit`
("engine resident memory 330 MB exceeded the 330 MB limit; process tree killed", stage `loading_network`):
jobs `cc22d394-8529-4444-8da6-5e6b26ab1418`, `0329ceb9-49e8-489a-bd62-13eb30c3ccac`,
`0c854dc7-72a2-45b1-9280-d96354742c60`. Cause: the job memory cap had been set to 330 MB; it was reverted to
400 MB and redeployed, after which job `ac207ce7-…` completed. The redeploy also wiped the ephemeral SQLite
job store, so earlier job ids (e.g. `d813df71-9211-4d0b-b80d-e7d38fc2a93a`) began returning 404.

## Recommended fixes (priority order)

1. Fix the `/runs/<id>` map race (M1): track readiness per map instance (e.g. reset `ready` synchronously
   with the instance or guard every style call with `map.isStyleLoaded()`/the instance that fired `load`).
2. Darken `--gs-fg-subtle` in the light theme to ≥ 4.5:1 on `#f0f2f5`; e.g. `#5f6977` computes to 4.96:1 on
   `#f0f2f5` and 5.10:1 on `#f4f5f7`. All reported `color-contrast` nodes use this token.
3. `TeX.tsx`: give the wrapper `role="img"` (or `role="math"`) with the `aria-label`, keeping the
   `overflow-x-auto` scroller separate.
4. Underline in-text links on `/methods` (or raise contrast to ≥ 3:1 against body text plus a non-colour cue).
5. Make horizontally scrollable table wrappers focusable (`tabIndex={0}`, `role="region"`, `aria-label`).
6. Asset-search trigger: drop the `aria-label` (let visible text name it) and add `aria-keyshortcuts="Control+K"`.
7. Enlarge layer-toggle checkboxes / their hit area to ≥ 24×24 px (clickable `<label>` padding).
8. Use `h3` for the contingency sub-headings; set descriptive `document.title` for run and 404 pages;
   render an error state (with heading) when a job is not found instead of an endless skeleton.

## Fixes applied (2026-11-15)

The live deployment was **not** re-audited. "Local axe" below means axe-core 4.14.0, with the same rule tags and
the same desktop/Pixel 7 profiles as above. It was injected into headless Chromium (Playwright 1.65.1) and run on
11 routes: the 10 above plus `/runs/<unknown id>`. Two `vite preview` builds were served against one local API:
"before" is HEAD `1247767`, "after" is the fixed build. Each fix also has a regression test, which fails on
`1247767` and passes after the fix.

| # | Finding | Change | Regression test |
|---|---|---|---|
| M1 | `/runs/<id>` crash `Style is not done loading` | **Root cause:** `RunPage` passes `coordinate_kind ?? 'schematic'`, so the map is first built schematic, which loads in ms from an inline style. It is then rebuilt as geographic once `GET /api/v1/networks` answers. In that same commit, the styling effect re-ran with the render's stale `ready === true` against the new, unloaded map. It re-ran on *every* render because the `carrierColors = {}` default was a new object each time. **Fix** (`components/map/NetworkMap.tsx`): readiness is the map *instance* whose own `load` fired (`loadedMap`). Every style/source effect requires `loadedMap === mapRef.current` and re-runs when the new instance loads. The default carrier colours are now a module constant. | `NetworkMap.test.tsx`: a fake MapLibre throws like `_checkLoaded`; before the fix it throws `Style is not done loading.`. `e2e/run-map.spec.ts` holds `GET /api/v1/networks` until the first map has loaded, which makes the live race deterministic. The before build lands on "Something went wrong / Style is not done loading."; the after build passed 4 of 4 runs. |
| M2 | Run and 404 pages titled "GridStorm" | `lib/title.ts` `useDocumentTitle`. `AppLayout` titles only nav routes. The run page uses `Run <scenario> · GridStorm`, `Job not found · GridStorm` or `Loading run · GridStorm`; the 404 page uses `Page not found · GridStorm`; the route-error screen uses `Error · GridStorm`. The route-error screen also gained a `<main>` landmark (the `landmark-one-main` finding in 8). | `AppLayout.test.tsx`: 404 title. `RunPage.test.tsx`: job-not-found title. |
| M3 / 8 | Endless skeleton for an unknown job id | **Root cause:** `useJob` polled every 1 s whenever no terminal job was loaded, including after a 404. TanStack Query resets a data-less query's error to `pending` on each refetch, so the page flipped back to the skeleton. HEAD made 4 GETs in 3.5 s in the test below. **Fix:** poll only while a non-terminal job is loaded (`api/hooks.ts`). `RunPage` renders an `h1` "Job not found" state on 404, with the API code and links to Studio/Library. | `RunPage.test.tsx` uses the app's real `createQueryClient()` (moved out of `main.tsx`): it checks the heading, that it is still shown after 1.5 s, and that exactly 1 fetch was made. |
| 1 | `color-contrast` (`--gs-fg-subtle`) | Light `#6b7686` → `#5d6775`; dark `#8792a2` → `#8f9aaa`. The audit's suggested `#5f6977` computes to 4.49:1 on `surface-3` (`#e4e7ec`), so it was darkened one step further. Ratios are in the table below. | `styles/contrast.test.ts` parses both theme blocks of `index.css` and asserts ≥ 4.5:1 for `--gs-fg`, `--gs-fg-muted` and `--gs-fg-subtle` on all 9 backgrounds. Before: light 4.22 on canvas, dark 4.29 on surface-3. |
| 2 | `aria-prohibited-attr` (equations) | `TeX.tsx`: the KaTeX output sits in `<div role="img" aria-label=…>` inside a separate, role-less `overflow-x-auto` scroller. | `pages.test.tsx` "/methods exposes each equation as a named image…" |
| 3 | `link-in-text-block` | `/methods` reference links and inline `[source]` citations are always underlined (`underline`, not `hover:underline`). | same test (reference links carry `underline`) |
| 4 | `label-content-name-mismatch` | The asset-search trigger drops `aria-label`, so its name is its visible text "Search assets… Ctrl K". The shortcut is exposed as `aria-keyshortcuts="Control+K Meta+K"`. | `controls.a11y.test.tsx`: accessible name === text content |
| 5 | `target-size` (layer toggles) | `LayerControls` `Check`: the whole row is a `<label>` at least 24 px tall (`min-h-6`) wrapping the 14 px box. Clicking anywhere on the row toggles it, and neighbouring boxes are ≥ 24 px apart. | `controls.a11y.test.tsx`: each checkbox is wrapped by a `min-h-6` label row; a text click toggles it |
| 6 | `scrollable-region-focusable` | The `DataTable` scroller is `role="region"`, `tabIndex={0}`, `aria-label="<caption> (table)"`. The "(table)" suffix keeps it distinct from a panel titled like the caption, which avoids `landmark-unique` (first seen locally on `/library` before the suffix). | `DataTable.test.tsx` |
| 7 | `heading-order` on `/contingency` | "Overloaded branches" and "Voltage violations" are `h3`, under the panel's `h2`. | `pages.test.tsx` "/contingency detail sub-headings…" |

`--gs-fg-subtle` contrast (WCAG 2.x formula, computed):

| Background | Light before `#6b7686` | Light after `#5d6775` | Dark before `#8792a2` | Dark after `#8f9aaa` |
|---|---:|---:|---:|---:|
| canvas | 4.22 | 5.26 | 5.96 | 6.59 |
| surface | 4.60 | 5.73 | 5.49 | 6.08 |
| surface-2 | 4.11 | 5.11 | 5.02 | 5.55 |
| surface-3 | 3.71 | 4.63 | 4.29 | 4.75 |
| accent-soft | 3.89 | 4.85 | 4.54 | 5.03 |
| ok-soft | 3.96 | 4.93 | 4.89 | 5.41 |
| warn-soft | 4.04 | 5.03 | 4.77 | 5.28 |
| danger-soft | 3.82 | 4.76 | 5.18 | 5.73 |
| info-soft | 3.89 | 4.84 | 4.91 | 5.43 |

Local axe, before (`1247767`, light theme) reproduced every violation in the live table:

- `/`: label-content-name-mismatch(1), target-size(5)
- `/contingency`: color-contrast(3), heading-order(1)
- `/operations`: color-contrast(6)
- `/benchmarks`: color-contrast(3)
- `/methods`: aria-prohibited-attr(9), link-in-text-block(3)
- mobile only: scrollable-region-focusable(1) on `/contingency` and on `/benchmarks`

`/runs/<unknown id>` also failed page-has-heading-one(1). It was titled plain "GridStorm", as were the run and 404 pages.
In the dark theme the before build had no color-contrast violations (desktop), but did have the same non-contrast violations as the light theme.

Local axe, after (fixed build): **0 violations on all 11 routes** in each of three profiles: desktop light, Pixel 7 light and
desktop dark. Every route has a descriptive title, e.g. `Run ac-dc-meshed-baseline · GridStorm`,
`Job not found · GridStorm` and `Page not found · GridStorm`. The dark theme on mobile was not run, and nothing was re-checked
against the live deployment.
