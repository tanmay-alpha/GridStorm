# AC power-flow validation and N-1 contingency screening (pandapower)

Component: `workers/pandapower` (package `gridstorm_pandapower`). Artifacts: `data/artifacts/pandapower/`
(`index.json`, `ac-reference-validation.json`, `n1-pglib-case{14,118,300}-ieee.json`).

Regenerate (single thread, about 36 s wall time for everything, imports included):

```bash
cd workers/pandapower
uv run --locked python scripts/run_studies.py                     # all three networks
uv run --locked python scripts/run_studies.py --cases pglib-case14-ieee --out-dir /tmp/pp
uv run --locked pytest -q
```

All numbers below come from the committed artifacts, produced with pandapower 3.5.4, SciPy 1.13.1,
NumPy 2.2.6, PYPOWER 5.1.21 and Python 3.11.15 on Windows 10 x64.

## 1. Method

* **Power flow.** `pandapower.runpp`: Newton-Raphson, mismatch tolerance 1e-8 MVA, at most 30
  iterations, voltage angles on, π transformer model (the same model MATPOWER uses), generator
  reactive limits **not** enforced, numba on. The options are fixed in `powerflow.PF_OPTIONS`.
* **Case loading.** MATPOWER/PGLib `.m` files are parsed with `matpowercaseframes` and converted
  with `pandapower.converter.from_ppc`. An explicit id map ties every element to the contract ids:
  `bus-<BUS_I>`, `branch-<1-based mpc.branch row>` (component `transformer` if the ratio is not 0 or 1,
  the phase shift is non-zero or the end baseKVs differ; otherwise `line`), `gen-<1-based mpc.gen row>`,
  `load-<BUS_I>`. Names are never used to recover the map.
* **Converter correction.** MATPOWER always puts the off-nominal tap at `F_BUS`. pandapower 3.5's
  `from_ppc` orders transformer buses by voltage level, and when `F_BUS` is the lower-voltage bus
  it moves the tap to the wrong side. `model.py` repairs those transformers: a from-side tap τ
  equals a to-side tap 1/τ with series impedance z·τ² and shunt b/τ². pandapower scales its
  LV-referred impedance and magnetising admittance by the LV tap factor, so setting an LV ratio tap
  of (τ − 1) and leaving vk/vkr/i0 unchanged gives MATPOWER's admittances exactly. Before this fix,
  MATPOWER `case300` (several reversed transformers) differed from PYPOWER by 0.107 pu |V|,
  2.26° and 34.7 MW of branch flow. After it, the converted bus admittance matrix equals PYPOWER's
  `makeYbus`, with max |ΔY| = 4.6e-13 pu (case300) and 5.7e-14 pu (case118). The test
  `test_converted_admittance_matrix_equals_matpower` checks this.
* **Power balance.** Σ generation − Σ load − Σ shunt P − Σ branch losses is computed from the
  result tables for every solution.

## 2. Reference validation (`ac-reference-validation.json`)

Pass tolerances: |ΔVm| ≤ 1e-6 pu, |ΔVa| ≤ 1e-4° (wrapped to [−180, 180)), branch/generator
|ΔP| ≤ 1e-3 MW, |ΔQ| ≤ 1e-3 Mvar, |balance residual| ≤ 1e-3 MW. Every case starts from a flat
start. Generator Q is compared per bus, because MATPOWER splits Q between several generators at one
PV bus in an arbitrary way.

### 2a. pandapower (with this loader) vs MATPOWER/PYPOWER

`t_case9_pf` is compared against MATPOWER's own stored solution `soln9_pf.mat` from the MATPOWER
test suite (`lib/t`). That is an independent implementation (MATLAB/Octave). The `caseN` rows
compare against PYPOWER `runpf` (Newton, `PF_TOL` = 1e-8 MVA / baseMVA) on the identical case dict.
PYPOWER is a Python port of MATPOWER, and pandapower's NR solver descends from it. These rows
therefore validate the **conversion and id map** (branch orientation, transformer model, shunts,
negative loads), not an independent NR algorithm. Files: MATPOWER `data/case*.m` at commit
`952ebcb`, vendored in `workers/pandapower/reference_data/matpower/`.

| case | max \|ΔVm\| pu | max \|ΔVa\| ° | max \|ΔP\| branch MW | max \|ΔQ\| branch Mvar | max \|ΔPg\| MW | max \|ΔQg\| bus Mvar | losses MW | balance residual MW | file Vm vs solved, pu | pass |
|---|---|---|---|---|---|---|---|---|---|---|
| t_case9_pf (vs soln9_pf.mat) | 4.4e-16 | 0 | 1.4e-13 | 8.3e-13 | 5.7e-14 | 7.1e-13 | 4.9547 | −9.7e-13 | – | ✔ |
| case9 | 2.2e-16 | 0 | 7.1e-14 | 4.3e-13 | 7.1e-14 | 3.4e-13 | 4.641 | −4.7e-13 | 0.04 | ✔ |
| case14 | 6.7e-16 | 0 | 3.9e-13 | 1.3e-12 | 1.4e-13 | 9.4e-13 | 13.393 | −2.8e-13 | 0.0013 | ✔ |
| case30 | 9.7e-11 | 1.1e-8 | 8.8e-8 | 3.4e-8 | 8.0e-8 | 1.1e-7 | 2.4438 | −7.3e-8 | 0.039 | ✔ |
| case57 | 2.0e-12 | 1.1e-10 | 1.7e-10 | 1.8e-10 | 1.0e-10 | 7.2e-11 | 27.864 | −1.4e-10 | 0.0098 | ✔ |
| case118 | 2.6e-12 | 3.0e-10 | 3.7e-9 | 6.4e-9 | 1.3e-8 | 6.8e-9 | 132.86 | −1.2e-8 | 0.017 | ✔ |
| case300 | 1.5e-13 | 1.6e-11 | 1.4e-10 | 2.0e-10 | 1.4e-10 | 2.0e-10 | 408.32 | −1.4e-10 | 0.0085 | ✔ |

The "file Vm vs solved" column compares our solution with the VM column stored in the `.m` file.
It is informational only: those stored states are not always a converged power flow (case9.m ships
flat 1.0 pu voltages, for example).

### 2b. pandapower built-in networks vs PYPOWER on the exported model

`pandapower.networks.caseN()` is solved with `runpp`, exported with `to_ppc` (π model) and re-solved
with PYPOWER.

| case | max \|ΔVm\| pu | max \|ΔVa\| ° | \|Δlosses\| MW | slack P MW | balance residual MW | vs same-named PYPOWER case, max \|ΔVm\| pu | pass |
|---|---|---|---|---|---|---|---|
| case9 | 4.4e-16 | 2.8e-14 | 6.0e-14 | 71.955 | −9.7e-13 | 2.2e-16 | ✔ |
| case14 | 6.7e-16 | 2.8e-14 | 3.6e-14 | 232.39 | 3.9e-14 | 8.9e-16 | ✔ |
| case30 | 9.7e-11 | 1.1e-8 | 7.0e-9 | 25.974 | −7.3e-8 | 9.7e-11 | ✔ |
| case57 | 5.2e-15 | 1.1e-13 | 3.0e-13 | 481.09 | −7.0e-13 | 0.216 | ✔ |
| case118 | 2.5e-12 | 2.8e-10 | 8.1e-10 | 514.13 | −1.1e-8 | 0.0136 | ✔ |
| case300 | 2.0e-14 | 1.5e-12 | 2.8e-11 | 472.01 | −7.7e-11 | 0.107 | ✔ |

The last column is a diagnostic, not a pass criterion. pandapower's bundled case57/118/300 are
not numerically the same model as PYPOWER's same-named cases (up to 0.216 pu). We did not
investigate which data differ. Use the MATPOWER files (2a), not `pandapower.networks`, whenever
MATPOWER equivalence matters.

**Summary:** all 13 comparisons pass. Worst |ΔVm| = 9.7e-11 pu, |ΔVa| = 1.1e-8°, branch
|ΔP| = 8.8e-8 MW, |balance residual| = 7.3e-8 MW.

## 3. N-1 / N-2 contingency screening

### Operating point

The generator set points shipped in PGLib files are not a secure operating point: with them the
pglib case118 base case loads branch-119 to 196.7 %. Each study therefore starts from pandapower's
AC-OPF (`runopp`, PIPS interior point; polynomial costs, RATE_A, bus voltage and generator P/Q
limits). The OPF objectives agree with the PGLib `BASELINE.md` AC values (commit `dc6be4b`):

| network | pandapower AC-OPF $/h | PGLib baseline AC $/h | OPF time s | base losses MW | base max loading % | base Vm range pu |
|---|---|---|---|---|---|---|
| pglib-case14-ieee | 2178.08 | 2178.1 | 0.21 | 15.977 | 64.81 | 1.0066–1.06 |
| pglib-case118-ieee | 97213.61 | 97214 | 0.46 | 138.685 | 100.00 | 0.9844–1.06 |
| pglib-case300-ieee | 565220.14 | 565220 | 1.47 | 423.879 | 100.00 | 0.94–1.06 |

pandapower's OPF ignores MATPOWER branch angle-difference limits (ANGMIN/ANGMAX). The study
refuses to run if the OPF fails; it never falls back to the file set points.

### Procedure and classification

Every in-service branch (line or transformer) is taken out on a deep copy of the solved base net.
NR is re-run from the base solution (`init="results"`) with the fixed options. Generators keep
their P and V set points (no re-dispatch); one slack absorbs any imbalance. Flags:

* `islanding`: a bus energised in the base case has no path to a slack
  (`pandapower.topology.unsupplied_buses`). `islanded_load_mw` is the load at those buses and
  `islanded_generation_mw` is the generation stranded there. If every slack is cut off from the
  island with the largest load, the in-service generator with the largest Pmax in that island
  becomes the slack. The old slack's island is de-energised, its pre-outage output counts as
  stranded generation, and the row carries a `slack_reassignment` record. Without this step, losing
  the slack's step-up transformer would report the whole system as islanded.
* `thermal_overload`: loading = 100·max(|S_from|, |S_to|)/RATE_A > 100.01 % (RATE_A = 0 means
  unlimited). pandapower's current-based `loading_percent` is not used.
* `voltage_violation`: an energised bus has Vm outside [VMIN − 1e-4, VMAX + 1e-4]. All three PGLib
  cases provide VMIN/VMAX for every bus. The fallback for cases without limits is [0.94, 1.06] pu.
* `non_convergent`: NR did not converge in 30 iterations. Islanding is still reported from topology.
* `error`: any other solver exception. `secure`: none of the above.

The primary `class` follows the precedence error > non_convergent > islanding > thermal_overload >
voltage_violation > secure. `classes` lists every flag that applies.

**Severity** (dimensionless; null for non_convergent/error, which rank first):

S = Σ_overloads (L/100 − 1)² + Σ_buses (ΔV/0.05)² + 100·(P_islanded + P_slack,excess)/P_load,total

Here ΔV is the distance outside the voltage band in pu, and P_slack,excess = Σ max(0, P_slack − Pmax_slack)
is the shortfall the slack cannot cover (it is not a separate class). For scale: a 120 % overload
adds 0.04, a 0.05 pu excursion adds 1, and losing 1 % of system load adds 1. Rows are ranked by S
(descending), then class precedence, then branch number. In the published studies every row with
`slack_excess_mw > 0` also carries `islanding` or `thermal_overload`.

N-2: all pairs among the 5 highest-ranked N-1 contingencies (case14 only, 10 pairs).

### Results

| network | branches (lines/trafos) | secure | thermal_overload | voltage_violation | islanding | non_convergent | error | worst finite severity | screening time s |
|---|---|---|---|---|---|---|---|---|---|
| pglib-case14-ieee | 20 (17/3) | 18 | 1 | 0 | 1 | 0 | 0 | 2.70 | 0.43 |
| pglib-case118-ieee | 186 (175/11) | 56 | 119 | 2 | 9 | 0 | 0 | 14.69 | 5.7 |
| pglib-case300-ieee | 411 (282/129) | 43 | 189 | 76 | 85 | 18 | 0 | 110.1 | 18.1 |
| case14 N-2 (10 pairs) | – | 2 | 3 | 0 | 5 | 0 | 0 | 81.5 | 0.25 |

Counts use the primary class. Screening time is the measured N-1 loop wall time from one run on
one thread; it varies between runs.

* **case14.** branch-1 (bus 1–2) overloads branch-2 to 264.4 % (S = 2.70). branch-14 islands
  bus 8, a synchronous condenser with zero P and no load, so S = 0. The worst N-2 pair is
  branch-1 + branch-2, which isolates the slack bus: gen-2 becomes the slack and would have to
  produce 270.2 MW against a Pmax of 59 MW, leaving a 211.2 MW shortfall (S = 81.5).
* **case118.** The AC-OPF base runs several branches at exactly 100 % of RATE_A, so most outages
  push some branch past the limit. 122 rows carry the overload flag, but 62 of them peak at
  ≤ 101 % and only 33 exceed 105 %. Worst: branch-104 loads branch-106 to 385.1 %, Vmin 0.9386
  (S = 14.69). branch-9 and branch-7 strand the 505 MW unit at bus 10, and the slack then exceeds
  its Pmax by about 250 MW. branch-183 islands bus 116 (184 MW of load).
* **case300.** 18 outages do not converge from the base solution. A retry with DC and flat starts
  (100 iterations each) also failed for all 18. Four of them strand large units (bus 7003:
  1401 MW, bus 241: 1127 MW, bus 236: 881 MW, bus 7017: 490 MW) whose output falls on the single
  slack. Non-convergence is not proof that no operating point exists. branch-403 (the slack's
  step-up transformer) triggers slack reassignment to gen-28, which would need 3019.6 MW against
  a Pmax of 2465 MW. The worst finite severity is branch-137 (S = 110.1): 37 MW of load islanded,
  a 897.9 MW slack shortfall, Vmin 0.784.

## 4. StormSpec adapter

`gridstorm_pandapower.run_scenario(scenario, network_dir)` handles `execution.engine == "pandapower"`
with formulations `ac_pf` and `n_minus_1`, a single snapshot, and the events `line_outage`
(line or transformer), `generator_outage` and `demand_multiplier` (constant power factor, no
windows). Everything else raises `ScenarioRejected` with code `unsupported_operation`. Results
follow `gridstorm-result/1.0` and add an `ac` block (bus vm_pu/va_deg, branch flows and loading %,
losses, violations) plus explicit assumptions.

## 5. Tests (`tests/test_ac_validation.py`, 22 tests, about 11 s)

* Reference comparison: all cases pass, balance residual < 1e-6 MW.
* Admittance-matrix equality with MATPOWER for case118 and case300.
* Id-map round trip for all six MATPOWER cases.
* A constructed 3-bus network:
  * known islanding (2 MW lost)
  * known overload (> 150 %)
  * N-2 pair count
  * base net unchanged after screening
* Secure and voltage-violation classes.
* Slack reassignment, including an exact check of the slack-shortfall severity.
* Solver-exception classification (`error`).
* Real non-convergence: load × 1e6, no mock.
* Unsupported events and formulations are rejected.
* Adapter events and AC metrics on pglib case14, plus N-1 through the adapter.
* Committed artifact integrity: `payload_sha256`, class counts sum to the contingency count, no `error`.

## 6. Limitations

* Steady-state, balanced, single-snapshot AC power flow only. No protection, dynamics,
  transient or frequency stability, and no remedial actions or re-dispatch after an outage.
* Single-slack balancing. Generator reactive limits are not enforced, so post-contingency voltages
  at PV buses are optimistic. Loads are constant power.
* Islanding treats every island without a slack as de-energised. It does not check whether an
  island with local generation could survive on its own.
* The case118 and case300 base points sit on branch limits because the OPF is not
  security-constrained. Marginal (100–101 %) overloads dominate the counts; read them together
  with the loading values.
* `non_convergent` comes from one fixed solver configuration and does not establish voltage
  collapse.
* The pandapower 3.5.x AC-OPF calls the sparse `.H` attribute (`pypower/d2Sbr_dV2.py`), which
  SciPy 1.14 removed. With SciPy 1.17.1 and pandapower 3.5.6, the OPF failed on all three PGLib
  cases. The component pins `scipy<1.14`, and uv then resolves pandapower 3.5.4 and NumPy 2.2.6.
* The PYPOWER comparison shares algorithmic ancestry with pandapower. The only fully independent
  reference is MATPOWER's stored `soln9_pf.mat` (9 buses).
