# PyPSA preset benchmarks

Rows are the measurements recorded in the committed artifact headers
(`data/artifacts/pypsa/<preset>.json` → `artifact.measurements`), tabulated with the
`_write_benchmark_md` helper of `workers/pypsa/scripts/precompute_presets.py`; nothing was re-measured
for this table. The twelve original presets were measured on 2026-11-15, the three observed-analogue
presets (`observed-*`) on 2026-11-16 (UTC), on the same machine. To re-measure everything:

```
cd workers/pypsa && uv run python scripts/precompute_presets.py --out-dir ../../data/artifacts/pypsa --benchmark-md ../../docs/benchmarks/pypsa-presets.md
```

Platform: `Windows-10-10.0.26300-SP0`, CPU `Intel64 Family 6 Model 183 Stepping 1, GenuineIntel`, HiGHS single-threaded (`threads=1`). Each preset runs in a fresh Python process; peak RSS = psutil peak_wset (Windows) of that process (includes the Python interpreter, PyPSA/linopy/xarray imports, the network, the linopy model and HiGHS).

Objectives are in each network's declared cost basis (dataset manifest `cost_basis`), not a common
currency: `ac-dc-meshed` and `scigrid-de` illustrative cost units, `pglib-*` PGLib cost units
(never EUR), `pypsa-eur-be` EUR (2025). Values are not comparable across networks.

| Preset | Network | Outcome | Objective (cost-basis units) | Unserved (MWh) | Solver wall (s) | run_scenario wall (s) | Peak RSS (MB) |
|---|---|---|---:|---:|---:|---:|---:|
| `ac-dc-meshed-baseline` | ac-dc-meshed | feasible | 128,679 | 0.0 | 0.10 | 2.65 | 278 |
| `ac-dc-meshed-dc-link-outage` | ac-dc-meshed | feasible | 131,950 | 0.0 | 0.11 | 2.45 | 278 |
| `observed-dunkelflaute-2015-01-20` | scigrid-de | feasible | 59,147,318 | 2,721.0 | 3.87 | 12.76 | 550 |
| `observed-high-load-low-res-2017-01-24` | scigrid-de | feasible | 87,280,269 | 4,731.5 | 7.13 | 19.96 | 549 |
| `observed-peak-load-2017-12-13` | scigrid-de | feasible | 66,189,364 | 4,429.3 | 4.05 | 12.22 | 544 |
| `pglib-case118-ieee-baseline` | pglib-case118-ieee | feasible | 93,133 | 0.0 | 0.10 | 2.37 | 281 |
| `pglib-case14-ieee-baseline` | pglib-case14-ieee | feasible | 2,052 | 0.0 | 0.09 | 2.10 | 277 |
| `pglib-case14-ieee-gen-1-outage` | pglib-case14-ieee | feasible | 2,001,373 | 200.0 | 0.10 | 2.22 | 277 |
| `pypsa-eur-be-baseline` | pypsa-eur-be | feasible | 56,023,128 | 0.0 | 0.15 | 4.18 | 282 |
| `scigrid-de-baseline` | scigrid-de | feasible | 6,684,817 | 0.0 | 2.52 | 6.51 | 542 |
| `scigrid-de-dunkelflaute-storage-off` | scigrid-de | feasible | 19,614,438 | 190.2 | 1.21 | 5.38 | 548 |
| `scigrid-de-dunkelflaute-storage-on` | scigrid-de | feasible | 19,272,041 | 190.2 | 2.11 | 6.31 | 549 |
| `scigrid-de-high-demand` | scigrid-de | feasible | 16,337,148 | 446.7 | 2.53 | 6.41 | 545 |
| `scigrid-de-line-448-outage` | scigrid-de | feasible | 6,999,043 | 0.0 | 2.27 | 5.88 | 543 |
| `scigrid-de-wind-lull` | scigrid-de | feasible | 11,843,595 | 0.0 | 2.24 | 6.34 | 545 |

## 512 MB instance check (e.g. Render free tier)

Largest measured peak RSS: **550 MB**. Presets above 512 MB: `observed-dunkelflaute-2015-01-20`, `observed-high-load-low-res-2017-01-24`, `observed-peak-load-2017-12-13`, `scigrid-de-baseline`, `scigrid-de-dunkelflaute-storage-off`, `scigrid-de-dunkelflaute-storage-on`, `scigrid-de-high-demand`, `scigrid-de-line-448-outage`, `scigrid-de-wind-lull`. These do NOT fit a 512 MB instance for live execution; serve their precomputed artifacts instead, or run live on a larger instance.
