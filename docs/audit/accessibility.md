# Live accessibility audit (axe-core + keyboard)

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
