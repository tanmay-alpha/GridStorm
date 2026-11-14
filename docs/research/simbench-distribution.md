# SimBench distribution AC time-series studies

## Scope and reproducibility

`workers/distribution` is an isolated Python 3.11 uv component, using SimBench **1.6.3**,
pandapower **3.5.6**, pandas **2.3.3** and numpy **2.4.6** in its committed `uv.lock`.
It runs real `pandapower.timeseries.run_timeseries` calculations, with `ConstControl` profile
updates and, for one mitigation, pandapower's existing `DERController`. It is not an OPF,
reliability estimate, observed-event reconstruction, or dynamic simulation.

```sh
cd workers/distribution
uv sync --locked
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run python scripts/run_studies.py
# One study:
uv run python scripts/run_studies.py --only lv-rural1-2-high-pv
uv run pytest -q
```

The runner executes studies serially and defaults BLAS/OpenMP thread counts to one. Set those
variables explicitly if your shell already specifies another value. No API keys or paid solvers
are needed. Each artifact under `data/artifacts/distribution/` has contract §5's envelope,
`kind: timeseries`, a canonical payload SHA-256, exact configuration, solver/version/runtime
metadata and SHA-256 hashes of the packaged source CSV tables. `index.json` lists all studies.
Wall time and creation date vary between reproductions. Because `runtime_s` is part of the payload
(as `wall_time_s` is for other engines in contract §5), `payload_sha256` changes on every rerun.
A full rerun of all nine studies reproduced every other payload field exactly. The payload
includes calculated provenance and synthetic source provenance.

## Sources, licenses and reference grid

- [SimBench v1.6.3 license](https://github.com/e2nIEE/simbench/blob/v1.6.3/LICENSE):
  **BSD-3-Clause for code**, **ODbL-1.0 for the database**, **DbCL-1.0 for individual contents**.
  The local upstream license explicitly separates these terms (lines 5–11); the database is not
  BSD-licensed. Attribution: University of Kassel, TU Dortmund, RWTH Aachen University,
  Fraunhofer Institute for Energy Economics and Energy System Technology (IEE), and individual
  contributors. The derived numerical dataset published here is offered under ODbL-1.0, with
  DbCL-1.0 applying to source database contents. See the linked license, and
  [ODbL](https://opendatacommons.org/licenses/odbl/1-0/) / [DbCL](https://opendatacommons.org/licenses/dbcl/1-0/).
- [Pinned release](https://pypi.org/project/simbench/1.6.3/) supplies both the converter and CSV
  data. The wheel hash is fixed in `uv.lock`; per-table hashes are in each artifact. The grid
  code's leading `1` denotes **data generation version 1**, not package version 1.6.3; see
  [grid extraction](https://github.com/e2nIEE/simbench/blob/v1.6.3/simbench/networks/extract_simbench_grids_from_csv.py).
- [pandapower](https://github.com/e2nIEE/pandapower) is BSD-3-Clause. It is used as a dependency;
  no upstream solver implementation is copied. See its
  [time-series documentation](https://pandapower.readthedocs.io/en/latest/timeseries.html) and
  [DER controller documentation](https://pandapower.readthedocs.io/en/latest/control/controller.html).

We use one small radial rural LV feeder in two published development scenarios:
`1-LV-rural1--0-sw` (scenario 0) and `1-LV-rural1--2-sw` (scenario 2). Both have 15 buses,
13 lines and one 0.16-MVA MV/LV transformer; scenario 0 has 13 loads and four PV units;
scenario 2 has 28 loads, eight PV units and five home-storage units. Using the same feeder
makes changes in development assumptions visible without conflating them with network size.
This is a synthetic benchmark, not a model of a named distribution utility or a national sample.

SimBench supplies **35,136** 15-minute timestamps from 2016-01-01 00:00 to 2016-12-31 23:45
(a leap year). Weekly studies use 672 steps (168 h): July 25–31 for high-load / PV-loss cases,
and May 23–29 for PV-export cases. These are selected illustrative windows, not an annual
worst-case guarantee or probability sample. Heat-wave is only a **load ×1.3 proxy**: no measured
weather, temperature-dependent conductor rating, or causal temperature-to-demand model is used.
PV capacity stress scales both installed inverter `sn_mva` and its active-power profile by 1.5.
PV loss sets PV output to zero throughout the window; it is not a protection model.

## Boundary conditions and mitigation

The default upstream slack voltage is the SimBench setpoint (1.025 pu). The PV comparison group
also has a distinct baseline at a **fixed 1.055-pu upstream MV voltage**, and uses that same
boundary for high PV and both mitigations. This is an explicit assumed upstream voltage rise,
not an observed value. Comparing high PV against the default-boundary baseline would conflate
two interventions; use `lv-rural1-2-high-mv-baseline` to isolate the PV capacity increment.

1. **Static 50% cap:** before solving, each PV profile is limited to `0.5 × sn_mva` MW.
   This is a modeled inverter-output ceiling, not a claim about current German regulation or
   net export at the feeder connection. The 70% ceiling explored previously did not bind:
   the pinned annual PV profile peaks are only approximately 0.588–0.603 MW per MVA.
   Curtailed MWh integrates the difference between uncapped and capped active-power profiles.
2. **Q(U):** existing `DERController` + `QModelQVCurve`, with deadband 0.97–1.03 pu and
   requested Q/sn points `(0.93, +0.484)` and `(1.07, -0.484)` (saturated outside).
   Pandapower's `PQVArea4105(variant=2)` further bounds reactive capability. Positive Q injects;
   negative Q absorbs. This stylised setting is not asserted to satisfy a grid code. Apparent
   power circle saturation is not enabled. Voltage improvement need not improve thermal loading:
   reactive absorption also increases current and can worsen transformer loading.

Scenario-2 storage is **held idle, P=Q=0**. In the pinned converter output its aggregate
annual active-power profile integrates to **−125.46968442591802 MWh**, while total energy capacity
is only **0.412 MWh**. Under pandapower's storage sign convention this is a large net discharge,
not a sustainable annual operating cycle. We do not infer that upstream SimBench itself is
physically invalid; the profile/conversion interpretation is unresolved. Idling storage is an
explicit study assumption, not a simulated storage mitigation. No SOC or optimal dispatch is claimed.

## Results

All values below are copied from the committed artifacts (`summary`, `convergence`, `config`).
Every study converged on all 672 steps with no unstable controller steps. No study had line
overloads or under-voltage, so those columns are omitted. Voltage extrema and loadings are
rounded to four significant digits. Hours count steps with any affected element × 0.25 h.

| Study | Window (2016) | Stress | Upstream V (pu) | V min–max (pu) | Max line (%) | Max trafo (%) | Over-voltage h (bus-steps; buses) | Trafo overload h (longest h; events) | PV MWh | Curtailed MWh | Export MWh | Losses MWh (% of load) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `lv-rural1-0-baseline` | Jul 25–31 | — | 1.025 | 1.013–1.03 | 25.33 | 42.49 | 0 | 0 | 2.849 | 0 | 1.327 | 0.09868 (2.54) |
| `lv-rural1-0-heatwave` | Jul 25–31 | load ×1.3 | 1.025 | 1.01–1.029 | 24.67 | 40.2 | 0 | 0 | 2.849 | 0 | 1.066 | 0.1054 (2.087) |
| `lv-rural1-0-pv-loss-high-load` | Jul 25–31 | load ×1.3, PV = 0 | 1.025 | 1.009–1.025 | 15.72 | 37.08 | 0 | 0 | 0 | 0 | 0 | 0.1075 (2.129) |
| `lv-rural1-2-baseline` | May 23–29 | — | 1.025 | 1.008–1.06 | 40.72 | 139.4 | 0 | 26.75 (5.0; 6) | 12.06 | 0 | 9.257 | 0.2803 (6.321) |
| `lv-rural1-2-pv-loss-high-load` | Jul 25–31 | load ×1.3, PV = 0 | 1.025 | 1.005–1.025 | 32.47 | 51.25 | 0 | 0 | 0 | 0 | 0 | 0.1086 (2.101) |
| `lv-rural1-2-high-mv-baseline` | May 23–29 | — | 1.055 | 1.038–1.089 | 39.62 | 135.6 | 0 | 25.5 (5.0; 7) | 12.06 | 0 | 9.265 | 0.2743 (6.185) |
| `lv-rural1-2-high-pv` | May 23–29 | PV ×1.5 | 1.055 | 1.038–1.108 | 61.53 | 210.0 | 17.0 (134; 2) | 45.0 (6.75; 7) | 18.1 | 0 | 14.98 | 0.5379 (12.13) |
| `lv-rural1-2-high-pv-cap50` | May 23–29 | PV ×1.5, cap 0.5·sn | 1.055 | 1.038–1.102 | 52.17 | 188.3 | 8.25 (61; 2) | 45.0 (6.75; 7) | 17.48 | 0.617 | 14.41 | 0.4957 (11.18) |
| `lv-rural1-2-high-pv-qu` | May 23–29 | PV ×1.5, Q(U) | 1.055 | 1.038–1.066 | 73.09 | 241.3 | 0 | 49.0 (7.5; 7) | 18.1 | 0 | 14.81 | 0.7086 (15.98) |

What these numbers show, within the stated model:

- **Scenario 0 (today) has no violations** in the July week, even with load ×1.3 and all PV lost
  (lowest voltage 1.009 pu against a 0.90-pu limit). Its peak transformer loading is set by PV
  export: the 0.06846-MW maximum reverse flow is ≈ 42.5 % of the 0.16-MVA rating. Removing PV
  therefore lowers peak transformer loading (42.49 → 37.08 %) despite 30 % more load. This feeder
  is not under-voltage-limited under these load proxies.
- **Scenario 2's 0.468 MVA of PV already overloads the 0.16-MVA transformer** in the May week.
  This occurs at default boundary voltage, with 26.75 h above 100 % and a 139.4 % peak. The
  0.2266-MW maximum reverse flow (≈ 142 % of rating) is of the same magnitude as that peak.
  Voltages remain inside 0.90–1.10 pu.
- Raising the upstream voltage to 1.055 pu alone shifts the voltage band up (max 1.06 → 1.089 pu)
  without creating over-voltage. Adding **PV ×1.5 (0.7023 MVA)** then produces **17 h of
  over-voltage at two end-of-feeder buses** (`LV1.101 Bus 5`/`Bus 6`, max 1.108 pu), plus
  45 h of transformer overload (peak 210 %).
- The **50 % static cap** curtails 0.617 MWh (3.4 % of the 18.1 MWh available). This halves
  over-voltage hours (17 → 8.25 h) and lowers peak transformer loading to 188.3 %. However,
  overload hours are unchanged (45 h): the cap removes only the profile peaks.
- **Q(U)** removes over-voltage entirely (max 1.066 pu). However, reactive absorption raises
  peak transformer loading to 241.3 %, overload hours to 49 h, line loading to 73.09 % and losses
  from 0.5379 to 0.7086 MWh. Voltage support trades against thermal loading here. Neither
  mitigation resolves the transformer overload, which would need reinforcement or export
  limitation at the transformer (not modeled). Q(U) controller iterations made this study's
  runtime ≈ 57 s vs ≈ 7 s for the others (single thread, this workstation).
- Losses as % of load are large in PV-export weeks because losses scale with reverse flow while
  load is the denominator. This ratio is not a feeder efficiency metric.

## Numerical interpretation and limitations

Newton–Raphson uses tolerance `1e-8 MVA`, at most 30 iterations, with numba disabled. Controller
iterations are handled by pandapower. Results are balanced, positive-sequence, quasi-static
three-phase AC power flows: no phase imbalance, dynamics, fault current, protection trips,
transformer heating, tap control or corrective load shedding. Thermal overloads remain in the
solved network; convergence does **not** mean operational feasibility or security.

Per-step series include voltage extrema, voltage-violation bus counts, maximum line and
transformer loading and overload counts, grid P/Q exchange, PV P/Q, load, losses, curtailment and
convergence. Summary durations count **steps with any affected element**, not element-hours;
separate `element_steps` and affected-element counts are also provided. Limits are taken from
SimBench bus and branch tables (fallback 0.90–1.10 pu and 100%); violations use strict inequalities.
These are instantaneous study limits, **not an EN 50160 compliance calculation**, which would
require the appropriate measurement and statistical aggregation rules. The ambiguous legacy
summary key `any_violation` is a duration in hours.

Energy is the rectangle sum `Σ P × 0.25 h`. Positive grid exchange means import; import and
export energies are accumulated separately. Failed PF or unstable-controller steps have null
physical series and are excluded from energy totals; `convergence.valid_hours` states the
coverage. Entirely unknown energy is null, not zero. Violation counts over missing steps are
unknown in substance even though no flag is accumulated. Never interpret incomplete coverage
as demonstrated absence of violations. Voltage series retain six significant digits; other
artifact values are rounded to four significant digits after metrics are computed.

There are no outage probabilities, so these are deterministic energy/violation studies, not
EENS or risk estimates. Neither extrapolation to annual violations nor utility-wide claims is supported.

## StormSpec boundary

No `run_scenario(scenario, grid_code)` shim is provided. StormSpec 1.0's `pandapower` capability
supports only `ac_pf` / `n_minus_1`, at most one snapshot, no time-windowed events, and no renewable
availability event. These studies also require a SimBench-native dataset/profile identity,
capacity scaling (distinct from availability), fixed upstream voltage and explicit controller
configuration. Accepting a StormSpec scenario here would silently bypass that contract.

Proposed future capability (not implemented): a separately declared `ac_timeseries` formulation,
canonical SimBench dataset/profile mapping with native element IDs, explicit load/PV P/Q scaling
and windows, a separate capacity-scaling event, upstream voltage boundary, and typed static-cap /
Q(U) controller settings. The existing single-snapshot adapter must remain unchanged until the
schema, validation and engine contracts support these operations together.
