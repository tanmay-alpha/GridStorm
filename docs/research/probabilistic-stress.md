# Probabilistic stress studies (StormRisk Monte Carlo EENS)

`packages/stormrisk` turns one deterministic StormSpec scenario into a **probability-weighted
scenario set** by Monte Carlo sampling of component outages (and optionally demand), solves every
distinct sampled state with the real GridStorm PyPSA adapter (`gridstorm_pypsa.run_scenario`,
DC linear optimal power flow, HiGHS), and reports Expected Energy Not Served (EENS) with its
sampling uncertainty.

> **Naming rule.** "EENS" labels only the probability-weighted estimate over the sampled scenario
> set (`payload.estimates`, `metric: "EENS"`, `probability_model.provenance: "modeled"`). The
> unserved energy of a single deterministic run (each entry of `payload.states`, or any ordinary
> GridStorm scenario result) is `unserved_energy_mwh` and is never called EENS.

> **Not a reliability assessment.** The outage probabilities are *modelled assumptions* taken
> from generic test-system data (IEEE RTS-96) and scaled for a storm-stress case; the networks are
> research/example datasets. Numbers below describe the model, not any real power system.

## Method

1. **Inputs.** A base `stormspec/1.0` scenario (network, horizon, load shedding at VOLL) and a
   `stormrisk-sampling/1.0` spec (`packages/stormrisk/src/stormrisk/spec.py`): outage classes
   (component type `line | transformer | link | generator`, optional carrier / id filter,
   unavailability $q$, provenance, source citation), an optional demand-multiplier distribution
   (discrete, or truncated normal quantised to a resolution), $N$ and a seed.
2. **Population.** Each class is mapped onto the network's assets (canonical-grid ids; ids are
   unique per component type, so assets are keyed by `(component, id)`). An asset may match at
   most one class; assets already out in the base scenario are excluded and reported.
3. **Sampling.** `numpy.random.Generator(PCG64(seed))`; outage uniforms are drawn row by row in
   fixed chunks, then demand draws. Asset $k$ is out for the whole horizon iff $u_{ik} < q_k$.
   Identical states (same outage set + demand multiplier) are collapsed by hash and weighted by
   their frequency $c_s$ ($\sum_s c_s = N$), so each distinct state is solved once.
4. **Scenario mapping.** Each state becomes a concrete StormSpec scenario: whole-horizon
   `line_outage` (with `component: line|transformer`), `link_outage`, `generator_outage` events
   and a `demand_multiplier` event, validated with `stormspec.validate` before solving.
5. **Solving and classification.** Every state is classified explicitly: `feasible` (finite,
   non-negative unserved energy), `infeasible`, `error` (engine exception or malformed result) or
   `invalid` (validation/adapter rejection, or more than `max_outages_per_sample` events). Counts
   per class are reported in `sample_accounting`; nothing is dropped silently.

## Estimators

With distinct states $s$, counts $c_s$, $p_s = c_s/N$, unserved energy $E_s$ [MWh]:

$$\widehat{\mathrm{EENS}} = \sum_s p_s\,E_s \qquad(\texttt{stormspec.eens}; \textstyle\sum_s p_s = 1 \text{ is enforced})$$

$$S^2 = \frac{1}{N-1}\sum_s c_s\,(E_s - \widehat{\mathrm{EENS}})^2,\qquad
\mathrm{SE} = \frac{S}{\sqrt N},\qquad
\mathrm{CI}_{95} = \widehat{\mathrm{EENS}} \pm z_{0.975}\,\mathrm{SE}\ (z_{0.975}=1.95996)$$

$$\mathrm{CV} = \mathrm{SE}/\widehat{\mathrm{EENS}},\qquad
\widehat{\mathrm{LOLP}} = \sum_s p_s\,\mathbf 1[E_s > \tau],\qquad
\mathrm{SE}(\widehat{\mathrm{LOLP}}) = \sqrt{\widehat{\mathrm{LOLP}}(1-\widehat{\mathrm{LOLP}})/N}$$

* $\tau$ = `shed_tolerance_mwh` (studies below: $10^{-3}$ MWh). The lower CI bound is clipped at 0.
* Also reported: mean unserved energy given shedding, 95th percentile and maximum of $E$.
* **Convergence trace**: running mean and CI half-width after $k$ samples in draw order
  (geometrically spaced $k$).
* **Importance ranking** (descriptive only): for each component, samples in which it is out, how
  many of those shed load, conditional mean unserved energy when out / in service, and its share
  of total sampled unserved energy. Several components can be out together, so shares can sum to
  more than 1; this is co-occurrence, not causal attribution.
* If any sample is not `feasible`, estimates are conditional on feasible samples
  (`basis: feasible_samples_only`) and `eens_lower_bound_all_samples_mwh` counts the others as 0.
* A warning is emitted when fewer than 10 samples shed load (CLT interval unreliable).

## Assumptions

* Outage probabilities are **modelled**, not observed (each class carries its citation):
  * Generators: forced outage rates from IEEE RTS-96 Table 6 (Grigg et al., "The IEEE Reliability
    Test System-1996", *IEEE Trans. Power Syst.* 14(3):1010–1020, 1999): 0.02–0.12 by unit type
    (coal/steam 350 MW 0.08, nuclear 400 MW 0.12, oil/steam 197 MW 0.05, oil CT 0.10).
  * Lines: RTS-96 Table 12 normal-weather permanent outage rates 0.24–0.54 /yr with 10–16 h
    duration give $q=\lambda r/8760\approx 3\cdot10^{-4}$–$10^{-3}$. Storm stress is represented
    by scaling to $q=0.01$–$0.05$, within the one-to-two-orders-of-magnitude adverse-weather
    envelope of the two-state weather model (Billinton & Allan, *Reliability Evaluation of Power
    Systems*, 2nd ed., 1996). These are illustrative stress values.
  * Transformers: RTS-96 0.02 /yr × 768 h → $q\approx0.002$ (not storm-scaled).
* Components fail **independently** of each other and of demand (no common-mode or spatially
  correlated storm damage).
* Outages last the **whole horizon** (the PyPSA adapter supports whole-horizon topology changes
  only); no repair or restoration.
* Each state is a **DC linear OPF** (PyPSA, HiGHS, threads = 1, capacities fixed at `p_nom`/`s_nom`)
  with load shedding at VOLL = 10 000 EUR/MWh: no AC feasibility, voltage, stability or
  protection behaviour.
* Crude Monte Carlo: the CI covers sampling error only, not parameter or model uncertainty.
