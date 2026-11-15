# Cost-basis audit — GridStorm 3.0

Audit date: 2026-11-15. Scope: all five committed datasets, their nonzero monetary coefficients,
PyPSA dispatch objectives, VOLL, cost analytics and API comparisons. This is a metadata and
interpretation correction: **no optimisation coefficients, constraints or scenario values changed**.

## Findings by dataset

| Dataset | Classification / money unit | Coefficients actually present | Evidence and limitations |
|---|---|---|---|
| `ac-dc-meshed` | illustrative / illustrative cost units; currency/year null | 6 generator marginal costs (0.09–5.8928445406 per MWh); generator, line and link capital costs | PyPSA toy example, not market data. [Source retrieval](../../data/networks/ac-dc-meshed/source/retrieval.json), [import assumptions](../../pipelines/network-import/src/network_import/examples.py), [PyPSA example documentation](https://docs.pypsa.org/latest/examples/ac-dc-meshed/). Capital costs belong to its capacity-expansion demo and are excluded from GridStorm dispatch. |
| `scigrid-de` | illustrative / illustrative cost units; currency/year null | Generator marginal costs 0–100 per MWh (441 nonzero); 38 storage units have marginal cost 3 per MWh | Geographic/topological provenance does not validate cost provenance. The upstream notebook describes the per-carrier costs as “not accurate”; importer records `marginal_cost_placeholder`. [Retrieval](../../data/networks/scigrid-de/source/retrieval.json), [import assumptions](../../pipelines/network-import/src/network_import/examples.py), [SciGRID example documentation](https://docs.pypsa.org/latest/examples/scigrid-lopf-then-pf/). |
| `pglib-case14-ieee` | benchmark_nominal / PGLib cost units; currency/year null | MATPOWER polynomial `mpc.gencost`, 2 nonzero imported generator slopes (7.920951 and 23.269494 per MWh); remaining slopes zero | [Committed case and generator-cost update notes](../../data/networks/pglib-case14-ieee/source/pglib_opf_case14_ieee.m), [secant importer](../../pipelines/network-import/src/network_import/pglib.py), [MATPOWER case format](https://matpower.org/docs/ref/matpower7.1/lib/caseformat.html). Nominal benchmark $, not EUR or verified-year USD. |
| `pglib-case118-ieee` | benchmark_nominal / PGLib cost units; currency/year null | Same MATPOWER polynomial semantics; 19 nonzero imported generator slopes, range including zero 0–124.581564 per MWh | [Committed case](../../data/networks/pglib-case118-ieee/source/pglib_opf_case118_ieee.m), [importer](../../pipelines/network-import/src/network_import/pglib.py), [PGLib release pinned by importer](../../pipelines/network-import/src/network_import/pglib_import.py). No inflation-year or exchange-rate evidence. |
| `pypsa-eur-be` | currency_verified / EUR, currency year **2025** | 33 nonzero generator marginal costs, 0.01–124.76737142857144 EUR/MWh; generator, line, link, storage-unit and Store capital costs | [Build/import pins](../../pipelines/pypsa-eur/import_network.py), [overlay](../../pipelines/pypsa-eur/config.gridstorm.yaml), upstream [data/versions.csv at c8209014](https://github.com/PyPSA/pypsa-eur/blob/c8209014468dbb3bf43257f45d34abc6e3c8c898/data/versions.csv) selects technology-data **v0.15.0**; [that release config](https://github.com/PyPSA/technology-data/blob/v0.15.0/config.yaml) explicitly sets **`eur_year: 2025`**. Model assumptions, not observed prices. |

The inventory was read from each committed `network.nc` via PyPSA: all static/dynamic attributes
containing `cost` were inspected. Apart from the terms listed above, there are no nonzero monetary
coefficients in these files (no dynamic cost series, quadratic marginal, spill, startup/shutdown or
storage-charging cost terms). Zero coefficients are not evidence for a real currency.

### PGLib/MATPOWER interpretation

MATPOWER defines polynomial cost `f(P) = c2*P² + c1*P + c0` in nominal `$/h`, with `P` in MW;
startup/shutdown columns are nominal US dollars. GridStorm's existing LOPF importer uses
`marginal_cost = c1 + c2*Pmax` (the secant on `[0,Pmax]`), drops `c0`, and does not model
startup/shutdown. It is exact for linear source costs, approximate for quadratic ones. The
PGLib benchmark's statistical cost-update notes are not evidence of an exchange rate or price year.
The manifest's previous `cost_currency_not_eur` flag was correct; downstream universal EUR labels
were not. No coefficient was converted in this correction.

### Belgium: three different years

The pinned [tutorial config](https://github.com/PyPSA/pypsa-eur/blob/c8209014468dbb3bf43257f45d34abc6e3c8c898/config/test/config.electricity.yaml)
uses March **2013 weather**; the embedded network metadata declares `planning_horizons: [2050]`
and `costs.year: null`, with no marginal/capital overrides and dynamic fuel prices disabled.
The 2050 technology assumptions are expressed in **2025 EUR**, as defined by technology-data
v0.15.0's `eur_year`, not in 2013 EUR and not in “2050 currency”. The retained coefficient floor
and defaults are model assumptions, not estimated market prices. Upstream
[add_electricity.py](https://github.com/PyPSA/pypsa-eur/blob/c8209014468dbb3bf43257f45d34abc6e3c8c898/scripts/add_electricity.py)
assembles fuel/efficiency/variable-O&M dispatch costs and annuitised investment/fixed-O&M costs.
Capital costs are scaled to the model horizon, per nominal power capacity (MW) or Store energy
capacity (MWh); they are not a uniform EUR/MW/year field. The GridStorm runner freezes capacities,
so none enters its dispatch objective. Analytics installed CAPEX retains those planning coefficients
and must not be added to OPEX as if both represented a full year's expenditure.

## Objective and VOLL: the mixed-label defect

Previously `voll_eur_per_mwh: 10000` was numerically added to all dataset objectives and the
assumption text called it EUR/MWh, including when generation coefficients were nominal benchmark
or illustrative units. There was no actual currency conversion. This was a scientifically
incoherent **interpretation**, not a solver arithmetic error.

The corrected contract interprets VOLL in **the dataset's own money unit/MWh**. It is a chosen
load-shedding penalty, not a calibrated economic damage estimate. Every new result embeds the
manifest `cost_basis` plus `penalties` (empty when shedding is disabled). Example:

```
pglib-case14-ieee-gen-1-outage
200 MWh × 10000 PGLib cost units/MWh = 2000000 PGLib cost units (penalty)
generation                                  =    1372.900146 PGLib cost units
total objective                             = 2001372.900146 PGLib cost units
```

Legacy field names `objective_eur`, `*_eur`, `*_eur_per_mwh` and `voll_eur_per_mwh` remain
unchanged for compatibility and stable scenario hashes. They no longer assert a currency.
No dispatch/constraint/penalty value was modified. Costs are comparable only when both runs have
the same nonempty `comparability_key`; incompatible monetary deltas are null while physical
energy/loading deltas remain available. Matching PGLib keys mean the same benchmark numerical
basis, not that benchmark systems constitute comparable real-world economies. The two illustrative
example networks have different keys even though their display-unit strings are identical.

## Before/after numerical proof

Before regeneration, all 12 original payloads were retained in the audit session. After running
`cd workers/pypsa && uv run python scripts/precompute_presets.py`, comparison of parsed JSON found
**exact equality of every objective, all 216 metric fields (including carrier maps and nulls),
all time-series and all per-asset arrays**. No tolerance was needed; this is stronger than the
requested `1e-7` relative objective/metric tolerance. Input `network.nc` files and scenario hashes
are unchanged. Result/payload hashes change because cost-basis and explanatory text are hashed;
timestamps and runtime/memory measurements are freshly measured by the generator, not scientific
changes or substituted measurements.

| Preset | Before objective | After objective | Difference |
|---|---:|---:|---:|
| ac-dc-meshed-baseline | 128678.573360 | 128678.573360 | 0 |
| ac-dc-meshed-dc-link-outage | 131950.187606 | 131950.187606 | 0 |
| pglib-case118-ieee-baseline | 93132.679288 | 93132.679288 | 0 |
| pglib-case14-ieee-baseline | 2051.526309 | 2051.526309 | 0 |
| pglib-case14-ieee-gen-1-outage | 2001372.900146 | 2001372.900146 | 0 |
| pypsa-eur-be-baseline | 56023127.857557 | 56023127.857557 | 0 |
| scigrid-de-baseline | 6684817.323607 | 6684817.323607 | 0 |
| scigrid-de-dunkelflaute-storage-off | 19614438.430578 | 19614438.430578 | 0 |
| scigrid-de-dunkelflaute-storage-on | 19272040.832661 | 19272040.832661 | 0 |
| scigrid-de-high-demand | 16337147.738097 | 16337147.738097 | 0 |
| scigrid-de-line-448-outage | 6999042.865984 | 6999042.865984 | 0 |
| scigrid-de-wind-lull | 11843595.347971 | 11843595.347971 | 0 |

Each row uses its own dataset money unit; the column is intentionally not labelled EUR.
The regenerated artifact index contains all 12 entries. All five analytics sets were cheaply
regenerated with `cd services/analytics && uv run python scripts/precompute_analytics.py`.
Cost analytics now label their legacy `*_eur` columns using the declared basis instead of
“GridStorm assumes EUR”. Unsolved OPEX remains null, not zero.

## Legacy research artifacts and remaining limitations

- Heavy pandapower/advisor studies were **not rerun**. In PGLib payloads,
  `operating_point.objective_eur_per_h` (and any related `*_eur_per_h` fields) means
  **PGLib cost units/h**, not EUR/h. This applies to both case14 and case118 artifacts. Their
  nonlinear AC-OPF objectives are not the secant-linearised DC-LOPF objectives and should not be
  compared as identical formulations. ResearchWorkbench was asked to relabel these fields.
- Raw historical stored result downloads remain byte-for-byte/hash-preserving, including historical
  assumption text. Report loading resolves absent `cost_basis` from the network catalog; it does
  not rewrite stored artifact bytes or claim a changed checksum. Stored legacy comparisons are
  hydrated with basis-aware labels on read and expose a hash of the hydrated representation.
- Historical results whose coefficient provenance differs from today's catalog cannot be fully
  recovered from a missing basis alone. New results embed provenance to avoid that ambiguity.
- VOLL sensitivity is scenario sensitivity, not a welfare/insurance-loss estimate. Benchmarks and
  examples are not inflation-adjusted economic studies. No cross-currency conversion, real-price
  calibration, or hidden exchange-rate assumption was introduced.
- New arbitrary NetCDF imports without an audited descriptor use “cost units (basis unknown)”,
  never EUR. The five bundled datasets have explicit audited descriptors preserved by their
  manifest generators. The manifest and result schema versions remain 1.0; `cost_basis` is optional
  for backward compatibility, but generated bundled results always include it.

## Verification run

All commands below were run locally on the audited changes:

| Component | Command (from component directory) | Result |
|---|---|---|
| `tests/scientific` | `uv run pytest` | 179 passed, 3 deselected |
| `tests/scientific` | `uv run pytest -m slow` | 2 passed, 180 deselected |
| `workers/pypsa` | `uv run pytest` | 40 passed |
| `packages/canonical-grid` | `uv run pytest` | 19 passed |
| `packages/stormspec` | `uv run pytest`; `uv run python scripts/export_schema.py --check` | 30 passed; schema current |
| `pipelines/network-import` | `uv run pytest` | 27 passed |
| `pipelines/pypsa-eur` | `uv run pytest` | 8 passed |
| `services/analytics` | `uv run pytest` | 53 passed |
| `services/api` | `uv run pytest tests/test_cost_basis.py tests/test_comparisons_artifacts.py tests/test_networks.py tests/test_analytics_precomputed.py` | 36 passed |
| `services/api` | `uv run pytest tests/test_cost_basis.py` after legacy assumption relabelling | 14 passed |
| All eight Python components above | `uvx ruff@0.14.0 check .`; `uvx ruff@0.14.0 format --check .` | Both pass |
| `apps/web` | `npm run gen:stormspec` | Generated the clarified VOLL field documentation |

Initial style failures were corrected without changing coefficient text values. An initial new
worker test attempted to mutate StormSpec's frozen model; it now constructs a valid disabled-shedding
scenario instead, and the final complete worker suite passes. Existing scientific tolerances and
physics/hash assertions were not weakened. Remaining warnings are upstream pandas/PyPSA/FastAPI
deprecations, not failed scientific checks.
