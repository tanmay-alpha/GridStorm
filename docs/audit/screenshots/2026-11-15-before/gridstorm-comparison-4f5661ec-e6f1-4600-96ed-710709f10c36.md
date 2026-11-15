# GridStorm comparison `4f5661ec-e6f1-4600-96ed-710709f10c36`

Network `pglib-case14-ieee` — baseline **PGLib IEEE 14-bus — baseline DC OPF** (`0137980b-a106-49ed-a292-7fa1bacf7813`, outcome feasible) vs scenario **PGLib IEEE 14-bus — loss of the main unit gen-1 (deliberate load shedding)** (`06b4f635-4eb8-4d34-99ca-362d53b88e6c`, outcome feasible).

Values are model outputs (provenance: modeled); deltas are calculated (scenario − baseline). This is not a prediction of real grid behaviour.

## Metrics

| metric | unit | baseline | scenario | delta | delta % |
|---|---|---|---|---|---|
| balance_residual_max_mw | MW | 0 | 0 | 0 | — |
| co2_emissions_t | t | — | — | — | — |
| congested_line_count | count | 0 | 0 | 0 | — |
| curtailment_mwh | MWh | 0 | 0 | 0 | — |
| generation_cost_eur | EUR | 2,052 | 1,373 | -678.6 | -33.08 |
| load_shed_hours | h | 0 | 1 | 1 | — |
| load_shedding_cost_eur | EUR | 0 | 2,000,000 | 2,000,000 | — |
| max_line_loading_pct | % | 60.66 | 8.828 | -51.83 | -85.45 |
| mean_line_loading_pct | % | 18.55 | 1.845 | -16.7 | -90.06 |
| peak_load_shed_mw | MW | 0 | 200 | 200 | — |
| served_load_mwh | MWh | 259 | 59 | -200 | -77.22 |
| storage_charge_mwh | MWh | 0 | 0 | 0 | — |
| storage_discharge_mwh | MWh | 0 | 0 | 0 | — |
| total_load_mwh | MWh | 259 | 259 | 0 | 0 |
| total_system_cost_eur | EUR | 2,052 | 2,001,373 | 1,999,321 | 9.746e+04 |
| unserved_energy_mwh | MWh | 0 | 200 | 200 | — |

## generation_by_carrier_mwh

| carrier | baseline | scenario | delta | delta % |
|---|---|---|---|---|
| NG | 259 | 59 | -200 | -77.22 |
| SYNC | 0 | 0 | 0 | — |

## curtailment_by_carrier_mwh

_no data_

## Branch loading (max over time; top 20 of 20 by |delta|)

| component | id | baseline % | scenario % | delta (pp) | outaged (b/s) |
|---|---|---|---|---|---|
| line | branch-2 | 60.66 | 4.97 | -55.69 | False/False |
| line | branch-3 | 47.53 | 4.596 | -42.94 | False/False |
| line | branch-1 | 38.42 | 1.348 | -37.08 | False/False |
| transformer | branch-10 | 36.73 | 0.7883 | -35.94 | False/False |
| transformer | branch-9 | 31.1 | 0.6413 | -30.46 | False/False |
| line | branch-4 | 33.46 | 8.828 | -24.63 | False/False |
| transformer | branch-8 | 20.03 | 0.413 | -19.62 | False/False |
| line | branch-5 | 23.53 | 6.413 | -17.11 | False/False |
| line | branch-6 | 15.8 | 4.165 | -11.63 | False/False |
| line | branch-15 | 10.58 | 0.2181 | -10.36 | False/False |
| line | branch-17 | 9.664 | 0.3706 | -9.293 | False/False |
| line | branch-13 | 8.611 | 0.142 | -8.47 | False/False |
| line | branch-7 | 9.781 | 2.374 | -7.406 | False/False |
| line | branch-12 | 7.331 | 0.0784 | -7.252 | False/False |
| line | branch-20 | 7.017 | 0.4828 | -6.534 | False/False |
| line | branch-11 | 5.105 | 0.4145 | -4.691 | False/False |
| line | branch-18 | 2.369 | 0.3939 | -1.976 | False/False |
| line | branch-16 | 1.741 | 0.1709 | -1.57 | False/False |
| line | branch-19 | 1.539 | 0.0824 | -1.457 | False/False |
| line | branch-14 | 0 | 0 | 0 | False/False |

## Assumptions

- Deltas are scenario minus baseline, computed from the stored gridstorm-result documents.
- Both runs use the same network dataset; differences reflect the scenario specification only within the stated model assumptions of each run.
- Results are model outputs (provenance: modeled); deltas are provenance: calculated. They are not observations or predictions of real grid behaviour.
- DC linearised power flow (LOPF) — no reactive power, voltage magnitudes or losses
- Kirchhoff's voltage law imposed on a cycle basis with series reactances (x_pu_eff); branch active-power flow limited to s_nom x s_max_pu
- Perfect foresight: all snapshots of the horizon are optimised jointly in one LP
- Costs are short-run marginal costs from the dataset; nodal prices are LP duals of the nodal balance constraints
- Modeled results for scenario analysis — not a validated blackout predictor or operational forecast
- Dataset dispatch set-points (p_set) released so the LOPF optimises dispatch: 5 generators
- Load shedding modelled as one dispatchable generator per load bus (11 buses), marginal cost = VOLL 10000 EUR/MWh, bounded by the bus demand at every snapshot
- Synchronous condensers (carrier SYNC) have zero active-power capacity in the dataset

## Reproducibility

Generated 2026-11-15T00:33:43.950459Z by gridstorm-api 0.1.0 (git 7c63ccaec57eddf292a287b267199132c42b7032).

### Baseline
- job: `0137980b-a106-49ed-a292-7fa1bacf7813` (live)
- scenario: `pglib-case14-ieee-baseline` hash `c78bee9b3540b8a39fecb7acaec9d2459544384ecc00aac1e968ee6c0c791d77`
- dataset: `pglib-case14-ieee` network.nc sha256 `52424e30e5375a7d8b57d66704b2c0b258c21cad65d47c223e02bad0cb056a42`
- engine: pypsa 1.4.0 (lopf)
- solver: highs 1.16.0 — optimal
- result sha256: `87386d4782ff81d62ad86460820f21c8f5cfd0a8b7d327839f742376622cd831`

<details><summary>Scenario specification (stormspec/1.0)</summary>

```json
{
  "assumptions": [],
  "dataset": {
    "network_id": "pglib-case14-ieee",
    "sha256": "52424e30e5375a7d8b57d66704b2c0b258c21cad65d47c223e02bad0cb056a42"
  },
  "description": "Single-snapshot DC optimal power flow of PGLib-OPF pglib_opf_case14_ieee (259 MW load, two dispatchable units, three synchronous condensers). MATPOWER Pg set-points are released so the dispatch is optimised.",
  "events": [],
  "execution": {
    "deterministic": true,
    "engine": "pypsa",
    "formulation": "lopf",
    "seed": 0,
    "solver": "highs",
    "solver_options": {
      "threads": 1,
      "time_limit_s": 300.0
    }
  },
  "horizon": {
    "snapshots": 1,
    "start": 0
  },
  "id": "pglib-case14-ieee-baseline",
  "mitigation": {
    "curtailment": true,
    "load_shedding": {
      "enabled": true,
      "voll_eur_per_mwh": 10000.0
    },
    "storage_dispatch": true
  },
  "name": "PGLib IEEE 14-bus — baseline DC OPF",
  "schema_version": "stormspec/1.0"
}
```
</details>

### Scenario
- job: `06b4f635-4eb8-4d34-99ca-362d53b88e6c` (live)
- scenario: `pglib-case14-ieee-gen-1-outage` hash `ba25e910a97c0caed16c841af59913905fc7d8b93f920015c8fd90c4de22d8e9`
- dataset: `pglib-case14-ieee` network.nc sha256 `52424e30e5375a7d8b57d66704b2c0b258c21cad65d47c223e02bad0cb056a42`
- engine: pypsa 1.4.0 (lopf)
- solver: highs 1.16.0 — optimal
- result sha256: `63a3817850eee0eca34e5fbee709b8a5c858c316af45dda987888bba011d57ab`

<details><summary>Scenario specification (stormspec/1.0)</summary>

```json
{
  "assumptions": [
    "Synchronous condensers (carrier SYNC) have zero active-power capacity in the dataset"
  ],
  "dataset": {
    "network_id": "pglib-case14-ieee",
    "sha256": "52424e30e5375a7d8b57d66704b2c0b258c21cad65d47c223e02bad0cb056a42"
  },
  "description": "Generator gen-1 (bus-1, 340 MW, the cheapest and largest unit) is forced out. The remaining dispatchable capacity (gen-2, 59 MW) cannot cover the 259 MW load, so the run deliberately demonstrates load shedding at VOLL (expected unserved energy = 259 - 59 = 200 MWh).",
  "events": [
    {
      "asset_id": "gen-1",
      "type": "generator_outage",
      "window": null
    }
  ],
  "execution": {
    "deterministic": true,
    "engine": "pypsa",
    "formulation": "lopf",
    "seed": 0,
    "solver": "highs",
    "solver_options": {
      "threads": 1,
      "time_limit_s": 300.0
    }
  },
  "horizon": {
    "snapshots": 1,
    "start": 0
  },
  "id": "pglib-case14-ieee-gen-1-outage",
  "mitigation": {
    "curtailment": true,
    "load_shedding": {
      "enabled": true,
      "voll_eur_per_mwh": 10000.0
    },
    "storage_dispatch": true
  },
  "name": "PGLib IEEE 14-bus — loss of the main unit gen-1 (deliberate load shedding)",
  "schema_version": "stormspec/1.0"
}
```
</details>
