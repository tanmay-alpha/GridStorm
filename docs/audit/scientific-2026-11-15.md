# Scientific result audit — 2026-11-15

## Verdict and evidence

**All 12 committed PyPSA artifacts pass the independent offline checks.** Two small presets were solved again locally: objectives matched the committed values exactly, and all 18 metrics per result matched within the stated reproducibility tolerance. **Live scientific results remain unavailable**, not passed: the only publicly listed completed job returned HTTP 500 `artifact_missing`.

Implementation: `tests/scientific/`, its own `pyproject.toml` and `uv.lock`, with editable path dependencies on `workers/pypsa` and `packages/stormspec`. The invariant implementation does not import worker post-processing; it reads the committed NetCDF inputs through PyPSA and independently rebuilds demand, availability, event masks, bounds, storage equations and costs. Only the reproducibility tests call the worker solver.

Commands actually run from `tests/scientific`:

```sh
uv run pytest test_artifacts.py -k nonfinite -q
# Before the harness fix: 4 failed, 1 passed, 156 deselected.
uv run pytest -m '' -s -q
# After the fix: 163 passed, 1 skipped, 1 warning in 20.39s.
```

The fail-before tests exposed NaN/negative-infinity bounds and equal infinities incorrectly passing the draft harness. All five now pass by rejecting nonfinite values; assertions were not weakened. Ten additional fault-injection cases prove corrupted balance, energy, demand, generator output, branch flow, objective, CO2 semantics, solver mapping, outage output and SOC are detected. The single warning is an upstream PyPSA/Pandas `DataFrame.drop(inplace=...)` deprecation during the meshed-network rerun, not a solver failure.

Environment observed: PyPSA 1.4.0, linopy 0.10.1, highspy 1.16.0, NumPy 2.4.6, pandas 3.1.1, pytest 9.2.0.

## Committed results

All rows passed provenance, solver/outcome mapping, snapshot weights, demand, energy, balance, generator limits, branch limits/congestion, applicable storage equations, outages, objective and CO2 checks. Storage checks are explicitly not applicable on networks without StorageUnits. `null` means missing CO2-intensity data, not zero emissions.

| Artifact | Objective / total cost (EUR) | Unserved (MWh) | Weight (h) | Reported balance residual (MW) | Congested branches | CO2 (t) | Result |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ac-dc-meshed-baseline | 128678.573360 | 0 | 1 | 0 | 0 | 21266.040933 | PASS |
| ac-dc-meshed-dc-link-outage | 131950.187606 | 0 | 1 | 0 | 0 | 21289.486084 | PASS |
| pglib-case118-ieee-baseline | 93132.679288 | 0 | 1 | 0 | 2 | null | PASS |
| pglib-case14-ieee-baseline | 2051.526309 | 0 | 1 | 0 | 0 | null | PASS |
| pglib-case14-ieee-gen-1-outage | 2001372.900146 | 200 | 1 | 0 | 0 | null | PASS |
| pypsa-eur-be-baseline | 56023127.857557 | 0 | 24 | 0 | 0 | 358110.366178 | PASS* |
| scigrid-de-baseline | 6684817.323607 | 0 | 1 | 3.24e-7 | 42 | null | PASS |
| scigrid-de-dunkelflaute-storage-off | 19614438.430578 | 190.215174 | 1 | 1e-9 | 33 | null | PASS |
| scigrid-de-dunkelflaute-storage-on | 19272040.832661 | 190.215174 | 1 | 1.2e-8 | 30 | null | PASS |
| scigrid-de-high-demand | 16337147.738097 | 446.659815 | 1 | 1.4e-8 | 43 | null | PASS |
| scigrid-de-line-448-outage | 6999042.865984 | 0 | 1 | 5e-9 | 39 | null | PASS |
| scigrid-de-wind-lull | 11843595.347971 | 0 | 1 | 1e-9 | 32 | null | PASS |

\* The result schema omits `Store` dispatch (distinct from `StorageUnit`). Five Belgian H2 store buses cannot therefore be independently closed from published result primitives; the harness explicitly records their IDs as `balance_unchecked_buses` and checks the remaining buses. This is a visibility limitation, not proof of balance at those five buses. StorageUnit bounds and SOC recursion are checked for this result and all six SciGRID results.

Notable semantics checked:

- Energy and unserved energy use `sum(P_t * snapshot_weightings_h[t])`, not an unweighted snapshot sum. Belgium's weights are **24 h**, explicitly exercised by a regression test.
- Nodal balance includes generator injections, signed StorageUnit dispatch, shedding, demand, passive branch withdrawals and efficiency-adjusted link flows. Reported unrounded residual must be at most `1e-3 MW`; every committed value is below that threshold. Rounded asset reconstruction has a largest nodal residual of about `0.000348 MW`, and a largest system residual of about `0.001500 MW`; the latter accumulates independent output-rounding errors across the grid.
- Generation availability is independently `p_max_pu * p_nom`, including renewable multipliers and generator-outage windows. Demand multipliers are reconstructed against the original loads with bus/window selection.
- Passive branch limits are `abs(flow) <= s_nom * s_max_pu`, loading is `100 * abs(flow)/(s_nom*s_max_pu)`, and congestion counts **in-service lines plus transformers reaching 99.9% at any snapshot**. SciGRID baseline has 42 congested branches but only 41 congested lines; high demand has 43 versus 42; line-448 outage has 39 versus 38. These are consistent with the documented branch definition, not numerical violations.
- Storage bounds, nonnegative charge/discharge/spillage, efficiency, standing losses, inflow, weighted SOC recursion and cyclic/initial conditions are checked. Outage flows/availability are zero in their specified windows and asset flags match events.
- VER-006: `solver.objective_eur == metrics.total_system_cost_eur` exactly; `generation_cost_eur` is total operating cost excluding shedding (including applicable link/storage operating terms). The objective is also reconstructed from primitive dispatch and input marginal costs. Fixed-capacity artifacts have no additional investment constant.
- CO2 is recomputed using carrier intensity and generator efficiency when intensities exist. Missing intensities require `null` plus the data-gap warning; replacing null with zero fails the regression test.
- `ok/optimal` maps to feasible; infeasible terminations map to infeasible; other terminations map to error. Nonfeasible results must not publish objective/metrics/series/assets. All 12 observed artifacts are feasible; their mapping is checked, with an altered-termination regression case.
- `stormspec.scenario_hash` is recomputed from each preset and compared with header, payload and execution manifest. Network SHA256 is checked against the actual `data/networks/<id>/network.nc`, the dataset manifest and artifact inputs. Preset input SHA, canonical payload SHA and result SHA also recompute correctly.

## Tolerances

Series/assets are rounded to four decimal places: maximum error `5e-5` per term. Metrics are rounded to six: `5e-7`. Sum/energy/SOC tolerances propagate these errors through term counts, snapshot weights, efficiencies and costs. Bound/balance solver slack adds `max(1e-5, 1e-6 * magnitude)` MW. The reported balance-residual metric has a separate `1e-3 MW` ceiling. Loading conversion propagates flow rounding through each branch rating; aggregate loading metrics permit `0.001` percentage point. Congestion/shed-hour boundary ambiguity is limited to values within the relevant output-rounding bin; no tested violation was waived.

Local reproducibility uses relative `1e-7`, absolute `1e-5` for objective and every numeric metric, preserving `null` exactly. Timing, timestamps and result hashes are deliberately not required to reproduce; scenario and input-network hashes must reproduce. Dispatch is not required to be identical in a degenerate optimum.

## Local reproducibility

| Preset | Committed objective (EUR) | Fresh objective (EUR) | Absolute difference (EUR) | Metrics | Fresh invariants |
| --- | ---: | ---: | ---: | --- | --- |
| ac-dc-meshed-baseline | 128678.573360 | 128678.573360 | 0 | 18 matched | PASS |
| pglib-case14-ieee-baseline | 2051.526309 | 2051.526309 | 0 | 18 matched | PASS |

## Live API evidence / open issue

Public [simulation inventory](https://gridstorm-api.onrender.com/api/v1/simulations?limit=100): one listed job, one total, one completed. The completed job `2d47898b-8546-420e-a382-acc29f14d3d4` is IEEE-14 baseline. Its [result endpoint](https://gridstorm-api.onrender.com/api/v1/simulations/2d47898b-8546-420e-a382-acc29f14d3d4/result) returned **HTTP 500**, error code **`artifact_missing`**. No live physics, objective or provenance was claimed verified. The network-marked test skipped after recording that job and response, as required for unavailable 410/500 results. This reproduces [production issue #8](https://github.com/tanmay-alpha/GridStorm/issues/8); Storage and Main were notified. A fresh durable-storage result must be audited after deployment; that acceptance remains open.

## Repeatable commands

```sh
cd tests/scientific
uv run pytest                     # fast, offline committed artifacts + fault injection
uv run pytest -m slow -s           # two local real-solver reruns
uv run pytest -m network -s        # public completed jobs; 410/500 recorded as unavailable
uv run pytest -m '' -s             # all three groups
```

`GRIDSTORM_API_URL` overrides the default public API origin. The network group checks at most the explicitly requested first 100 listed jobs, fetches each retrievable completed result and its scenario, and recomputes live hashes plus the same numerical invariants. It does not create jobs or mutate production.
