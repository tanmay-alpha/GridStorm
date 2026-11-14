# StormBench: DC sensitivity screening versus exact N-1 power flow

## Scope and reproducibility

StormBench independently implements sparse DC matrices, PTDF and LODF with NumPy/SciPy.
The committed measurements cover six PGLib-OPF networks, including the 1,354-bus PEGASE case.
Results are calculated model outputs, not observations of grid operation or reliability predictions.

Source: [PGLib-OPF](https://github.com/power-grid-lib/pglib-opf), commit
`dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3`. The six input `.m` files and upstream license
are vendored in `benchmarks/stormbench/cases/`; each result records its input SHA-256.
The IEEE-named cases use PGLib ratings, not the often-unlimited ratings of other IEEE distributions.

From the repository root:

```sh
cd packages/stormbench
uv sync --locked
uv run --locked python ../../benchmarks/stormbench/run_benchmark.py
uv run --locked python ../../benchmarks/stormbench/make_tables.py
uv run --locked python -m pytest -q
uvx ruff@0.14.0 check --fix .
uvx ruff@0.14.0 format .
```

The full runner writes raw results to `benchmarks/stormbench/results/`, and contract §5
`kind: benchmark` envelopes plus `index.json` to `data/artifacts/stormbench/`.
For the shorter CI regeneration (defaults to case14 and case30):

```sh
uv run --locked python scripts/generate_artifacts.py --out-dir /tmp/stormbench
```

`--cases case14_ieee,case30_ieee`, `--repeats N`, and `--no-memory` are available on both runners.
A complete six-case run creates the summary/index; partial runs produce only individual artifacts.
Published measurements use three repeats, not the one-repeat configuration used in the end-to-end test.

Measured platform: Intel Core i7-14650HX, 24 logical CPUs, 15.7 GiB RAM,
Windows 10 build 26300, Python 3.11.15; NumPy 2.4.6, SciPy 1.17.1,
pandapower 3.5.6, Numba 0.68.1, psutil 7.2.2. The runner sets
`OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, and `NUMBA_NUM_THREADS`
to `1` unless already set: unset or set these to `1` before reproduction.
No random sampling is used; every in-service branch is considered and no seed is needed.
HiGHS and linear algebra are deterministic for fixed versions/platform; wall times, memory,
platform strings, timestamps, commands, and consequent payload hashes are not reproducible constants.

The tables below are transcribed from the committed `results/summary.json`; `make_tables.py`
prints the same tables. The continuation that completed this document retained the already-measured
six-case timings rather than rerunning them; it reran the component tests (17 passed).

## Model and reference methods

For branch reactance `x`, tap ratio `tau` (zero means unity), phase shift `phi`, and
oriented branch/bus incidence matrix `C`, StormBench constructs:

- `b = 1 / (x * tau)`, `Bf = diag(b) C`, `Bbus = C.T Bf`;
- `Pshift = -b * phi` (radians), including its bus-injection contribution;
- injections `(generation - demand - shunt conductance consumption) / baseMVA`.

One reference bus has fixed angle zero and absorbs active-power imbalance.
The PTDF column of this bus is zero; other columns map an injection balanced by withdrawal at
the reference bus. With `H = PTDF C.T`, the LODF is `H[k,l] / (1-H[l,l])`, with diagonal `-1`.
The outage estimate is `f_post[k,l] = f_base[k] + LODF[k,l] f_base[l]`.
Transfer sensitivities and LODFs are independent of the choice of single slack bus.

An iterative Tarjan bridge search handles parallel branches correctly. Bridge outages and
numerically singular outages (`abs(1-H[l,l]) < 1e-8`) are classified as islanding and have NaN
LODF columns, never a division by a near-zero denominator. They are counted separately and excluded
from thermal screening/reference accuracy metrics. There is no assumed redispatch, load shedding,
or converged power flow for an island; reported island injection is not unserved energy.
All committed cases have zero structural/numerical islanding classification mismatches.

The exact DC benchmark rebuilds and factorizes the reduced sparse nodal matrix independently
for every non-islanding outage; it does not reuse LODFs. Unit tests additionally compare each
non-islanding case9/case14 outage against pandapower `rundcpp` (`trafo_model="pi"`) within
`1e-8` MW absolute tolerance. PTDF/LODF tests compare with pandapower `makePTDF`/`makeLODF`.
The benchmark's exact-DC timings are for the independent sparse solver, not `rundcpp`.

The exact AC reference converts MATPOWER branches to pandapower lines/transformers/impedances,
keeps branch identities and orientation, and runs Newton-Raphson `runpp` for each non-islanding
outage. It first uses DC initialization with 30 iterations, then flat initialization with 60.
Outcomes are `converged`, `converged_retry`, or `not_converged`; base-case failure aborts the case.
AC loading uses the larger apparent power magnitude at the two branch ends (MVA), whereas
DC loading uses active power magnitude (MW) with the same rating. Generator reactive limits
are not enforced (`runpp` defaults); convergence therefore does not certify operational feasibility.
Non-convergence is a numerical outcome, not proof of voltage collapse or infeasibility.

Operating points are DC-OPF dispatches using PGLib costs approximated with ten linear segments
and SciPy HiGHS. DC N-0 security does not imply AC N-0 security. For case300, the DC-OPF dispatch
has no AC Newton solution with the attempted initializations; the runner instead uses the
published IEEE case300 dispatch and voltage set-points from `pandapower.networks.case300`.
PGLib branch ratings remain in force, and base overloads are reported explicitly.
These benchmarks use fixed dispatch (with slack balance), not post-contingency corrective OPF.

## Metrics and caveats

A contingency is flagged if a monitored, non-outaged branch that was **not already overloaded
in that model's base case** exceeds 100% after the outage. The tolerance is `1e-6` percentage
points, preventing binding OPF limits from becoming false positives due to roundoff.
`RATE_A <= 0` means unlimited/unmonitored, never a zero capacity. Tests cover this convention;
all six measured PGLib inputs have positive ratings.

Severity is the maximum loading among those same eligible branches. Consequently the eligible
branch sets can differ between AC and DC when their base-case overloads differ. These are
**new-overload** metrics, not absolute post-outage security metrics or claims that worsening
pre-existing violations are safe. AC precision/recall/rank metrics include only converged
non-islanding outages; DC counts can include outages omitted from the AC comparison.

Precision is TP/(TP+FP), recall TP/(TP+FN); undefined ratios are JSON null.
Ranking uses stable index tie-breaking, Kendall tau-b and Spearman rho.
`recall@k = |top-k(screening) intersect top-k(reference)| / k`, with `k` the number of reference
overloading contingencies (at least one); it measures top-list overlap, not binary recall.
The JSON also includes recall@10, confusion counts, and DC ranking metrics.
DC recall@k and recall@10 are 1 for all six cases. Tiny roundoff differences among tied or
nearly tied severities affect correlation even when binary classification agrees:

| case | recall@k (DC) | Kendall tau (DC) | Spearman (DC) |
|---|---|---|---|
| case14_ieee | 1 | 0.9883 | 0.9982 |
| case30_ieee | 1 | 0.995 | 0.9996 |
| case57_ieee | 1 | 0.9997 | 1 |
| case118_ieee | 1 | 0.9771 | 0.9912 |
| case300_ieee | 1 | 0.9907 | 0.9988 |
| case1354_pegase | 1 | 0.978 | 0.995 |

### Case coverage

| case | buses | branches | RATE_A=0 | islanding | screened | operating point |
|---|---|---|---|---|---|---|
| case14_ieee | 14 | 20 | 0 | 1 | 19 | dc_opf_highs |
| case30_ieee | 30 | 41 | 0 | 3 | 38 | dc_opf_highs |
| case57_ieee | 57 | 80 | 0 | 1 | 79 | dc_opf_highs |
| case118_ieee | 118 | 186 | 0 | 9 | 177 | dc_opf_highs |
| case300_ieee | 300 | 411 | 0 | 89 | 322 | ieee_published_dispatch |
| case1354_pegase | 1354 | 1991 | 0 | 561 | 1430 | dc_opf_highs |

### Numerical validation

Errors are absolute. The flow errors compare every branch flow in every non-islanding outage
against an independently factorized DC solution (outaged branch flow is zero).
Agreement is at floating-point numerical precision, not an approximation guarantee for AC.

| case | max PTDF diff vs pandapower | max LODF diff vs pandapower | max flow error vs DC re-solve (MW) | mean flow error (MW) |
|---|---|---|---|---|
| case14_ieee | 3.331e-16 | 1.887e-15 | 6.253e-13 | 3.891e-14 |
| case30_ieee | 1.776e-15 | 1.998e-15 | 7.39e-13 | 6.039e-14 |
| case57_ieee | 8.882e-16 | 9.437e-15 | 7.958e-13 | 3e-14 |
| case118_ieee | 7.784e-15 | 8.216e-15 | 3.07e-12 | 9.173e-14 |
| case300_ieee | 1.176e-13 | 2.674e-14 | 1.16e-11 | 1.341e-13 |
| case1354_pegase | 8.616e-14 | 1.19e-13 | 2.274e-10 | 8.868e-13 |

### Thermal classification and ranking

| case | overloading: screening / DC exact / AC exact | vs DC: precision | recall | vs AC: precision | recall | recall@k (AC, k) | Kendall tau (AC) | Spearman (AC) |
|---|---|---|---|---|---|---|---|---|
| case14_ieee | 1 / 1 / 1 | 1 | 1 | 1 | 1 | 1 (1) | 0.7895 | 0.8789 |
| case30_ieee | 18 / 18 / 1 | 1 | 1 | 0.05556 | 1 | 1 (1) | -0.09123 | -0.1319 |
| case57_ieee | 12 / 12 / 15 | 1 | 1 | 1 | 0.8 | 1 (15) | 0.9162 | 0.9803 |
| case118_ieee | 123 / 123 / 28 | 1 | 1 | 0.2295 | 1 | 0.5714 (28) | 0.2864 | 0.3971 |
| case300_ieee | 39 / 39 / 35 | 1 | 1 | 0.9259 | 0.7143 | 0.9143 (35) | 0.6962 | 0.8062 |
| case1354_pegase | 1157 / 1157 / 200 | 1 | 1 | 0.1698 | 0.98 | 0.745 (200) | 0.2247 | 0.3097 |

### AC convergence and new voltage-limit violations

Voltage violations use each input bus's VMIN/VMAX and `1e-6` pu tolerance. The voltage columns
count converged contingencies that newly violate a bus limit, excluding buses already in
violation in the AC base case. They are separate from thermal metrics.

| case | AC converged | converged on retry | not converged | AC base overloads | new-V-violation contingencies | of which not flagged by screening |
|---|---|---|---|---|---|---|
| case14_ieee | 19 | 0 | 0 | 0 | 3 | 2 |
| case30_ieee | 38 | 0 | 0 | 1 | 9 | 8 |
| case57_ieee | 78 | 0 | 1 | 0 | 68 | 57 |
| case118_ieee | 176 | 0 | 1 | 4 | 7 | 0 |
| case300_ieee | 306 | 0 | 16 | 4 | 116 | 103 |
| case1354_pegase | 1427 | 0 | 3 | 12 | 16 | 1 |

### Runtime and memory

Times are medians of three serial runs per complete method. Screening includes matrix
construction, factorization, sensitivities and all estimates. Exact DC reuses the base
network description; exact AC includes conversion and the base solve. Operating-point
optimization, metrics/report writing and input parsing are outside these timed regions.
No explicit Numba warm-up is excluded: the first AC repeat can include compilation, while the
median limits its influence. Ratios are specific to these implementations and workloads.

Peak memory is Python `tracemalloc` peak in a separate method pass; it is not whole-process peak
RSS and may exclude native library allocations. `psutil` reports process RSS at case end,
not the peak. The larger screening memory reflects dense PTDF/LODF/post-outage arrays despite
sparse factorization; memory scales quadratically in branch count.

| case | screening (s) | exact DC (s) | exact AC (s) | speed-up vs DC | speed-up vs AC | peak tracemalloc screening / DC / AC (MiB) | RSS end (MiB) |
|---|---|---|---|---|---|---|---|
| case14_ieee | 0.001558 | 0.008955 | 0.7393 | 6x | 475x | 0.0383 / 0.0456 / 1.47 | 249.8 |
| case30_ieee | 0.002185 | 0.0224 | 1.308 | 10x | 599x | 0.109 / 0.0972 / 1.66 | 250.7 |
| case57_ieee | 0.003066 | 0.06353 | 2.977 | 21x | 971x | 0.37 / 0.279 / 2.02 | 252.9 |
| case118_ieee | 0.004321 | 0.1433 | 6.575 | 33x | 1522x | 1.6 / 1.18 / 2.77 | 256.3 |
| case300_ieee | 0.0157 | 0.4301 | 16.22 | 27x | 1033x | 6.6 / 4.32 / 4.11 | 227.9 |
| case1354_pegase | 0.3718 | 5.2 | 93.46 | 14x | 251x | 141 / 89.8 / 7.96 | 337.1 |

## Interpretation and limitations

DC screening exactly reproduces the chosen linear DC reference to numerical precision. It does
not reproduce nonlinear AC physics. AC thermal recall is 0.8 on case57, 0.7143 on case300,
and 0.98 on PEGASE; case300 misses ten of 35 converged AC new-overload contingencies.
High recall elsewhere is not a universal safety guarantee. Case30 AC precision is only 0.05556,
and its severity ordering is weakly negative in correlation with AC. Model-specific exclusion
of pre-existing overloads also contributes to these differences.

Voltage-driven issues are outside DC's state variables: on case57, 57 of 68 converged outages
with new voltage-limit violations are not thermally flagged by screening. Reactive power,
losses, voltage magnitudes, and generator reactive limits require separate AC/operational
analysis. A thermal false positive is not evidence that an outage is harmless, and successful
AC convergence is not an all-constraints security certificate.

Islanding and AC non-convergence are explicitly retained as separate outcomes, never converted
into zero severity or silently treated as safe in quality metrics. The results describe one
operating point per case, without stochastic outage probabilities, multi-outage events,
corrective dispatch or dynamic stability. They do not establish superiority over other tools,
production readiness, or expected energy not served.

## References

- A. J. Wood, B. F. Wollenberg and G. B. Sheblé, *Power Generation, Operation, and Control*,
  3rd ed., Wiley, 2014, chapter 7 ([publisher](https://www.wiley.com/en-us/Power+Generation%2C+Operation%2C+and+Control%2C+3rd+Edition-p-9780471790556)).
- T. Güler, G. Gross and M. Liu, “Generalized line outage distribution factors,”
  *IEEE Transactions on Power Systems*, 22(2), 879–881, 2007
  ([DOI](https://doi.org/10.1109/TPWRS.2006.888950)).
- [MATPOWER manual](https://matpower.org/docs/MATPOWER-manual.pdf), DC modeling and sensitivity factors.
- [pandapower power-flow documentation](https://pandapower.readthedocs.io/en/stable/powerflow.html).
- [PGLib-OPF source and license](https://github.com/power-grid-lib/pglib-opf/tree/dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3).
