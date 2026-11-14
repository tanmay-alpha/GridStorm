# ADR 0002 — PyPSA-Explorer as the analytical baseline

- Status: accepted
- Date: 2026-11-15
- Evidence: [unchanged-upstream audit](../audit/pypsa-explorer-baseline.md)
- Upstream: [PyPSA-Explorer](https://github.com/open-energy-transition/PyPSA-Explorer), commit `c85252c98cab742b43245a18bcd310d095bab443`

## Context

ADR 0001 selects a React public frontend and an isolated PyPSA 1.4.x / pandas 3 core environment.
We need capacity, energy-balance and cost views without importing Dash into that frontend or the API.

The pinned Explorer is MIT-licensed (Copyright (c) 2025 OET Network Viewer contributors). Its
analytical callbacks are a thin layer over PyPSA statistics: optimal capacity, energy balance,
CAPEX and OPEX, grouped by carrier, bus carrier and country. This is useful analytical precedent,
not an independent numerical engine. Its bundled tests mostly exercise Dash wiring, not physics.

The unchanged upstream suite recorded **105 passed, 3 skipped** both with its frozen lock and
with a fresh PyPSA 1.4.0 / pandas 3 install. Its lock is stale relative to its project metadata;
`uv sync --locked --extra test` fails. Headless launch of the unchanged app with `demo-network.nc`
returned HTTP 200 for the root, Dash metadata and capacity/CAPEX callbacks. Direct execution of
all analytical plotting calls also succeeded with PyPSA 1.4.0. Exact commands, logs, warnings,
skipped tests and coverage limitations are in the audit.

The application itself is not an appropriate public multi-user backend: it keeps networks in a
shared module-level registry, parses uploads in-process and defaults to a development server.
Its country filter builds a query expression from client values. It requires Python >=3.12,
whereas our core is Python 3.11. Depending on its distribution would also pull in Dash, Flask,
folium and other unnecessary UI dependencies.

## Decision

**Retain PyPSA-Explorer's analytical views as GridStorm's preferred analytical baseline, but port
only their analytical logic into `services/analytics` (`gridstorm_analytics`).** PyPSA's own
`n.statistics` remains the numerical implementation. We do not fork or embed Explorer's Dash
application, and we do not describe the port as an independent validation of PyPSA.

1. Expose `available_analytics()` and `compute(kind, network, carriers=..., countries=...)` for
   capacity, energy balance, costs and a small network summary. Return strict JSON with units,
   assumptions, calculated provenance, upstream SHA and engine version. The React frontend
   consumes these results through the API contract, never through Dash callbacks.
2. Keep component classes and units separate: MW generation/link capacity, MVA branch ratings,
   MWh storage energy. Preserve bus-carrier splits for energy balances and exclude mass-based
   carriers from MWh fields. Keep raw carrier identifiers with separate display names.
3. Add installed capacity and installed CAPEX for unsolved networks. Withhold dispatch-dependent
   energy balance and OPEX when optimisation results are absent; do not turn missing dispatch
   into zero. Optimal capacities and optimal CAPEX are also withheld until solved.
4. Validate filters against the loaded network and filter statistics indices directly, without
   constructing query expressions. The port's carrier filter selects component carriers;
   Explorer's UI selected bus carriers. This deliberate difference is documented in the audit.
5. Keep unrounded statistics and zero rows for numerical consumers. Document the PyPSA sign
   convention (injection positive, withdrawal negative), snapshot weighting and branch country
   attribution. Monetary fields assume network cost inputs are in EUR; PyPSA does not establish
   the currency itself.
6. Preserve the MIT copyright/attribution header in every derived source file and ship the full
   upstream license with the package. Do not depend on Explorer at runtime.

## Consequences and limits

- The analytical API is independent of the plotting/UI stack and compatible with the core
  environment. The port owns its own lockfile and numerical regression tests.
- Tests exercise all kinds on unsolved and HiGHS-solved `ac_dc_meshed` and `scigrid_de` examples,
  comparing capacity, costs and dispatch energy to raw-table calculations and checking balance
  residuals. They do not establish correctness for every possible PyPSA model formulation.
- A solved legacy PyPSA-Eur demo has an approximately 2.3% difference between statistics-derived
  optimal CAPEX plus OPEX and its stored objective plus objective constant. The cause is not
  established. We report the statistics, not a claimed reconciliation of that legacy objective.
- Unchanged upstream test success does not establish analytical correctness: upstream skips
  three tests and has little analytical callback coverage. Our independent numerical checks
  are required in addition to the baseline audit.
- Side-by-side/difference analysis is not inherited from Explorer: its multiple-network UI
  switches the active network. GridStorm comparisons belong to its own API/frontend contracts.

## Alternatives rejected

- **Embed the Dash app or import its package:** incompatible Python floor, unnecessary UI
  dependencies and unsuitable public-session/upload model.
- **Replace the analytical baseline entirely:** no evidence of an analytical API incompatibility
  on PyPSA 1.4.0; it would discard useful, MIT-licensed view/grouping precedent without adding a
  distinct numerical implementation. Reconsider if future PyPSA versions invalidate the port's
  numerical regression checks or require substantially different analytical semantics.
