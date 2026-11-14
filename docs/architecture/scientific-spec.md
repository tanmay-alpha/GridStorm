# Scientific specification — PyPSA LOPF engine

Scope: what `gridstorm_pypsa.run_scenario` (`workers/pypsa`) computes for a StormSpec 1.0 scenario
(`packages/stormspec`), how the numbers in a `gridstorm-result/1.0` are defined, and what they do
**not** mean. Interfaces are fixed in [`contracts.md`](contracts.md); per-preset wall time and
peak RSS are recorded in the artifact headers and [`../../data/artifacts/pypsa/index.json`](../../data/artifacts/pypsa/index.json).

All results are **modeled** (`provenance: "modeled"`): scenario analysis on a linearised network
model, not a validated blackout predictor or operational forecast.

## 1. Problem solved

GridStorm runs a **dispatch-only linear optimal power flow (LOPF)** with PyPSA 1.4
(`n.optimize.create_model()` + `n.optimize.solve_model(solver_name="highs", io_api="direct")`) over
the scenario horizon: all snapshots $t \in T$ of the horizon are optimised jointly in one linear
program (perfect foresight). Capacities are fixed (§5.1), so the only decision variables are
operational.

### Notation

| Symbol | Meaning | Unit | PyPSA attribute |
|---|---|---|---|
| $w_t$ | snapshot weighting (duration) | h | `snapshot_weightings.generators` / `.stores` |
| $g_{s,t}$ | generator dispatch | MW | `generators_t.p` |
| $\bar G_s$ | generator nominal power | MW | `p_nom` |
| $\underline g_{s,t}, \bar g_{s,t}$ | per-unit min/max availability | p.u. | `p_min_pu`, `p_max_pu` |
| $o_s$ | marginal cost | EUR/MWh | `marginal_cost` |
| $d_{n,t}$ | demand at bus $n$ | MW | `loads_t.p_set` (sign −1) |
| $f_{\ell,t}$ | branch active-power flow bus0 → bus1 | MW | `lines_t.p0`, `transformers_t.p0` |
| $F_\ell$, $\bar f_\ell$ | branch rating, per-unit limit | MVA, p.u. | `s_nom`, `s_max_pu` |
| $x_\ell$ | effective series reactance | p.u. | `x_pu_eff` |
| $p^{dis}_{r,t}, p^{st}_{r,t}$ | storage discharge / charge | MW | `storage_units_t.p_dispatch`, `.p_store` |
| $e_{r,t}$ | storage state of charge | MWh | `storage_units_t.state_of_charge` |
| $\eta^{st}_r, \eta^{dis}_r, \eta^{sl}_r$ | store / dispatch efficiency, standing loss | – | `efficiency_store`, `efficiency_dispatch`, `standing_loss` |
| $h_r$ | energy-to-power ratio | h | `max_hours` |
| $p^{shed}_{n,t}$ | load shed at bus $n$ | MW | generator `"<bus> load_shedding"` |
| $\mathrm{VOLL}$ | value of lost load | EUR/MWh | `mitigation.load_shedding.voll_eur_per_mwh` |

### 1.1 Objective

$$
\min \sum_{t\in T} w_t \Big[ \sum_s o_s\, g_{s,t} + \sum_r o_r\, p^{dis}_{r,t} + \sum_k o_k\, p_{k,t}
 + \sum_n \mathrm{VOLL}\; p^{shed}_{n,t} \Big]
$$

(generators $s$, storage units $r$, links $k$; PyPSA also adds any `marginal_cost_storage`,
`marginal_cost_quadratic` and spill costs present in the dataset). No capital costs enter because no
capacity is extendable (§5.1). `total_system_cost_eur` is the LP objective; `load_shedding_cost_eur`
is the VOLL term; `generation_cost_eur` = objective − shedding cost.
Docs: <https://docs.pypsa.org/latest/user-guide/optimization/objective/>.

### 1.2 Nodal power balance (Kirchhoff's current law)

For every bus $n$ and snapshot $t$:

$$
\sum_{s\in n} g_{s,t} + \sum_{r\in n}\big(p^{dis}_{r,t}-p^{st}_{r,t}\big) + p^{shed}_{n,t}
 - \sum_{\ell} K_{n\ell}\, f_{\ell,t} - \sum_{k} K^{link}_{nk,t} = d_{n,t}
$$

with $K$ the incidence matrix ($+1$ at bus0, $-1$ at bus1). For a link, $p_{1,k,t} = -\eta_k\, p_{0,k,t}$.
The bus marginal price reported as `marginal_price_eur_per_mwh` is the dual of this constraint
(EUR/MWh). Docs: <https://docs.pypsa.org/latest/user-guide/optimization/energy-balance/>.

### 1.3 Kirchhoff's voltage law — cycle formulation

PyPSA does not use voltage angles in the LOPF. For every synchronous sub-network it computes a cycle
basis $C$ (independent cycles $c$ of the AC graph of lines and transformers) and imposes

$$
\sum_{\ell} C_{\ell c}\; x_\ell\; f_{\ell,t} = 0 \qquad \forall c, t
$$

(with phase shifts of transformers added to the right-hand side). This is equivalent to the angle
formulation $f_\ell = (\theta_{bus0}-\theta_{bus1})/x_\ell$ but typically faster
(Hörsch, Ronellenfitsch, Witthaut, Brown 2018, arXiv:1704.01881).
Consequence for scenarios: an AC branch cannot be "partially" switched by setting its limit to zero
for some hours — the cycle constraints would still bind its flow through the reactances. A branch
outage therefore removes the branch from the topology (`active = False`) for the **whole horizon**,
and partial-window line/transformer/link outages are **rejected** (`unsupported_operation`).
Docs: <https://docs.pypsa.org/latest/user-guide/optimization/power-flow/>.

### 1.4 Branch and dispatch limits

$$
|f_{\ell,t}| \le \bar f_{\ell,t}\, F_\ell, \qquad
\underline g_{s,t}\,\bar G_s \le g_{s,t} \le \bar g_{s,t}\,\bar G_s, \qquad
p^{min}_{k,t} P_k \le p_{0,k,t} \le p^{max}_{k,t} P_k .
$$

Limits apply to **active power only**; `s_nom` (MVA) is used as an MW limit (§6).
Docs: <https://docs.pypsa.org/latest/user-guide/optimization/dispatch-limits/>.

### 1.5 Storage units

$$
0 \le p^{dis}_{r,t} \le \bar p_{r,t} P_r,\quad 0 \le p^{st}_{r,t} \le -\underline p_{r,t} P_r,\quad
0 \le e_{r,t} \le h_r P_r
$$

$$
e_{r,t} = (1-\eta^{sl}_r)^{w_t}\, e_{r,t-1} + w_t\Big(\eta^{st}_r\, p^{st}_{r,t} - \frac{p^{dis}_{r,t}}{\eta^{dis}_r}
 + \mathrm{inflow}_{r,t} - \mathrm{spill}_{r,t}\Big)
$$

with $e_{r,-1}$ = `state_of_charge_initial` (non-cyclic) or $e_{r,|T|-1}$ (cyclic). Reported per unit:
`p_mw` $= p^{dis}-p^{st}$ (positive = discharge to the grid), `p_dispatch_mw`, `p_store_mw`,
`spill_mw`, `soc_mwh`. `storage_discharge_mwh` $=\sum_t w_t \sum_r p^{dis}_{r,t}$,
`storage_charge_mwh` $=\sum_t w_t \sum_r p^{st}_{r,t}$. The test suite checks the recursion on the
reported numbers. Docs: <https://docs.pypsa.org/latest/user-guide/optimization/storage/>.

### 1.6 Load shedding and unserved energy

Load shedding is a dispatchable generator per load bus (carrier `load_shedding`,
$o = \mathrm{VOLL}$) bounded by the bus demand at each snapshot, $0 \le p^{shed}_{n,t} \le d_{n,t}$.

$$
E_{unserved} = \sum_{t} w_t \sum_n p^{shed}_{n,t} \;\; [\mathrm{MWh}],\qquad
\text{served} = \sum_t w_t \sum_n d_{n,t} - E_{unserved}.
$$

`peak_load_shed_mw` $=\max_t \sum_n p^{shed}_{n,t}$; `load_shed_hours` $=\sum_t w_t\,[\sum_n p^{shed}_{n,t} > 10^{-3}\,\mathrm{MW}]$.
Shedding is economic, not physical: the LP sheds where VOLL is cheaper than any feasible
re-dispatch. With load shedding disabled, a scenario whose demand cannot be met is **infeasible**
(`outcome: "infeasible"`, metrics/series/assets `null`) — never "zero unserved energy".

### 1.7 Expected energy not served (EENS)

For a complete set of mutually exclusive scenarios $k$ with probabilities $\pi_k$
(`stormspec.eens`):

$$
\mathrm{EENS} = \sum_k \pi_k\, E_{unserved,k}, \qquad \pi_k\in[0,1],\; \Big|\sum_k \pi_k - 1\Big| \le 10^{-9}.
$$

GridStorm does not estimate outage probabilities; EENS is only as meaningful as the supplied
$\pi_k$. Infeasible scenarios must not be passed in.

## 2. Derived metrics

| Metric | Definition |
|---|---|
| `total_load_mwh` | $\sum_t w_t \sum_n d_{n,t}$ after scenario events |
| `generation_by_carrier_mwh` | $\sum_t w_t \sum_{s\in c} g_{s,t}$, load-shedding generators excluded |
| `curtailment_mwh` | $\sum_t w_t \sum_{s\in V} (\bar g_{s,t}\bar G_s - g_{s,t})^+$ over **variable** generators $V$ = generators with a time series `p_max_pu` in the original dataset |
| loading of branch $\ell$ | $100\,|f_{\ell,t}| / (\bar f_{\ell,t} F_\ell)$ % (relative to the LOPF limit) |
| `max_line_loading_pct`, `mean_line_loading_pct` | max / mean over in-service lines and transformers and snapshots |
| `congested_line_count` | number of in-service branches with loading $\ge 99.9$ % in at least one snapshot |
| `co2_emissions_t` | $\sum_t w_t \sum_s g_{s,t}\, \epsilon_{c(s)} / \eta_s$ (carrier `co2_emissions` in t/MWh of primary energy); `null` when the dataset has no CO2 intensities (data gap, not zero) |
| `balance_residual_max_mw` | $\max_{n,t} \big|\sum$ one-port injections $-\sum$ branch withdrawals$\big|$ recomputed from solved outputs; must be ≈ 0 (tests require $< 10^{-3}$ MW) |

## 3. Sign conventions and units

* Generators, storage `p`: positive = injection into the bus. Loads: positive = consumption.
* Branch `flow_mw` = `p0`: power withdrawn from bus0 (positive = flow bus0 → bus1).
* Units: MW, MWh, MVA, EUR, EUR/MWh, t CO2, h; percentages in %.
* Series are rounded to 4 decimals, metrics to 6 decimals (balance residual to 9).

## 4. Scenario events → model changes

| Event / toggle | Applied as | Windows |
|---|---|---|
| `demand_multiplier` | `loads_t.p_set *= value` (all loads or loads at `buses`) | yes |
| `renewable_availability_multiplier` | `p_max_pu *= value` for variable generators of `carrier` | yes |
| `generator_outage` | `p_max_pu = p_min_pu = 0` in window (committable units rejected) | yes |
| `line_outage` (`component: line\|transformer`) | `active = False` in the chosen component list | whole horizon only |
| `link_outage` | `active = False` | whole horizon only |
| `storage_state` | `state_of_charge_initial = f · P·h`, cyclic SOC disabled | n/a |
| `storage_dispatch: false` | storage `p_min_pu = p_max_pu = 0` | – |
| `curtailment: false` | variable generators `p_min_pu = p_max_pu` (must take all available energy) | – |
| `load_shedding.enabled` | one VOLL generator per load bus (§1.6) | – |

Validation (`stormspec.validate`) rejects unknown ids (resolved per component list — SciGRID reuses
ids such as `"2"` for a line and a transformer), unknown carriers, horizons/windows outside the
dataset, and operations the engine cannot represent faithfully (`unsupported_operation`).

## 5. Assumptions applied by the adapter (always listed in `result.assumptions`)

1. **Dispatch only:** extendable capacities are fixed at the dataset `p_nom`/`s_nom`/`e_nom`
   (`*_extendable = False`); no investment decisions.
2. **Dataset global constraints removed** (e.g. the 1000 t CO2 cap of the `ac-dc-meshed` example):
   they belong to the dataset's planning study; in a dispatch run a binding emission cap would trade
   unserved energy against emissions.
3. **Dispatch set-points released:** a non-NaN `p_set` makes PyPSA fix the dispatch. Power-flow
   cases (PGLib/MATPOWER `Pg`) carry an operating point, not a must-run schedule, so `p_set` of
   generators/links/storage is cleared.
4. Cyclic storage SOC follows the dataset (`cyclic_state_of_charge`); SciGRID-DE pumped hydro is
   non-cyclic and starts empty.
5. Deterministic solve: HiGHS, `threads = 1`, `parallel = off`, `random_seed = execution.seed`,
   time limit from the scenario. Identical scenario + dataset + software ⇒ identical objective and
   `result_sha256` (sha256 of the canonical result without `manifest` and `solver.wall_time_s`).

## 6. Limitations

* **DC approximation:** no reactive power, voltage magnitudes, losses or voltage/stability limits;
  `s_nom` (MVA) is used as an active-power limit. Results can understate stress on weak/radial or
  heavily reactive networks — use the pandapower AC engine for AC checks.
* **No security constraints:** the LOPF is not N-1 secure. (The PyPSA SciGRID example applies
  `s_max_pu = 0.7` as an N-1 proxy; GridStorm keeps the dataset value 1.0 and does not add it.)
* **Perfect foresight** over the horizon; no forecast error, no unit commitment, no ramping unless
  in the dataset.
* **Synthetic stresses:** preset multipliers are illustrative, not observed events.
* **Dataset scope:** SciGRID-DE is a 2011 snapshot with stylised costs and no CO2 intensities
  (`co2_emissions_t = null`); `ac-dc-meshed` is a toy model; PGLib cases are benchmark systems with
  a single non-temporal snapshot (`"now"`).
* **Memory:** use the measured per-process peak RSS in each preset artifact's
  `artifact.measurements` before enabling live execution. Measurements include interpreter,
  imports, network, model and solver, but not the separate API server or operating-system overhead.
  A Windows working-set measurement is not proof of fit on Linux; leave additional memory headroom
  and serve large SciGRID runs precomputed on 512 MB instances.
  The committed Windows run measured SciGRID-DE presets at **541.1–549.5 MiB**, already above
  512 MiB without the API process. Small AC/DC and PGLib presets measured **276.9–280.4 MiB**.
  Header key `peak_rss_mb` uses binary MiB (`bytes / 2**20`).

## 7. Verification (automated)

`workers/pypsa/tests/test_runner.py` (real HiGHS solves on `data/networks`): result validates against
`packages/stormspec/schema/gridstorm-result-1.0.schema.json`; nodal balance residual $< 10^{-3}$ MW;
$g \le$ available capacity; storage SOC bounds and recursion; branch outage ⇒ flow 0 and other flows
change; demand ×k ⇒ total load ×k; $E_{unserved}=\sum_t w_t p^{shed}_t$ and VOLL cost; infeasible
handling (no numbers, CLI exit 0); curtailment restricted to variable generators; reproducibility of
objective and result hash; partial-window branch outage rejected; transformer/line id collision.
`tests/test_presets.py` also checks every shipped artifact's result schema, payload/result/input
hashes, index membership and measured peak RSS, the baseline-based line selection, and the
storage-dispatch mitigation pair.

## References

* T. Brown, J. Hörsch, D. Schlachtberger, "PyPSA: Python for Power System Analysis", *Journal of Open
  Research Software* 6(1), 2018. arXiv:1707.09913 — <https://arxiv.org/abs/1707.09913>
* J. Hörsch, H. Ronellenfitsch, D. Witthaut, T. Brown, "Linear optimal power flow using cycle flows",
  *Electric Power Systems Research* 158, 2018. arXiv:1704.01881 — <https://arxiv.org/abs/1704.01881>
* PyPSA documentation (1.x): <https://docs.pypsa.org/latest/> — optimisation
  [overview](https://docs.pypsa.org/latest/user-guide/optimization/overview/),
  [objective](https://docs.pypsa.org/latest/user-guide/optimization/objective/),
  [energy balance](https://docs.pypsa.org/latest/user-guide/optimization/energy-balance/),
  [power flow](https://docs.pypsa.org/latest/user-guide/optimization/power-flow/),
  [dispatch limits](https://docs.pypsa.org/latest/user-guide/optimization/dispatch-limits/),
  [storage](https://docs.pypsa.org/latest/user-guide/optimization/storage/),
  [storage units](https://docs.pypsa.org/latest/user-guide/components/storage-units/).
* HiGHS solver: Q. Huangfu, J. A. J. Hall, "Parallelizing the dual revised simplex method",
  *Mathematical Programming Computation* 10, 2018 — <https://highs.dev/>
