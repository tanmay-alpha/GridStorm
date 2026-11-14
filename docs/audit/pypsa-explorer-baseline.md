# Audit: PyPSA-Explorer baseline

Purpose: establish what open-energy-transition/PyPSA-Explorer does when run unchanged, which PyPSA
version it targets, and which of its modules GridStorm can reuse. The resulting decision is
[ADR 0002](../decisions/0002-pypsa-explorer-baseline.md); the port lives in
`services/analytics` (`gridstorm_analytics`).

## Source

| Item | Value |
|---|---|
| Repo | https://github.com/open-energy-transition/PyPSA-Explorer |
| Pinned commit | `c85252c98cab742b43245a18bcd310d095bab443` (2026-09-03, "Bump version to 0.1.2") |
| Local clone (read-only) | `D:/New folder (4)/upstream/PyPSA-Explorer` (`git clone --filter=blob:none`) |
| Licence | MIT, `LICENSE`: "Copyright (c) 2025 OET Network Viewer contributors". No NOTICE / third-party notice files are tracked (`git ls-files` shows only `LICENSE`). |
| Package version | `pypsa-explorer` 0.1.2, `requires-python = ">=3.12"` |

The MIT terms require the copyright and permission notice in copies of substantial portions. Every
derived file in `services/analytics/src/gridstorm_analytics/` carries a header naming the upstream
commit, original paths and copyright, and the licence text is shipped next to them as
`UPSTREAM_LICENSE_PyPSA-Explorer.txt` (verbatim copy of upstream `LICENSE`).

## Dependencies (`pyproject.toml`)

Runtime: `plotly>=5.0`, `dash>=2.14`, `folium>=0.14`, `mapclassify>=2.5`,
`dash-bootstrap-components>=1.5`, `pypsa>=1.0.3`, `pyyaml>=6.0`, `typer>=0.9`, `rich>=13.0`,
`ipython>=8.0`. Extras: `test` (pytest, pytest-cov, pytest-mock), `dev`, `docs`.

**Lockfile is stale.** `uv.lock` resolves PyPSA from git master
(`1.0.0rc1.post1.dev25+g0b7f9689d`, `git = "https://github.com/PyPSA/PyPSA.git?rev=master"`),
while `pyproject.toml` now declares `pypsa>=1.0.3`:

```text
$ uv sync --locked --extra test          # uv 0.11.32
Resolved 202 packages in 7.37s
error: The lockfile at `uv.lock` needs to be updated, but `--locked` was provided.
$ uv lock --check --offline
error: The lockfile at `uv.lock` needs to be updated, but `--check` was provided.
```

Root cause: the lock was not regenerated after the PyPSA dependency changed from a git source to
the PyPI range. Upstream CI cannot be reproduced with `--locked`; the lock was therefore installed
as recorded with `--frozen` (environment A) and, separately, the package was installed fresh from
PyPI (environment B).

### PyPSA version targeted

- Declared: `pypsa>=1.0.3` (no upper bound).
- Locked: PyPSA git master at `0b7f9689d` (a 1.0.0rc1 dev build).
- Code shows PyPSA ≥ 1.0 API usage: `n.c` / `c.static` (`network_loader.py`), the
  `n.statistics.<metric>.iplot.<bar|area>` plotting accessor, and a comment in
  `callbacks/network.py` ("popup and components parameters removed for PyPSA v1.0 compatibility").
- Still uses `n.component_attrs` (`utils/data_table.py:69`), which emits a `DeprecatedWarning`
  ("deprecated as of 1.0.0 and will be removed in 2.0.0").

## Test results (unchanged code)

### Environment A — upstream lock, `uv sync --frozen --extra test`

Python 3.13.9, PyPSA `1.0.0rc1.post1.dev25+g0b7f9689d`, pandas 2.3.3, dash 3.2.0, plotly 6.3.1,
numpy 2.3.3. Command: `uv run --frozen --no-sync python -m pytest -p no:cacheprovider`
(log: `upstream/_audit_logs/explorer-pytest-frozen.log`).

```text
collecting ... collected 108 items
...
================ 105 passed, 3 skipped, 25 warnings in 46.51s =================
TOTAL                                              872    410    53%
```

### Environment B — fresh install from PyPI with PyPSA 1.4.0 / pandas 3

`uv venv _explorer_fresh_venv --python 3.12` then
`uv pip install --python _explorer_fresh_venv/Scripts/python.exe "./PyPSA-Explorer[test]"`
(non-editable install of the pinned checkout). Python 3.12.13, PyPSA 1.4.0, pandas 3.1.1, dash
4.5.0, plotly 7.1.0, numpy 2.5.4. Command:
`../_explorer_fresh_venv/Scripts/python.exe -m pytest -p no:cacheprovider -v --no-cov`
(log: `upstream/_audit_logs/explorer-pytest-fresh-pypsa140.log`).

```text
collecting ... collected 108 items
...
================ 105 passed, 3 skipped, 147 warnings in 45.93s ================
```

A first attempt of this run aborted at conftest import with
`ImportError: DLL load failed while importing _imaging: The paging file is too small for this
operation to complete.` That is host memory exhaustion (≈20 parallel agents on a 16 GB host), not
an upstream defect; the rerun above succeeded unchanged.

### Failures and skips (root cause)

No test failed in either environment. The 3 skips are hard-coded in the test files:

| Test | Root cause |
|---|---|
| `tests/test_cli.py::test_cli_help` | unconditional `pytest.skip("Known issue with TyperArgument.make_metavar() in test environment")` — upstream works around a typer/click incompatibility instead of testing `--help` |
| `tests/test_theme.py::TestThemeVisualizationImpact::test_visualization_template_in_dark_mode` | `@pytest.mark.skip(reason="Requires integration with plotly config - to be implemented")`, body is `pass` |
| `tests/test_theme.py::TestThemeVisualizationImpact::test_visualization_template_in_light_mode` | same; placeholder |

Warnings worth recording: env A `RuntimeWarning: numpy.ndarray size changed, may indicate binary
incompatibility` (compiled wheel built against another numpy); both envs: 24× `component_attrs is
deprecated`; env B: 47× pandas 4 `'str' is not supported as a fill value for float64 dtype`
(`utils/data_table.py:30`, `df_reset.fillna("")` — will raise in a future pandas), plus PyPSA
internal `Pandas4Warning`s.

### What the suite does not cover

Coverage per module (env A): `callbacks/visualizations.py` **12 %**, `callbacks/network.py` 19 %,
`utils/network_loader.py` 73 %, `utils/helpers.py` 88 %. The tests per file: `test_app` 10,
`test_callbacks_data_explorer` 29, `test_cli` 22, `test_navigation` 19, `test_theme` 13,
`test_utils` 17. None of them asserts a computed number (capacity, energy, cost): the analytical
callbacks are effectively untested upstream. To close that gap for the PyPSA 1.4 question, every
statistics/plot call that `visualizations.py` makes was executed verbatim on the bundled demo
network in environment B (`upstream/_audit_logs/iplot_pypsa140.py`, log `iplot_pypsa140.log`):

```text
pypsa 1.4.0 solved True countries ['AL', 'AT', 'BA', 'BE', 'BG'] ...
OK   energy_balance.iplot.bar filter=False traces=1
OK   energy_balance.iplot.bar filter=True traces=2
OK   energy_balance.iplot.area filter=False traces=50
OK   energy_balance.iplot.area filter=True traces=80
OK   optimal_capacity.iplot.bar filter=False traces=1
OK   optimal_capacity.iplot.bar filter=True traces=2
OK   capex.iplot.bar filter=False traces=1
OK   capex.iplot.bar filter=True traces=2
OK   opex.iplot.bar filter=False traces=1
OK   opex.iplot.bar filter=True traces=2
```

(`filter=True` = `query="country in ['DE', 'FR']", facet_col="country"`, as built by
`get_country_filter`.) Conclusion: Explorer's analytical calls run on PyPSA 1.4.0 / pandas 3.

## App launch (unchanged, environment A)

```text
$ .venv/Scripts/pypsa-explorer.exe demo-network.nc:Demo --port 8050 --no-debug
WARNING:pypsa.network.io:Importing network from PyPSA version v0.28.0 while current version is v1.0.0rc1. ...
INFO:pypsa.network.io:Imported network 'Hybrid Scenario from https://www.nature.com/articles/s41560-025-01752-6' has buses, carriers, generators, global_constraints, lines, links, loads, storage_units, stores
Dash is running on http://127.0.0.1:8050/
 * Running on http://127.0.0.1:8050
INFO:werkzeug:127.0.0.1 - - [14/Nov/2026 21:40:40] "GET / HTTP/1.1" 200 -
INFO:werkzeug:127.0.0.1 - - [14/Nov/2026 21:40:52] "POST /_dash-update-component HTTP/1.1" 200 -
INFO:werkzeug:127.0.0.1 - - [14/Nov/2026 21:40:59] "POST /_dash-update-component HTTP/1.1" 200 -
```

Headless checks (curl, log `upstream/_audit_logs/explorer-launch.log`):

| Request | Result |
|---|---|
| `GET /` | HTTP 200 after ≈28 s (demo network load) |
| `GET /_dash-layout`, `GET /_dash-dependencies` | HTTP 200; 18 callbacks registered |
| `POST /_dash-update-component` → `capex-charts-container.children` (tab `capex`, all countries) | HTTP 200, 20 737 bytes, 1.52 s; Plotly bar figure with one trace per carrier (AC, Air Heat Pump, Allam Cycle, Battery Charger, …) |
| `POST /_dash-update-component` → `capacity-charts-container.children` (bus carrier `AC`) | HTTP 200, 10 334 bytes, 0.24 s; 24 bar traces |

The server was then stopped (`pkill -f pypsa-explorer`; `curl` → `000`, no process left).

Behaviour notes from the launch and source:

- `pypsa-explorer` with **no** argument starts with no network
  (`load_default_on_start=networks_input is not None` in `cli.py`); the demo network is loaded
  only via the welcome page button or when passed as an argument. `demo-network.nc` (50.5 MB,
  tracked in git, last changed 2025-10-04) is a solved PyPSA-Eur "Hybrid Scenario" network saved
  with PyPSA 0.28.
- CLI default is `--debug` (Flask debugger + reloader) on the Werkzeug development server.
- All loaded networks live in one module-level `dict` shared by every browser session; uploads are
  written to `uploaded_networks/` and opened with `pypsa.Network(path)`.

## Features (as implemented at the pinned commit)

| Feature | Implementation | Analytical core |
|---|---|---|
| Network loading | `utils/network_loader.load_networks` (path, `{label: path|Network}`, CLI `path:label`), UI upload (base64 → `uploaded_networks/`, filename sanitised against absolute paths and `..`), example button; `ensure_carriers_defined` **mutates** the network (adds missing carriers and tab10 colours) | — |
| "Comparison" / multi-network | README: "Load and compare multiple networks". Code: a network selector switches the *active* network; there is no side-by-side or difference computation (`grep -i compar src/` finds nothing) | — |
| Energy balance (time series, aggregated) | `create_energy_balance_callback`: one chart per selected bus carrier | `n.statistics.energy_balance.iplot.area/bar(bus_carrier=…, nice_names=True, query=…, facet_col=…)` |
| Capacity | `update_capacity_charts`: one chart per bus carrier | `n.statistics.optimal_capacity.iplot.bar(bus_carrier=…)` — *optimal* capacity only, i.e. 0 for an unsolved network |
| CAPEX | `update_capex_charts` | `n.statistics.capex.iplot.bar` (optimal capacity × capital cost) |
| OPEX | `update_opex_charts` | `n.statistics.opex.iplot.bar` |
| Map | `update_map` | `n.plot.explore(tooltip=True)` → folium HTML in an iframe |
| Carrier filter | global multi-select of **bus carriers** (`get_bus_carrier_options`) | passed as `bus_carrier=` |
| Country filter | `get_country_filter`: mode All/Specific → `query = "country in ['DE', ...]"`, `facet_col="country"` | pandas `query` string on the statistics frame |
| Data explorer | `callbacks/data_explorer.py` + `utils/data_table.py`: static tables and time series of any component as Dash DataTable (≤ 5000 rows) | — |
| KPI header | `layouts/components.create_header`: counts of buses, generators, lines, links, storage units | — |
| Theme / navigation | `callbacks/theme.py`, `navigation.py`, `config.py` (1579 lines, mostly CSS/HTML template and Plotly templates) | — |

Observations relevant to GridStorm:

- The analytical layer is thin: five calls into `pypsa.statistics` plus helper functions. The
  numbers come from PyPSA; Explorer contributes the *choice of views*, grouping (carrier ×
  bus carrier × country) and filter semantics.
- Statistics defaults are used as-is: `nice_names=True`, `drop_zero=True`, values rounded to
  `params.statistics.round` (5 decimals). Unsolved networks silently produce zero/empty charts.
- The country filter is a string-built pandas `query` from client-supplied values without
  escaping (`f"'{c}'"`). Values normally come from a dropdown, but Dash callbacks accept any
  client payload, so this is an expression-injection surface in a public deployment.
- Uploads have no size limit in the layout and are parsed by netCDF/HDF5 readers in the web
  process; combined with the shared network dict and the dev server this is not suitable for a
  public multi-user site (consistent with ADR 0001: no Dash in the public frontend).

## Module reuse assessment

| Upstream module | Reuse | How |
|---|---|---|
| `callbacks/visualizations.py` | **Logic ported** | statistics calls and grouping → `capacity.py`, `energy_balance.py`, `costs.py` |
| `utils/helpers.py` (`get_carrier_nice_name`, `get_country_options`, `get_bus_carrier_options`, `get_country_filter`, `summarize_network`) | **Logic ported** | `_common.py` (nice names, countries, validated filters applied to the index instead of `query` strings), `summary.py` |
| `utils/network_loader.py` (`get_unique_carriers`) | **Logic ported** | `_common.network_carriers` (read-only; GridStorm does not mutate networks on load) |
| `layouts/components.py` (`create_header` KPI counts) | Logic ported | `summary.py` counts |
| `utils/network_loader.load_networks`, `ensure_carriers_defined` | Not reused | GridStorm loads networks through its own artifact store; colour assignment is a frontend concern |
| `callbacks/data_explorer.py`, `utils/data_table.py` | Not reused | Dash DataTable-specific; the API serves component tables directly |
| `callbacks/network.py` (upload, registry, map) | Not reused | upload/session model unsuitable for the public API; map is rendered by the React frontend |
| `layouts/*`, `config.py`, `callbacks/theme.py`, `navigation.py`, `filters.py`, `app.py`, `cli.py` | Not reused | Dash UI |
| `tests/` | Not reused | they test Dash wiring, not numbers |

Depending on the `pypsa-explorer` package at runtime is not possible in the core environment:
it requires Python ≥ 3.12 (core env pins 3.11, ADR 0001) and pulls Dash, Flask, folium, ipython
and typer into the API image.

## The port: `gridstorm_analytics`

Package `services/analytics` (dist `gridstorm-analytics`, Python 3.11, `pypsa>=1.4,<1.5`,
`pandas>=3,<4`; own `pyproject.toml` + `uv.lock`). API:

```python
gridstorm_analytics.available_analytics() -> list[str]   # ["capacity", "energy_balance", "costs", "summary"]
gridstorm_analytics.KINDS                                 # same, tuple
gridstorm_analytics.compute(kind, n, *, carriers=None, countries=None) -> dict
```

Unknown kind → `UnknownAnalyticsKind` (subclass of `ValueError`); unknown/empty carrier or country
filter, or a country filter on a network without `buses.country` → `ValueError`. Every result is
strict JSON (`json.dumps(..., allow_nan=False)`) with `schema_version`, `kind`, `available`,
`reason`, `provenance: "calculated"`, `network_solved`, `filters`, `units`, `assumptions` and
`source: {upstream: "PyPSA-Explorer", url, sha, license, derived_from, engine: {name, version},
pypsa_statistics}`.

| Kind | Content | Unsolved network |
|---|---|---|
| `capacity` | per component group (Generator MW, StorageUnit MW and MWh, Store MWh, Line MVA, Transformer MVA, Link MW): rows by carrier × country with `installed_*` (`statistics.installed_capacity`) and `optimal_*` (`statistics.optimal_capacity`), `by_carrier`, totals; `generation_capacity_by_carrier_mw` | installed values; `optimal_*` = null |
| `energy_balance` | per bus carrier: rows (component, carrier, country, `energy_mwh`), `by_carrier_mwh`, `supply_mwh`, `withdrawal_mwh`, `net_mwh`, `balance_residual_max_mw`, `timeseries_mw.by_carrier`, plus `snapshots`, `snapshot_weightings_h` (`statistics.energy_balance`) | `available: false`, `reason: "network is not solved: ..."` |
| `costs` | rows by component × carrier × country with `capex_installed_eur` (`statistics.installed_capex`), `capex_optimal_eur` (`statistics.capex`, what Explorer plots), `opex_eur` (`statistics.opex`); `by_carrier`, `totals`, `objective_weighted_hours_h` | CAPEX installed only; `opex_available: false`, optimal CAPEX and OPEX null |
| `summary` | component counts, bus carriers, carriers + nice names, countries, snapshot range/hours, objective | objective null |

Sign convention (energy balance, PyPSA's): positive = supplied to a bus, negative = withdrawn
(loads, charging, branch withdrawal at a port); each branch port is booked at its own bus, so with
no carrier filter each bus carrier balances to ≈ 0 per snapshot — reported as
`balance_residual_max_mw` as a self-check. Branch capacities and costs are attributed to the
country of `bus0` (PyPSA statistics grouping).

Deliberate differences from Explorer (recorded in each result's `assumptions`): no rounding
(`round=0`), zeros kept (`drop_zero=False`), raw carrier ids plus a `carrier_names` map instead of
`nice_names=True`, installed capacity/CAPEX added so unsolved networks give real numbers, results
needing dispatch are withheld (null / `available: false`) instead of plotted as zero, filters are
validated, and the carrier filter applies to *component* carriers (the bus-carrier split is always
returned). Bus carriers whose unit is not MW-based (PyPSA-Eur `t_co2`) are listed in
`excluded_bus_carriers` instead of being reported under `_mwh` fields; `MWh_el`, `MWh_LHV`,
`MWh_th` (PyPSA-Eur labels for MW-flow buses) are included with their raw `unit`.

### Verification

`uv run pytest` in `services/analytics` (Python 3.11, PyPSA 1.4.0, pandas 3, HiGHS single-thread):

```text
45 passed, 13 warnings in 33.56s
```

Continuation verification on 2026-11-15, with `OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1`:

```text
$ uvx ruff@0.14.0 check --fix . && uvx ruff@0.14.0 format . && uv run pytest
All checks passed!
8 files left unchanged
pytest: 45 passed, 13 warnings in 20.75s
```

The upstream results and launch evidence above are preserved from the original baseline run;
they were not rerun during this continuation. Both upstream pytest summaries were checked
against their retained logs.

Tests run every kind on `pypsa.examples.ac_dc_meshed()` and `pypsa.examples.scigrid_de()`, each
unsolved and solved with HiGHS, and compare against recomputation from raw component tables
(not via `n.statistics`):

- capacity by carrier == `n.generators.groupby("carrier").p_nom.sum()`; line/transformer/link
  totals == `s_nom`/`p_nom` sums; StorageUnit energy == `Σ p_nom·max_hours`; solved: optimal ==
  `p_nom_opt`/`s_nom_opt` sums; country filter `DE` == generators on DE buses and lines with DE
  `bus0`; carrier filter.
- energy balance: per bus carrier `net_mwh` and `balance_residual_max_mw` ≤ 1e-6·supply;
  generator rows == `generators_t.p · weightings` by carrier; load rows == `−loads_t.p ·
  weightings`; time series × weightings == totals; carrier filter; unsolved → `available: false`;
  `MWh_el` included / `t_co2` excluded on a synthetic two-bus network.
- costs: installed CAPEX == `Σ nominal·capital_cost` over all six cost components; optimal CAPEX ==
  `Σ *_opt·capital_cost`; generator OPEX == `Σ generators_t.p · marginal_cost · weightings.objective`;
  `n.objective + n.objective_constant` == optimal CAPEX + OPEX; country partition (DE+NO+UK) sums to
  the unfiltered totals.
- envelope: strict JSON, provenance, upstream sha, engine version, `reason` iff unavailable.

Additional run on Explorer's `demo-network.nc` (PyPSA-Eur sector-coupled, 50 MB;
`upstream/_audit_logs/demo_ga.py`, log `demo_ga.log`):

```text
capacity: 0.22 MB JSON, 0.2s
energy_balance: 0.79 MB JSON, 0.5s bus_carriers=15 excluded=[{'bus_carrier': 'co2', 'unit': 't_co2'}, {'bus_carrier': 'co2 sequestered', 'unit': 't_co2'}, {'bus_carrier': 'co2 stored', 'unit': 't_co2'}, {'bus_carrier': 'process emissions', 'unit': 't_co2'}] max|net|/supply=1.43e-09
costs: 0.34 MB JSON, 0.4s totals={'capex_installed_eur': 112749129305.39131, 'capex_optimal_eur': 748560112233.3885, 'opex_eur': 2366894764.383436} objective=6.82145e+11 constant=5.18366e+10
summary: 0.01 MB JSON, 0.1s
filtered DE/onwind: {'onwind': 54383.22008974904} direct: 54383.22008974905
```

Open observation (not root-caused): on this demo network, solved with PyPSA-Eur/PyPSA 0.28, optimal
CAPEX + OPEX (7.509e11) exceeds `objective + objective_constant` (7.340e11) by ≈ 2.3 %, while
the identity holds exactly on both example networks solved with PyPSA 1.4. Candidate causes are
objective terms of the older model formulation that `statistics` does not reproduce; GridStorm
reports the statistics values and does not claim they equal the stored objective.
