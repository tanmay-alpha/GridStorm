# Cross-engine numerical agreement

## Verdict and scope

**AGREES:** pandapower DC power flow and PyPSA LPF agree on all 20 branches of
`pglib-case14-ieee` and all 186 branches of `pglib-case118-ieee`, for both unmodified
PGLib PG/PD inputs and an explicitly balanced dispatch. The absolute tolerance is
**1e-6 MW (1 W)** for every branch flow and bus injection, and **1e-6 degrees** for
every bus angle. Maximum observed inter-engine flow difference is **4.03588e-12 MW**.
Both also agree with an independent NumPy implementation of the MATPOWER DC equations.

**EXPECTED_DIFFERENCE:** AC versus DC sending-end active-power differences reach
**11.8782 MW** (case14) and **69.4121 MW** (case118). These quantify the approximation
at the specified operating points, not cross-engine numerical disagreement or a
universal DC error bound. The AC runs ignore generator reactive limits and are **not
AC-feasibility certificates**.

**AGREES:** linear DC OPF objectives and dispatch agree between pandapower, PyPSA,
and an independently assembled SciPy LP on both cases. Although PGLib supports
quadratic costs, every quadratic coefficient in these particular source files is
zero; this is not evidence of quadratic-OPF equivalence.

Each case artifact contains 10 `AGREES`, one `EXPECTED_DIFFERENCE`, zero `DISAGREES`,
and zero `NOT_RUN` checks.

## Reproduction and evidence

From the repository root, with Python and `uv` installed:

```sh
python tests/cross_engine/run_all.py
# Optional: reproduce just one case
python tests/cross_engine/run_all.py pglib-case14-ieee
```

Prerequisites are the imported `data/networks/<id>/network.nc` files and their
`source/pglib_opf_case*.m` files. The runner does not recreate or modify imported
networks. Raw `.m` files may alternatively be read from `GRIDSTORM_PGLIB_DIR`
(default `../upstream/pglib-opf`). `GRIDSTORM_DATA_DIR` overrides the data root for
network inputs. Raw engine outputs remain in ignored `tests/cross_engine/_work/`;
`_work/tables.md` is a generated check-by-check table.

The entry script runs each engine in its own locked component environment with
`uv run --frozen --project ...`. It sets OMP, OpenBLAS, MKL and Numba threads to one,
and uses HiGHS with `threads=1, random_seed=0`. It returns nonzero on a failed step,
any `DISAGREES`/`NOT_RUN` comparison, or a physical/integrity regression failure.
No remote services are required.

Published evidence (contract §5, `kind: benchmark`):

- [case14 artifact](../../data/artifacts/cross-engine/cross-engine-pglib-case14-ieee.json)
- [case118 artifact](../../data/artifacts/cross-engine/cross-engine-pglib-case118-ieee.json)
- [artifact index](../../data/artifacts/cross-engine/index.json)

Artifacts include source and NetCDF SHA-256 hashes, harness and lockfile hashes,
engine versions, command, platform, UTC generation time, and a canonical payload
SHA-256. Metrics are computed on full-precision raw results before six-significant-digit
artifact rounding; a tiny difference is therefore not reconstructed by subtracting
rounded worst-branch flows. Timestamps/platform strings can change between runs;
last-bit floating-point differences are not promised to be bitwise reproducible.

Observed environment: Windows 10 build 26300, Python 3.11.15; pandapower **3.5.6**,
matpowercaseframes **2.1.1**, PyPSA **1.4.0**, NumPy **2.4.6**, SciPy **1.17.1**,
linopy **0.10.1**, highspy/HiGHS **1.16.0**.

Validation actually run: `python tests/cross_engine/run_all.py` completed all
engine/comparison stages and **10 unittest tests passed**. Tests include analytical
mesh splitting and tap/phase-shift redistribution; original PG versus slack
balancing; rejection of nonfinite data, injection mismatch, and unmatched dispatch;
actual engine KCL/KVL; OPF bounds, thermal limits and polynomial cost;
AC nodal balance and all-branch loss accounting; and artifact/index/input hashes.
The harness was checked/formatted using Ruff **0.14.0** in `tests/cross_engine`.

## Method and identical inputs

1. `mpc.py` parses MATPOWER v2 independently of the importer. On the pandapower
   side, `_m2ppc` (matpowercaseframes) and `from_ppc` are exactly the stages of
   `from_mpc`; splitting them allows PG replacement between parsing and conversion.
   All bus/gen/branch/gencost values are cross-checked against the independent
   parser: maximum elementwise difference is zero on both cases, after accounting
   for pandapower's zero-based bus indices and zero-tap-to-one normalization.
2. **Original PG run:** keep PGLib PG and PD unchanged. Ordinary power flow does
   not fix the reference generator's output: the single slack supplies the
   generation/load imbalance. All non-slack PG values remain fixed. Both engines
   use the PGLib reference bus (bus-1 or bus-69), not an arbitrarily selected bus.
3. **Balanced run:** start from PG and allocate `sum(PD)+sum(GS)-sum(PG)` pro rata
   to generator upward headroom (downward room for a negative residual). This is a
   different, explicitly labelled operating point, not a correction made to one
   engine to force agreement. It stays within active-power nameplate bounds before
   AC losses and supplies the operating point for the AC-versus-DC comparison.
4. PyPSA loads the actual imported NetCDF and uses its first snapshot. Generator
   and load `p_set` are explicitly set to the same harness values. The imported
   topology, branch impedances, taps and limits are not retuned. Branch orientation
   is reconciled against MATPOWER from/to buses; MATPOWER branch row IDs
   `branch-<1-based row>` retain parallel branches separately. These source-row IDs
   are unique across this source case; the general GridStorm contract only
   guarantees uniqueness within each component type.
5. Run pandapower `rundcpp`, PyPSA `lpf`, and NumPy `Bbus theta = P/baseMVA-Pbusinj`
   with `b = status/(x*tap)` and `Pfinj = -b*shift_rad`. Compare sending-end MW,
   generation-positive bus injections, and degree angles on the common reference.
   Relative error is `abs(a-b)/abs(b)` only where the reference flow magnitude is
   at least **1 MW**; near-zero branches remain in absolute-error metrics.

| Input/dispatch feature | case14 | case118 |
|---|---:|---:|
| Buses / branches / generators | 14 / 20 / 5 | 118 / 186 / 54 |
| Total PD (MW) | 259 | 4242 |
| Original total PG (MW) | 199.5 | 3257.5 |
| Lossless imbalance (MW) | 59.5 | 984.5 |
| Original-PG solved slack output (MW) | 229.5 | 1575.5 |
| Balanced nominal slack output (MW) | 220.702 | 769.615 |
| Slack Pmax (MW) | 340 | 1182 |
| Non-unity taps / phase shifters | 3 / 0 | 9 / 0 |
| Nonzero bus Bs / Gs | 1 / 0 | 14 / 0 |
| Extra parallel rows beyond unique bus pairs | 0 | 7 |

The original case118 warm-start PG would drive slack above Pmax; a converged DC
power flow does not enforce generator bounds. This is why the balanced operating
point is used for the separate approximation experiment rather than treating the
raw warm start as a feasible schedule.

## DC agreement measurements

All four rows below are **AGREES** under the flow/injection/angle tolerances above.
Relative errors are fractions, not percentages.

| Case / dispatch | Max absolute MW | Mean absolute MW | Max relative error | Max angle error (degrees) | Max injection error (MW) |
|---|---:|---:|---:|---:|---:|
| case14 / original PG | 2.84217e-13 | 5.51115e-14 | 8.72392e-15 | 2.30926e-14 | 1.70530e-13 |
| case118 / original PG | 4.03588e-12 | 4.78819e-13 | 3.58337e-13 | 4.76064e-13 | 4.54747e-12 |
| case14 / balanced | 2.84217e-13 | 5.18696e-14 | 1.81737e-14 | 1.95399e-14 | 1.70530e-13 |
| case118 / balanced | 2.55795e-12 | 2.69491e-13 | 5.27381e-13 | 2.77112e-13 | 2.27374e-12 |

Independent NumPy arbiter, maximum absolute branch-flow error (MW):

| Case / dispatch | pandapower vs reference | PyPSA vs reference | Verdict |
|---|---:|---:|---|
| case14 / original PG | 8.52651e-14 | 3.12639e-13 | AGREES |
| case118 / original PG | 3.01270e-12 | 3.63798e-12 | AGREES |
| case14 / balanced | 8.88178e-14 | 2.84217e-13 | AGREES |
| case118 / balanced | 1.64846e-12 | 1.50635e-12 | AGREES |

### Root-cause audit and sensitivity controls

No unexplained DC discrepancy was observed. Potential modelling differences were
checked rather than compensated with fitted factors:

- **Units/taps:** PyPSA `x_pu_eff * baseMVA` equals MATPOWER `x*tap` with maximum
  relative error **2.22045e-16** on each case (`AGREES`, tolerance **1e-9**).
  Lines use ohms converted from bus kV/system MVA; transformers use their own
  nameplate MVA base and bus0-side tap, as documented in the importer.
- **Different component representations:** case118 has 175 pandapower lines,
  nine transformers and two impedance elements, versus 175 PyPSA lines and eleven
  transformers. Comparing source-row identity and orientation, not component-table
  row order, gives agreement. AC losses must include the impedance elements too.
- **Parallel branches:** all seven extra parallel case118 rows remain separate;
  neither engine is compared against a collapsed equivalent circuit.
- **Shunts:** Bs is reactive and does not enter DC active-power balance; Gs is
  zero in both cases. Phase shifts and nonzero Gs are therefore **not cross-engine
  coverage claims** from these two cases. The analytical phase-shift test checks
  the independent reference's sign convention, not both engines on such a case.
- **Slack:** original PG uses the same reference bus; the balanced run removes
  the scheduled residual explicitly. No angle alignment or flow scaling is fitted.

Negative controls perturb only the independent reference at the balanced dispatch.
Ignoring all non-unity taps changes maximum branch flow by **0.703642 MW** (case14)
and **4.99190 MW** (case118), far above 1e-6 MW. Raising each branch reactance by 1%
one at a time is detected by the flow-or-angle tolerance for **19/20** and **186/186**
branches respectively. Case14 branch-14 has zero transfer in this operating point
and its reactance perturbation is unobservable; this control does not demonstrate
sensitivity to every conceivable error. Bridge flows can be KCL-fixed while their
angle drops still detect reactance changes.

## AC versus DC: quantified approximation, not feasibility

Pandapower `runpp` uses Newton-Raphson, `init='dc'`, a 50-iteration cap,
`calculate_voltage_angles=True`, PGLib Vg setpoints, and **`enforce_q_lims=False`**.
Loads and non-slack active generation equal the balanced DC run; the slack provides
AC losses. The comparison therefore includes loss redistribution as well as
voltage/reactive and nonlinear-angle effects, not solely a trigonometric truncation.

| Measurement | case14 | case118 |
|---|---:|---:|
| Maximum sending-end difference (MW) | 11.8782 | 69.4121 |
| Mean sending-end difference (MW) | 1.64768 | 3.25694 |
| 95th percentile difference (MW) | 6.17002 | 11.8193 |
| Maximum relative difference, DC >= 1 MW | 17.0777% | 139.834% |
| Largest difference divided by that branch's RATE_A | 4.04799% | 13.3853% |
| Maximum midpoint difference (MW) | 9.17742 | 69.4121 |
| Total AC branch losses (MW) | 16.0628 | 147.547 |
| AC slack output (MW) | 236.765 | 917.162 |
| AC voltage magnitude range (pu) | 0.962915–1.00000 | 0.962693–1.01383 |
| Generators exceeding Q limits | 3 | 25 |
| Largest Q-limit violation (MVAr) | 45.8675 | 158.176 |

The RATE_A row is `max_branch(abs(AC-DC)/RATE_A)*100`, not the maximum flow
error divided by a system-wide rating; it compares MW difference with the numerical
MVA rating and is not an AC apparent-power loading test. The two maxima need not
occur on the same branch. Midpoint flow is `(P_from-P_to)/2`; this removes half of
the branch's own losses but **does not remove system-wide slack loss redistribution**.
Case118 losses include all line, transformer **and impedance** branches; excluding
impedances would incorrectly report 147.327 MW instead of 147.547 MW.

Largest errors occur on branch-1 (bus-1 to bus-2) and branch-107 (bus-68 to bus-69),
both incident to the reference slack. Actual slack uplift minus total branch losses
is -4.54675e-9 MW and -1.93808e-8 MW respectively. Nodal active-power balance is
also checked by the tests. Neither case violates its bus voltage bounds in these
runs, but Q-limit violations prevent interpreting convergence as operational
feasibility. No AC OPF, constrained PV-to-PQ redispatch, or universal DC accuracy
claim is made. Verdict for each AC/DC check: **EXPECTED_DIFFERENCE**, no equality
tolerance applied.

## DC OPF consistency and cost model

Power flow and OPF are separate experiments. For OPF, loads stay at PD and generator
dispatch becomes free within Pmin/Pmax; PyPSA is reloaded and its imported `p_set`
constraints cleared. One snapshot is used; the PyPSA objective is divided by its
objective weighting to compare hourly costs. Pandapower uses `rundcopp`/PIPS,
PyPSA uses HiGHS, and the reference uses `scipy.optimize.linprog(method='highs')`.

| Check | case14 | case118 | Tolerance / verdict |
|---|---:|---:|---|
| Hourly objective (source PGLib currency units) | 2051.53 | 93132.7 | — |
| pandapower/PyPSA objective relative difference | 6.39899e-11 | 2.14171e-12 | <= 1e-6 / AGREES |
| pandapower/PyPSA maximum generator difference (MW) | 1.23718e-8 | 3.77100e-8 | <= 0.01 / AGREES |
| PyPSA/reference objective relative difference | 4.43326e-16 | 6.24997e-16 | <= 1e-6 / AGREES |
| PyPSA/reference maximum generator difference (MW) | 1.13687e-13 | 1.55609e-12 | <= 0.01 / AGREES |

The importer replaces `c2*P²+c1*P+c0` with marginal cost `c1+c2*Pmax` and drops
`c0`. The coefficient audit finds **zero** difference from that documented rule
(tolerance 1e-9 source currency/MWh). Here all c2 and c0 are zero, so objectives
really are comparable without an approximation or constant adjustment. For
quadratic costs this secant linearization changes partial-load costs and generally
the dispatch; these results must not be extrapolated to such cases. PGLib cost
numbers are retained as supplied, without claiming a currency conversion because
a pandapower/PyPSA attribute happens to be named EUR.

The independent reference imposes nodal DC balance, generator bounds and RATE_A
branch-flow limits. It, the PyPSA import, and pandapower's conversion used here do
not impose the source branch angle-difference limits. The reference optima have
maximum absolute angle differences **9.92 degrees** and **16.15 degrees**, below
the source ±30-degree limits, so that omission does not invalidate these particular
optima. The observed-engine tests independently check KCL, generator bounds,
branch ratings and evaluated polynomial cost; matching objective alone is not
accepted as proof of dispatch agreement.
