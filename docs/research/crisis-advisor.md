# Deterministic Crisis Response Advisor

Implementation: `workers/advisor` (`gridstorm_advisor`), isolated Python 3.11 / pandapower 3.5.x environment. No LLM, paid API, or operational control connection. Warden informed the verify-before-commit design; [the audit](../audit/warden-audit.md) records its MIT license, pinned revision, reproduced tests and unverified claims. No upstream code was copied.

## Inputs and reproducibility

Native crisis JSON accepts `id`, `line_outages` (branch ids, including transformers), `generator_outages`, `demand_multiplier`, and optional `demand_buses`. StormSpec input supports these events only, rejects time windows and unsupported events, and validates `line_outage.component` (`line` by default, or `transformer`). Active and reactive demand scale together. If the slack generator fails, the surviving generator with the largest Pmax becomes the reference; the artifact records this decision.

PGLib inputs come from `data/networks/<network_id>/source/*.m`, preserving `bus-<BUS_I>`, `branch-<one-based row>`, `gen-<one-based row>` and `load-<BUS_I>` ids. Built-in pandapower cases are also supported with explicitly different table-index ids. The preset runs use both `pglib-case14-ieee` and `pglib-case118-ieee`. PGLib's stored Pg values are not assumed feasible: each preset first obtains an intact-network AC-OPF operating point, with current limits conservatively tightened using VMAX to respect published MVA ratings. This dispatch and its objective are recorded, not passed off as observations.

From `workers/advisor`:

```bash
uv sync
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 \
  uv run python scripts/build_artifacts.py
uv run gridstorm-advisor advise --help
```

The single-case CLI accepts `--network-id`, `--operating-point case|opf`, `--crisis` (a native crisis or StormSpec JSON file), and `--out`. The committed batch inputs are `presets/crises.json`. The build script writes five contract §5 `kind: advisor` envelopes and `data/artifacts/advisor/index.json`; envelopes record the actual command, input hashes, platform, solver version, creation time and canonical payload hash. Wall time and envelope metadata are not deterministic; the advisor payload is deterministic for fixed inputs/environment.

## Method and objective

1. Deep-copy the network, apply the crisis, solve Newton–Raphson AC PF (DC initialization, one flat-start retry, tolerance 1e-8 MVA, generator Q limits enforced).
2. Identify overloads using max apparent power at either branch terminal / published rateA; respect each bus's VMIN/VMAX. Also report non-convergence, unsupplied load and slack Pmin/Pmax violations. Numerical tolerances are 0.01 percentage points thermal, 1e-4 p.u. voltage, 0.001 MW slack power.
3. Shortlist generator pairs by DC PTDF relief, respecting Pmin/Pmax headroom; shortlist effective load buses by flow relief and proximity to low voltages. Rank line-opening candidates using LODF, excluding openings that island load or generation. Combine up to two actions from a bounded pool (three per action type). Defaults cap standalone redispatch at six, switching at five, and shedding at up to nine.
4. For scalable candidates bisect a common scale for 14 iterations, rounding amounts upward to 0.01 MW. Originally overloaded branches target 99.5% to leave a numerical margin. Every probe and final candidate uses a deep copy and full AC PF. Bisection assumes a monotone response; it is not a global minimum-shedding optimization.
5. Accept only convergence, clearance of every original violation, no new violation and no additional islanded load. Rejections retain structured cleared/remaining/new violations, metrics, actions and explanation. Failed sensitivity calculation explicitly reports unavailable candidate generation; an empty shortlist never proves infeasibility.
6. Sort accepted candidates by total objective, then lower maximum branch loading, then stable candidate id. Perform full single-branch AC N-1 screening of the top three accepted candidates (or fewer), plus the intact pre-crisis state. Generator N-1 is not included.

For a modeled one-hour duration:

`objective_eur = MATPOWER_gencost(post-action dispatch including slack) + 10000 * shed_mw + 1000 * number_of_switches`.

The total generation cost, its change relative to the crisis, VOLL penalty and switching penalty are separate fields. MATPOWER's numeric cost coefficients are interpreted under an explicit EUR convention; these are not observed European market prices. VOLL and switching penalties are modeling choices. The objective ranks the generated candidates, not all feasible interventions.

## Measured results

These are actual solver outputs in `data/artifacts/advisor/`, not synthesized examples. All do-nothing baselines are rejected. A dash means no accepted shortlisted candidate, not a proof of physical infeasibility. Costs include total generation cost for the assumed hour.

| Network / outage | Crisis max loading (%) | Crisis min V (p.u.) | Evaluated / accepted | Top action | After max loading (%) | Shed (MW) | Objective (EUR) |
|---|---:|---:|---:|---|---:|---:|---:|
| case118 / branch-164 | 134.068 | 0.93999 | 48 / 12 | gen-45 → gen-46: 56.53 MW | 99.496 | 0 | 98,371.60 |
| case118 / branch-38 | 181.820 | 0.94039 | 48 / 0 | — | — | — | — |
| case118 / gen-21 | 140.407 | 0.93965 | 48 / 6 | gen-30 → gen-29: 307.74 MW | 100.000 | 0 | 101,729.62 |
| case14 / gen-1 | 55.480 | 0.94185 | 3 / 0 | — | — | — | — |
| case14 / branch-3 | 82.849 | 0.84883 | 2 / 1 | shed at loads 3, 4, 9 | 65.017 | 45.57 | 457,537.72 |

The case14 voltage fix sheds 25.03 MW at load-3, 12.70 MW at load-4 and 7.84 MW at load-9. Its minimum voltage is 0.93990 p.u., accepted within the documented 1e-4 tolerance of 0.94; it is not a large voltage margin.

### Baseline comparison

The proportional-shedding baseline scales every supplied load by the same fraction, AC-bisects clearance of the original violations (cap 99%), and then applies the same final rejection checks. New violations can invalidate its apparent original-violation fix: reducing load without rescheduling fixed generation can cause reverse flows, overvoltage or slack-limit violations. Rejected baseline costs are diagnostic, not feasible alternatives.

| Network / outage | Proportional status | Proportional shed (MW) | Proportional objective (EUR) | Advisor status |
|---|---|---:|---:|---|
| case118 / branch-164 | rejected | 901.17 | 9,085,585.64 | accepted, no shed |
| case118 / branch-38 | rejected | 4,199.58 | 42,000,986.55 | no accepted candidate |
| case118 / gen-21 | rejected | 4,199.58 | 42,001,194.50 | accepted, no shed |
| case14 / gen-1 | accepted | 200.62 | 2,007,572.50 | no accepted candidate |
| case14 / branch-3 | accepted | 63.08 | 632,485.04 | accepted, 45.57 MW shed |

The targeted case14 voltage fix sheds 17.51 MW less than the proportional baseline. The generator-loss case exposes a genuine shortlist limitation: the feasible broad proportional action is reported as a baseline, not silently promoted into the targeted advisor ranking. “No accepted candidate” is therefore deliberately weaker than “no solution exists”.

## Security scope and limitations

Accepted means **clears all thermal/voltage/slack/islanded-load violations in the post-contingency AC steady state within the stated tolerances**. It does not imply N-1 security. The additional single-branch screens find violations, islands and/or non-convergence for the recommended states; inspect each artifact's `n_minus_1` records. No recommendation here is certified N-1 secure. No dynamics, transient/frequency stability, protection coordination, ramp rates, time coupling or restoration sequence is checked.

DC sensitivities are heuristics for candidate selection, not acceptance. Candidate limits, pairwise combinations, fixed generator voltage setpoints and single-slack loss balancing can miss feasible cheaper fixes. Active-power cost and deterministic one-hour unserved energy are not probability-weighted EENS. Unlimited/missing rateA is not invented as a constraint. Built-in pandapower cases can contain placeholder ratings and should not be confused with the published PGLib ratings.

## Tests and verification

`workers/advisor/tests/test_advisor.py` uses a constructed three-bus mesh with a known redispatch fix, independently resolves accepted/rejected actions with plain pandapower, tests rejection of new violations, insufficient relief, non-islanding switching, baseline/security statements, deterministic payloads, finite JSON, unsupported events, component typing, sensitivity-unavailable reporting and explicit islanded-load detection.

Run `uv run pytest -q` in the advisor directory for integration verification. Artifact generation itself ran full AC candidate evaluations and branch-contingency screens; this is separate from the test suite. The completed upstream Warden suite result is documented in the audit (129 passed, one timing failure), not represented as an advisor test result.
