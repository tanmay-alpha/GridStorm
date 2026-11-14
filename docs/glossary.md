# Glossary

Short definitions of the power-system and GridStorm terms that appear in the UI, API payloads and
docs. Units follow the field-name convention of [`architecture/contracts.md`](architecture/contracts.md)
(`_mw`, `_mwh`, `_mva`, `_pct`, `_eur_per_mwh`, …).

| Term | Definition |
|---|---|
| **AC power flow (AC PF)** | Solution of the full nonlinear power-flow equations (active *and* reactive power, voltage magnitudes and angles) for one operating point. GridStorm uses pandapower's Newton–Raphson solver (`workers/pandapower`, `workers/advisor`). No dispatch optimisation is performed. |
| **Balance residual** | `balance_residual_max_mw` = max over snapshots *and* buses of the nodal balance residual \|Σ one-port injections − Σ branch withdrawals\| [MW], recomputed from the solved LOPF outputs (`balance_residuals` in `workers/pypsa/src/gridstorm_pypsa/runner.py`). A sanity check: it must be ≈ 0 MW (solver tolerance); a large value indicates a post-processing or model error, not a physical quantity. |
| **Bus** | A node of the network (substation busbar). Ids: PyPSA component names, or `bus-<BUS_I>` for MATPOWER-derived cases. |
| **Contingency** | Unplanned loss of one (N-1) or more network elements (line, transformer, generator). |
| **Curtailment** | Available variable-renewable energy that is not used: `Σ_t max(0, P_available,t − P_dispatched,t)·Δt` [MWh] over variable generators (generators with a time-varying `p_max_pu`), `P_available = p_max_pu · p_nom`. Reported as `curtailment_mwh` and `curtailment_by_carrier_mwh`. |
| **Carrier** | Energy type of an asset (e.g. `wind`, `solar`, `gas`, `AC`). Load shedding is modelled as the carrier `load_shedding`. |
| **DC power flow / DC linearisation** | Linear approximation of AC power flow: flat voltage magnitudes (1 p.u.), small angle differences, lossless lines, no reactive power. Flows `P_ij = (θ_i − θ_j)/x_ij`. Basis of LOPF, PTDF and LODF. |
| **EENS** | Expected Energy Not Served [MWh]: `EENS = Σ_s p_s · E_unserved,s` over a complete, mutually exclusive scenario set with probabilities `p_s` summing to 1 (`packages/stormspec/src/stormspec/eens.py`). Only as meaningful as the supplied probabilities; infeasible scenarios are excluded rather than counted as zero. |
| **Islanding** | A contingency splits the network into disconnected parts. Islands without a slack/generation cannot be solved by power flow; their load is reported as disconnected/unsupplied, not silently balanced. |
| **KVL (Kirchhoff's Voltage Law)** | In DC flow: the sum of `x·P` around any network cycle is zero. PyPSA's LOPF enforces it via cycle constraints, which is why a line cannot be "switched off" for part of the horizon by setting its capacity to zero (see [engineering story](engineering-story.md#2-why-partial-window-line-outages-are-rejected-in-lopf)). |
| **Line loading** | LOPF: `loading_pct = 100 · |p0| / (s_nom · s_max_pu)` — active-power flow relative to the limit used in the optimisation (`_branch_loading` in `workers/pypsa/src/gridstorm_pypsa/runner.py`). AC PF (pandapower): `100 · |I| / I_max`. A branch with loading ≥ 99.9 % at any snapshot counts in `congested_line_count`. |
| **LODF** | Line Outage Distribution Factor: `LODF_{l,k}` = change of flow on line *l* per unit of pre-outage flow on line *k* when *k* trips: `ΔP_l = LODF_{l,k} · P_k⁰`. Derived from PTDF: `LODF_{l,k} = PTDF_{l,k} / (1 − PTDF_{k,k})` (branch-to-branch form). Undefined (`PTDF_kk = 1`) when *k* is a bridge whose loss islands the grid. |
| **LOLP** | Loss Of Load Probability: probability that some load is not served, `LOLP = Σ_s p_s · 1[E_unserved,s > 0]` over a probability-weighted scenario set. Dimensionless. |
| **LOPF** | Linear Optimal Power Flow: cost-minimising dispatch of generators, storage and (optionally) load shedding subject to DC network constraints over multiple snapshots. PyPSA builds it with linopy and GridStorm solves it with HiGHS. |
| **Marginal price (LMP)** | Dual (shadow price) of the nodal power-balance constraint [EUR/MWh]: cost of serving one more MWh at a bus. At a bus that is shedding load (and not shedding all of it) the price is set by VOLL. |
| **N-1 security** | The system stays within limits (no overloads, voltages in band, no unsupplied load) after the loss of any single element. |
| **PTDF** | Power Transfer Distribution Factor: `PTDF_{l,n}` = change of flow on line *l* for 1 MW injected at bus *n* and withdrawn at the slack bus. `PTDF = B_f · B_bus⁻¹` (reduced, slack removed) in DC flow. |
| **p.u. (per unit)** | Quantity divided by a base value (e.g. 100 MVA base, nominal voltage). |
| **rho (ρ)** | Grid2Op's line usage ratio `ρ = |I| / I_thermal`. ρ > 1 means the thermal limit is exceeded (`OVERLOAD_RHO = 1.0` in `workers/grid2op/src/gridstorm_grid2op/kpis.py`). Grid2Op disconnects lines that stay overloaded too long. |
| **Screening** | Fast approximate ranking of contingencies (e.g. by PTDF/LODF post-outage DC flows) to select candidates for exact analysis. Screening can miss violations that an AC check would find; it is not a substitute for AC N-1. |
| **Slack bus** | Reference bus whose voltage angle is fixed (θ = 0) and which absorbs the power-balance mismatch (including losses) in power flow. PTDFs are defined relative to it. |
| **Snapshot** | One time step of a multi-period model, with weighting Δt [h] (`snapshot_weightings_h`). |
| **SOC (state of charge)** | Energy stored in a storage unit [MWh] (`storage_soc_mwh`); StormSpec's `storage_state` event sets the initial SOC as a fraction of capacity (`initial_soc_fraction`). |
| **Survival (Grid2Op)** | Number of steps the operator agent played before "game over" (the grid became invalid, e.g. load or generator disconnected / power flow diverged), out of the episode's maximum steps. |
| **Unserved energy (ENS)** | `E_unserved = Σ_t P_shed,t · Δt` [MWh] (`unserved_energy_mwh`): demand that the optimiser chose to shed at VOLL because it could not be served within network and generation limits. |
| **VOLL** | Value Of Lost Load [EUR/MWh]: the cost attached to each unit of shed load (`mitigation.load_shedding.voll_eur_per_mwh`, e.g. 10 000). A modelling assumption, not an observed value; it makes shedding the last-resort option in the optimisation. |

## Provenance classes

| Class | Meaning |
|---|---|
| `observed` | Measured or published data used as-is (e.g. bus coordinates from a dataset). |
| `estimated` | Derived from observed data by a documented estimation method. |
| `synthetic` | Constructed for testing/teaching; not a real system state. |
| `modeled` | Assumed model parameters (e.g. marginal costs) or engine outputs of a model. |
| `calculated` | Deterministic arithmetic on other values (e.g. KPI aggregations). |

## References

- T. Brown, J. Hörsch, D. Schlachtberger, "PyPSA: Python for Power System Analysis", *J. Open Research Software* 6(1), 2018. <https://doi.org/10.5334/jors.188>
- L. Thurner et al., "pandapower — an open-source Python tool for convenient modeling, analysis, and optimization of electric power systems", *IEEE Trans. Power Systems* 33(6), 2018. <https://doi.org/10.1109/TPWRS.2018.2829021>
- A. Marot et al., "Learning to run a power network challenge for training topology controllers", *Electric Power Systems Research* 189, 2020 (Grid2Op / L2RPN). <https://doi.org/10.1016/j.epsr.2020.106635>
- A. J. Wood, B. F. Wollenberg, G. B. Sheblé, *Power Generation, Operation, and Control*, 3rd ed., Wiley, 2014 (DC power flow, PTDF/LODF, contingency analysis).
- R. Billinton, R. N. Allan, *Reliability Evaluation of Power Systems*, 2nd ed., Springer, 1996 (LOLP, EENS).
