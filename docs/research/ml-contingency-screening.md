# ML contingency screening on simulator-generated AC N-1 labels (StormML)

`packages/stormml` asks whether a simple ML model trained on **simulator-generated** labels
ranks single-branch outages better than transparent DC-sensitivity screening, and whether it
generalises to unseen operating points and to an unseen network.

> **All labels are simulator-generated.** Every positive/negative label is the outcome of a
> pandapower Newton–Raphson AC power flow on a PGLib-OPF test case. They are not historical
> outages, operator decisions or measured events, and the networks are academic test systems.
> No dynamics, protection, remedial actions or corrective re-dispatch are modelled.

## Method

### Networks and inputs

PGLib-OPF v23.07 `pglib_opf_case{30,57,118,300}_ieee.m` (read from
`D:/New folder (4)/upstream/pglib-opf` or `data/networks/*/source`; file SHA-256 values are in
the dataset artifact). The `.m` matrices are parsed by `stormml.cases` and converted with
pandapower's own `from_ppc`; no power-flow code is re-implemented.

### Operating points (`stormml.datagen`)

Operating point = `(network, seed)`, RNG `numpy.random.default_rng([seed, crc32(network)])`.

1. **Load:** global factor $s \sim U(0.8, 1.2)$; per-bus multiplicative noise
   $\mathrm{clip}(1 + 0.05\,\mathcal{N}(0,1), 0.7, 1.3)$ on PD and QD (power factor kept).
2. **Dispatch diversity:** each generator's PGLib cost coefficients are multiplied by
   $\exp(0.1\,\mathcal{N}(0,1))$.
3. **Dispatch:** pandapower AC OPF (PIPS, flat start) with the perturbed PGLib costs,
   PMIN/PMAX, bus VMIN and an upper voltage limit of VMAX − 0.01 pu, and apparent-power branch
   limits $\max(|S_\text{from}|, |S_\text{to}|) \le \alpha\cdot\text{RATE\_A}$ with an
   operator-style N-0 security margin $\alpha \sim U(0.8, 1.0)$. `OPF_FLOW_LIM=0` (MVA) is set
   explicitly: pandapower's default is a current limit, which admits $V_\max\cdot$RATE_A MVA
   (we measured 106 % MVA loading on binding branches with the default). This needs
   SciPy < 1.14 (pandapower 3.5.x `d2Sbr_dV2` uses the sparse `.H` attribute, removed in SciPy
   1.14), hence the pin in `pyproject.toml`.
4. **Fall-backs:** PIPS fails erratically on these cases (on case300, success is not monotone in
   the margins). Attempts in fixed order: $(\alpha, 0.01)$, $(\alpha, 0)$, then $\alpha$ raised
   to 0.9, 0.95, 1.0 without the voltage margin. The realised margin and the attempt count are
   recorded per operating point.
5. **Generator Q limits are relaxed** (±1e5 Mvar) in the OPF because the labelling power flow
   does not enforce them either (`enforce_q_lims=False`) and PIPS does not converge on case300
   with them. The number of generators whose dispatched Q lies outside the PGLib limits is
   recorded per operating point. ANGMIN/ANGMAX are not enforced.
6. **Base state:** the dispatched PG and generator-bus voltages become PV set-points of an AC
   power flow (reference generator balances losses).
7. **Acceptance:** an operating point is used only if the OPF converged, the base AC power flow
   converged and the base state is **N-0 secure** (no branch > 100 % of RATE_A, no bus outside
   [VMIN, VMAX]). Rejections are counted per network and reason.

Why the dispatch step exists: the earlier version of this package scaled the PGLib/MATPOWER
reference dispatch. Those bases already violate limits (inspected records: case30 base loading
107–164 %, case57 1–7 bus-voltage violations, case300 171 % plus 45 bus-voltage violations), so
with absolute labels 94–100 % of all outages were "positive" (case118: 185/186 and 186/186;
case300: 410/411). A zero-margin AC OPF ($\alpha = 1$, no voltage margin) is secure but leaves
binding branches exactly at 100 %, so almost every outage pushes one over (smoke check: 88 %
positives on 4 case118 operating points, 81 % on 3 case300 operating points). The margins
above were chosen after inspecting label rates of such smoke-test operating points but
before any screening model was trained or evaluated; they were not tuned for screening
performance.

### Labels

For each outage of one `mpc.branch` row (AC warm-started from the base, then `dc` and `flat`
initialisation as fall-backs):

| label | definition |
| --- | --- |
| `label` (**primary**) | `thermal` OR `voltage` OR `nonconv` — absolute post-contingency violation |
| `thermal` | any remaining rated branch with $\max(|S_f|,|S_t|)/\text{RATE\_A} > 100\,\%$ |
| `voltage` | any energised bus outside the case's [VMIN, VMAX] |
| `nonconv` | AC power flow did not converge with any initialisation |
| `islanding` | diagnostic: some buses de-energised; their load (MW) is stored per row |
| `aggravated` | **secondary**: new violation, or existing one worsened by 5 pp / 0.01 pu |

Tolerances: 0.01 percentage points of loading and 1e-4 pu of voltage, identical for the base
security check and the labels. Because only N-0 secure bases are labelled, the secondary
incremental label is identical to the primary absolute label on every row (asserted in
`tests/test_artifacts.py`); it is therefore not evaluated separately. (An earlier version of this
package had silently switched the target to the incremental label; it was restored to absolute
violations as the primary target.)

### Features (base state only)

`stormml.features`: DC-LODF post-outage loading estimate from base AC active flows (maximum
over branches `dc_score`, count and sum of estimated overloads, max |LODF|), pre-contingency AC
loading of the outaged branch and its neighbours, system maximum loading, load factor,
topology (bridge flag, transformer flag, edge betweenness, end-bus degrees), voltage features
(end-bus voltage, margin to limits, system minimum margin), and relative rating/reactance. All
are dimensionless or percent; there is no network-size feature. For bridges (LODF undefined)
the DC estimate falls back to base loading and the bridge flag exposes this.

### Splits, models, metrics

* **Operating-point split:** train seeds `1_000_000 + i`, test seeds `2_000_000 + i`, all
  networks pooled. **Leave-one-network-out:** train on every operating point of the other
  networks, test on all operating points of the held-out network (case300 is the headline
  held-out network; every network is held out once). The leakage unit is the operating point;
  `stormml.splits.check_no_leakage` raises if an operating point (or, for network splits, a
  network) appears on both sides.
* **Baselines:** `dc_lodf_rule` (flag if `dc_score` > 100 %), `dc_lodf_tuned` (same score,
  F1-optimal threshold on train), `pre_loading` (pre-contingency AC loading of the outaged
  branch, F1 threshold on train).
* **ML:** `logreg` (standardised logistic regression, C = 1) and `gboost`
  (HistGradientBoosting, 300 iterations, lr 0.05, 31 leaves, seed 0); the decision threshold is
  the F1-optimal threshold on 3-fold out-of-fold predictions grouped by operating point.
* **Metrics:** PR-AUC (average precision), ROC-AUC, recall at precision ≥ 0.8/0.9, recall@k
  (share of all positives found in the top-k contingencies of their operating point, k = 5, 10,
  10 %), precision/recall/F1 at the fixed threshold, Brier score and ECE for probabilistic
  models. 95 % percentile CIs from a cluster bootstrap over **test operating points**
  (1000 resamples), and paired bootstrap differences ML − baseline on the same resamples.
* **Runtime:** sequential pandapower AC N-1 time per operating point vs feature extraction +
  model scoring per operating point (single thread).

## Dataset (real run, 2026-11-15, single thread, Windows x64, pandapower 3.5.4, SciPy 1.13.1)

| network | branches (bridges) | OPs requested | accepted | rejected: OPF not converged | accepted load factor | rows | positive | thermal | voltage | nonconv | islanding |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| case30 | 41 (3) | 60 | 33 (25 train / 8 test) | 27 | 0.803–1.038 | 1 353 | 15.1 % | 11.2 % | 4.4 % | 0 % | 7.3 % |
| case57 | 80 (1) | 60 | 44 (27 / 17) | 16 | 0.801–1.092 | 3 520 | 58.2 % | 2.8 % | 56.0 % | 1.4 % | 1.3 % |
| case118 | 186 (9) | 60 | 60 (40 / 20) | 0 | 0.812–1.184 | 11 160 | 30.5 % | 22.9 % | 12.4 % | 0.05 % | 4.8 % |
| case300 | 411 (89) | 45 | 21 (14 / 7) | 24 | 0.811–1.031 | 8 631 | 76.3 % | 32.1 % | 68.0 % | 4.1 % | 20.3 % |

Total 24 664 rows from 158 accepted operating points; no accepted point failed the base AC
power flow or the N-0 security check (all rejections are PIPS non-convergence). Fall-back
dispatch settings were needed for 5/33 (case30), 6/44 (case57), 2/60 (case118) and 14/21
(case300) accepted points, i.e. two thirds of the case300 points have no voltage margin.
**Every accepted operating point has at least one generator whose OPF reactive output is outside
its PGLib Q limits** (mean 1.0, 2.9, 19.7 and 26.0 generators per point for case30/57/118/300),
a direct consequence of relaxing Q limits. Generation wall time: 73 s, 89 s, 186 s and 335 s.
The OPF rejections are not random: they concentrate at high load (case30 accepts nothing above
s = 1.04, case300 nothing above 1.03), so the accepted sets do not cover the requested 0.8–1.2
range for case30, case57 and case300.

## Results (`ml-screening-results.json`, 1000 operating-point bootstrap resamples)

PR-AUC must be read against the test prevalence (a random ranking scores ≈ prevalence).
Recall@10 per operating point is capped by the number of positives per point (oracle cap
given); with hundreds of positives per case300 point it carries almost no information.

### Operating-point split (all four networks pooled; test prevalence 0.509)

| model | PR-AUC [95 % CI] | ROC-AUC | recall @ precision ≥ 0.9 [CI] | P / R / F1 at threshold | Brier / ECE |
| --- | --- | --- | --- | --- | --- |
| dc_lodf_rule (> 100 %) | 0.765 [0.685, 0.821] | 0.690 | 0.278 [0.233, 0.464] | 0.999 / 0.256 / 0.407 | — |
| dc_lodf_tuned | 0.765 [0.685, 0.821] | 0.690 | 0.278 [0.233, 0.464] | 0.637 / 0.658 / 0.648 | — |
| pre_loading | 0.641 [0.573, 0.702] | 0.617 | 0.019 [0.003, 0.049] | 0.510 / 1.000 / 0.675 | — |
| logreg | 0.912 [0.883, 0.933] | 0.903 | 0.649 [0.546, 0.746] | 0.763 / 0.908 / 0.829 | 0.126 / 0.029 |
| gboost | **0.973** [0.956, 0.985] | 0.973 | **0.927** [0.867, 0.966] | 0.895 / 0.930 / 0.913 | 0.064 / 0.013 |

Paired PR-AUC differences: gboost − DC +0.208 [0.158, 0.282], logreg − DC +0.148
[0.101, 0.210], gboost − pre-loading +0.332 [0.274, 0.401]. Much of the gap is voltage
violations, which a DC flow estimate cannot see: at its threshold the DC rule catches 52 % of
thermal-positive and 14 % of voltage-positive outages, gboost 97 % and 93 %. On the
**thermal-only target** (non-converged rows excluded, prevalence 0.236) DC-LODF is strong
(PR-AUC 0.858 [0.804, 0.908], ROC 0.934; the 100 % rule has precision 0.999) and gboost still
improves it (0.970 [0.952, 0.988]; paired +0.113 [0.076, 0.157]); logreg's gain over DC is
+0.050 [0.020, 0.079] in PR-AUC but not significant in recall @ precision 0.9
(+0.117 [−0.011, 0.203]).

### Leave-one-network-out (label = primary absolute violation)

| held-out network (prevalence) | DC-LODF PR-AUC / ROC | pre-loading PR-AUC / ROC | logreg PR-AUC / ROC | gboost PR-AUC / ROC | logreg − DC PR-AUC [CI] | gboost − DC PR-AUC [CI] |
| --- | --- | --- | --- | --- | --- | --- |
| **case300** (0.763) | 0.851 / 0.617 | 0.874 / 0.686 | **0.898** / 0.722 | 0.864 / 0.647 | +0.046 [0.025, 0.073] | +0.013 [−0.007, 0.036] |
| case118 (0.305) | 0.831 / 0.853 | 0.623 / 0.805 | **0.886** / 0.921 | 0.873 / 0.908 | +0.056 [0.029, 0.081] | +0.042 [0.019, 0.064] |
| case57 (0.582) | 0.678 / 0.546 | 0.606 / 0.528 | 0.774 / 0.677 | **0.838** / 0.779 | +0.096 [0.061, 0.136] | +0.160 [0.095, 0.229] |
| case30 (0.151) | 0.824 / 0.889 | 0.495 / 0.841 | **0.841** / 0.920 | 0.831 / 0.909 | +0.017 [0.003, 0.052] | +0.007 [0.002, 0.021] |

Further LONO findings (all from the same artifact):

* **case300 (the assigned unseen network):** gradient boosting does **not** beat the
  baselines — it is indistinguishable from DC-LODF and *worse* than the pre-loading heuristic
  (PR-AUC −0.010 [−0.017, −0.003], ROC −0.038 [−0.053, −0.025]). Logistic regression is
  modestly better than both (vs pre-loading +0.023 [0.015, 0.034]); its recall at precision
  ≥ 0.9 is 0.431 vs 0.216 for DC (paired +0.215 [−0.0, 0.296], CI touches 0). All ROC-AUCs are
  ≤ 0.72. At the thresholds transferred from the other networks, pre-loading has the best F1
  (0.675) ahead of logreg (0.633) and gboost (0.615).
* **Thresholds do not transfer.** The fixed physical DC rule (> 100 %) has a higher F1 than
  both ML models on held-out case118 (0.713 vs 0.683/0.688) and case30 (0.828 vs 0.615/0.521);
  the F1-tuned DC threshold learnt on other networks collapses (case118: 25 %, flags every
  outage, F1 0.468).
* **Calibration does not transfer:** ECE 0.010–0.029 in the operating-point split, 0.16–0.47
  on held-out networks (case300: 0.36 logreg / 0.38 gboost), partly due to the prevalence shift
  (case300 train prevalence 0.35, test 0.76).
* Recall@10 per operating point is bounded by the oracle cap (pooled split 0.116, case118
  0.176, case300 0.032, case57 0.215, case30 1.0). Every model except pre-loading is at the
  cap on held-out case118 and case300; on case57 DC and ML reach 0.146–0.152 (pre-loading
  0.128) of 0.215; on
  case30 logreg 0.882, gboost 0.770, DC 0.730, pre-loading 0.647; in the pooled split gboost
  0.116, logreg 0.110, DC 0.100, pre-loading 0.081.

### Runtime (per operating point, one thread)

| network | AC N-1 (pandapower, sequential) | AC OPF dispatch (incl. failed attempts) | features | gboost scoring | logreg scoring |
| --- | --- | --- | --- | --- | --- |
| case30 | 0.49 s | 0.85 s | 0.36 ms | 0.32 ms | 8 µs |
| case57 | 1.01 s | 0.62 s | 0.55 ms | 0.58 ms | 10 µs |
| case118 | 2.42 s | 0.53 s | 1.1 ms | 1.4 ms | 23 µs |
| case300 | 7.72 s | 3.76 s | 6.2 ms | 3.3 ms | 57 µs |

Screening (features + model) is about three orders of magnitude cheaper than the full AC N-1
loop. Both need the solved base AC state; one-time PTDF/LODF/topology preprocessing and model
fitting are excluded. The DC baselines' scoring time is negligible (< 0.1 µs).

## Conclusion

On **unseen operating points of networks seen in training**, ML trained on simulator labels
clearly beats transparent screening: gradient boosting reaches PR-AUC 0.973 vs 0.765 for
DC-LODF, mostly because it also predicts post-contingency voltage violations that a DC
estimate cannot represent, and it is well calibrated there. That advantage **does not carry
over reliably to an unseen network**: on held-out case300, gradient boosting is no better than
DC-LODF and worse than the pre-contingency loading heuristic; logistic regression gives small
but significant PR-AUC gains (+0.02 to +0.10 over DC across held-out networks), while
calibration and decision thresholds learnt elsewhere fail, so the fixed physical "> 100 %" DC
rule is often the better yes/no screen. For thermal-only screening, DC-LODF is already a
strong, high-precision baseline. These conclusions hold for this simulator, these four test
systems and this operating-point generator only.

## Limitations

* Labels are simulator outputs (pandapower AC power flow), not historical outages; no
  dynamics, protection, remedial action schemes, corrective re-dispatch or tap/shunt
  switching after the outage.
* Generator Q limits are relaxed in the dispatch and not enforced in any power flow; every
  accepted operating point uses some generator beyond its PGLib Q capability, which makes
  voltages more supported than reality (voltage labels are probably *under*-counted). ANGMIN /
  ANGMAX are ignored.
* pandapower's PIPS OPF failed on 45 % (case30), 27 % (case57) and 53 % (case300) of requested
  operating points, preferentially at high load; failures are not monotone in the margins
  (numerical, not proven infeasibility). The accepted sets are therefore biased towards lighter
  load, and two thirds of case300 points use the fall-back without voltage margin. This was not
  tuned further.
* The dispatch margins ($\alpha \sim U(0.8, 1.0)$, 0.01 pu) are a modelling assumption; label
  prevalence (15–76 %) depends strongly on them and on each network.
* Small held-out samples: 7 case300 and 8 case30 test operating points in the pooled split;
  21 case300 points in the network split. Bootstrap CIs resample operating points only (not
  networks), so the LONO results are four single-network case studies, not an estimate of
  generalisation to "networks in general".
* `dc_attributable_score` equals `dc_score` on N-0 secure bases (base DC loading never exceeds
  100 %), so it is a redundant duplicate feature in this dataset.
* Runtime is single-threaded Python on one workstation; the AC N-1 loop is not an optimised
  production contingency analysis.

## Reproduce

```bash
cd packages/stormml
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1
uv run python -m stormml generate --network case30  --n-train 40 --n-test 20
uv run python -m stormml generate --network case57  --n-train 40 --n-test 20
uv run python -m stormml generate --network case118 --n-train 40 --n-test 20
uv run python -m stormml generate --network case300 --n-train 30 --n-test 15
uv run python -m stormml assemble
uv run python -m stormml evaluate --n-boot 1000 --boot-seed 20261114
uv run pytest -q
```

Artifacts: `data/artifacts/stormml/{dataset.npz, ml-screening-dataset.json,
ml-screening-results.json, index.json}`.
