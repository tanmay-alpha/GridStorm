# GridStorm 3.3 — ranked UX review of the 3.2 production site

Method: production `f8b3c28` captured on 2026-11-17 with `apps/web/scripts/visual-matrix.mjs` (GET only)
for home, Grid Explorer (IEEE-14), Data Observatory index, two dataset pages, Crisis Studio, a live
IEEE-14 run, its comparison, Mitigation, Research Workbench, Benchmarks and Methods at 1440×900,
768×1024 and 390×844 in light and dark (102 captures; 0 page errors, 0 horizontal overflow, CLS ≤ 0.025).
Reviewed as a first-time visitor, a CS student, a power-system researcher and a recruiter scanning a
flagship project. Ranked by user impact × how often the page is seen.

| # | Finding (3.2) | Who it hurts | Change in 3.3 | Status |
|---|---|---|---|---|
| 1 | Embedded result maps (run, compare, mitigation): the schematic is small and the legend panel covers ≈ 40 % of the map | everyone reading a result | legend behind a "Legend" toggle, schematic re-fits, one-line colour scale under the map, taller maps | done (`b292ba7`) |
| 2 | Single-snapshot runs (all PGLib cases, i.e. the guided demo) spend ≈ one screen on three charts that each plot one value | first-time visitor, recruiter | compact single-period table (dispatch vs demand, load shed, mean and min–max nodal price) from the same result; multi-snapshot runs keep charts | done |
| 3 | Run page: findings scattered — banner, brief headline and KPI cards repeat; "what changed vs baseline" below the fold | everyone | outcome + KPIs + baseline deltas on the first screen at 1440×900; brief shows 5 statements + "show all"; run page 3 360 → 2 556 px tall | done |
| 4 | Explorer "Scientific warnings" are raw codes (`cost_currency_not_eur`, `marginal_cost_linearized_secant`, …) | student, recruiter | sentences from the importer code / cost-basis audit with the code kept underneath; same vocabulary in the Observatory | done (`b751059`) |
| 5 | Data Observatory: stress windows are listed, but the step from a historical window to its modelled scenario and result is a list of ids | researcher | per-window panel: derivation (quoted from the preset), precomputed status, unserved energy vs baseline, open in Studio / method / stored result; stress day shaded in the chart | done |
| 6 | Explorer legend overlaps nodes on first load | everyone | legend collapsed on first visit (remembered), network centred on the full canvas | done |
| 7 | Lost legacy results (HTTP 410) read like a generic error; no link between `2d47898b` and its recomputation `458fddab` | researcher checking reproducibility | cause stated with date and lost sha256, surviving metrics labelled, recomputations linked both ways, recompute offered only when recoverable | done |
| 8 | Downloads give no hint what each file is and no feedback after clicking | researcher | purpose, filename, size, sha256; announced post-download checksum check | done |
| 9 | Time-series workspace: only the published windows as presets; tooltips lack units and missing-value wording; export silent | researcher | last 31 days / whole coverage / calendar-year presets, UTC tooltips with units and "missing", export reports file, rows and licence | done |
| 10 | Weather data only for two short windows, so weather and demand cannot be compared across seasons | researcher | new `nasa-power-de-daily` (daily means of UTC hours, 2015-01-01 → 2020-09-30, same coverage as the load forecast) linked from the load-forecast page | done (`9551b52`) |
| 11 | Observatory index: categories hard to scan; card facts differ by type | first-time visitor | category jump bar, explanations, the same six facts on every card | done |
| 12 | Desktop run-page LCP regressed after 3.2 (1 460 → 1 668 ms) | everyone | scenario and baseline requests start in parallel with `/result` | implemented; production measurement in [web-performance-3.3](../benchmarks/web-performance-3.3.md) |
| 13 | Benchmarks/Methods/Workbench: dense but correct; no defect found that justified a redesign in this release | researcher | none | not changed |

Before/after first screens (1440×900 light unless noted): `docs/audit/screenshots/3.3-before/` and
`docs/audit/screenshots/3.3-after/` (run, run 390 dark, compare, mitigation, explorer, explorer 390
dark, dataset, a 410 run, and the observed-analogue entry after).
