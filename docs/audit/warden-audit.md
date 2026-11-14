# Warden audit (Energy Hack Munich 2026 submission)

Audit of <https://github.com/eklavyagoyal/energy-hackathon-2026-submission> ("Warden — a grid
operations agent that never gets the physics wrong") as input to the GridStorm Crisis Response
Advisor (`workers/advisor`, method in [`docs/research/crisis-advisor.md`](../research/crisis-advisor.md)).

| Item | Value |
|---|---|
| Clone | `D:/New folder (4)/upstream/warden` (read-only) |
| Pinned commit | `1e9ee209e9e00734343f9891e2033f43ce9d1f73` (2026-06-14T17:21:09+02:00) |
| License | MIT, "Copyright (c) 2026 Eklavya Goyal" (`LICENSE`, verified) — permissive |
| Size | 95 tracked files; ~6.4 k lines of Python (`src/` + `tests/`), plus a 2.1 k-line HTML console |
| Stack | Python 3.11, pandapower **3.4.0** (pinned in `requirements.lock.txt`), FastAPI, optional `anthropic` SDK |
| Audit environment | `uv venv --python 3.11` at `upstream/.venvs/warden`, `pip install -r requirements.lock.txt`; Windows 10, host shared with ~20 other jobs |

**Code reuse decision.** The license permits reuse, but **no Warden code was copied** into GridStorm.
The advisor is a re-implementation from concepts (cited below) because Warden's engine is coupled to
pandapower built-in `case118` with synthetic ratings, uses whole-system OPF instead of targeted
actions, and keys everything on pandapower table indices rather than GridStorm asset ids.

## 1. What Warden does (read from source)

| Area | File(s) | Finding |
|---|---|---|
| Network | `src/grid/loader.py`, `src/engine/network.py` | `pandapower.networks.case118()`; pandapower ships 9900 MVA placeholder ratings, so `apply_proportional_line_ratings` **assigns synthetic line ratings** = base-case current / 0.30 (rating target 30 % base loading), floored at the 25th percentile ("Motter-Lai 2002 style", decision D59). Transformer ratings are left at the placeholders (13 trafos effectively unconstrained — stated in the code). `lift_voltage_profile` moves generator voltage setpoints into 1.01–1.04 p.u. |
| Scenarios | `src/engine/scenarios.py` | `calm`; `demo_congestion` = loads within 2 hops of bus 115 scaled ×4; `demo_overload` = the same plus a system-wide ×1.22 load multiplier. Both were "discovered at build time" for case118. Time series (`src/timeseries/`) apply a 24-h multiplier profile + event list per step. |
| Power flow / violations | `src/engine/network.py::base_case_summary`, `constants.py` | `pp.runpp` with **pandapower defaults** (generator Q limits not enforced). Violation = `loading_percent` > 100 % (current-based) or |V| outside a uniform 0.95–1.05 p.u. band. |
| Contingencies | `src/engine/scan.py`, `cascade.py`, `severity.py` | N-1 set = every in-service line + trafo + every `ext_grid` (173 + 13 + 1 = 187 on case118). Each contingency runs an **iterative cascade**: trip every element above 120 % (`TRIP_THRESHOLD`), re-solve, de-energise islands, up to 20 iterations; a solve failure counts as divergence and all remaining load is counted as shed. A composite severity score (CSS, capped at 2000 for blackout) ranks contingencies. |
| Candidate actions | `src/engine/remediation.py` | Two levers only. (a) **Redispatch** = one pandapower AC-OPF (`runopp`) on a copy with *every* line limited to 85 % (`SECURITY_MARGIN_PCT`) and bus limits 0.955–1.045 p.u.; the action is the full set of changed gen P and V setpoints. `propose_remediation` repeats with the margin tightened by 5 % up to 3 times. (b) **Curtailment** = loads at the endpoints of overloaded lines plus one-hop neighbours, a single shed fraction bisected (12 steps, ≤ 90 %) until the base case is secure; **only `p_mw` is scaled** (reactive demand unchanged). No switching actions, no candidate ranking by sensitivities, no combinations. |
| Verify-before-commit | `remediation.py::verify_action` | Apply the action to a deep copy, re-run `runpp` and the cascade for the **top-3 offending contingencies** (`_VERIFY_TOP_OFFENDING = 3` in `src/agent/tools.py`). `verified = base case SECURE and no screened contingency score got worse`. Contingencies outside the top 3 are not re-checked, so "holds N-1" means "the three worst screened contingencies did not get worse". |
| Objective / cost | `remediation.py::_redispatch_cost`, `VOLL_EUR_PER_MWH = 5000` | Redispatch cost = marginal-cost-weighted MW moved (from pandapower `poly_cost`); curtailment cost = 5000 EUR/MWh × MW. Redispatch is always tried first; curtailment is the fallback. |
| Baselines | `remediation.py::greedy_policy`, `src/api/routes/compare.py` | (1) Greedy strawman: repeatedly trip the most overloaded line. (2) AC-OPF with the 85 % margin, scored by the same verifier. (3) The agent = the same OPF + verification + narration. |
| LLM | `src/agent/` | Optional Anthropic narration / tool loop; without `ANTHROPIC_API_KEY` a deterministic template narrator runs and the verification path is identical. Every number in the narration is copied from solver JSON. |
| Outputs | `fixtures/*.json`, FastAPI routes | Frozen 24-step trace, topology layout, battery-siting fixtures (`make freeze-*`). |
| Tests | `tests/` (25 files, 130 tests) | Engine invariants (slack guard, islanding, cascade iteration, determinism), remediation (no commit without verification, shed ≤ total load), API shape, timeseries budget, dataset portability. |

## 2. Test run (time-boxed to 45 min)

Command (from the clone, no API key, single-threaded BLAS):

```bash
ANTHROPIC_API_KEY= OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMBA_NUM_THREADS=1 \
  ../.venvs/warden/Scripts/python.exe -m pytest tests -q -p no:cacheprovider -rfEs --durations=20
```

Result (log `upstream/.venvs/warden-pytest.log`): **129 passed, 1 failed in 502.4 s**.
The failure is a wall-clock budget, not a physics assertion:

```
FAILED tests/timeseries/test_simulator.py::test_runs_under_30s
AssertionError: 24-step simulation took 77.1s, over the 30s budget
```

Slowest items: the 24-step case118 simulation fixture (77.1 s), `test_compare_three_policies`
(76.4 s), `test_agent_plan_demo_overload_verifies` (38.1 s). The host was shared with ~20 other
agents, so the timing failure does not show that the claimed ~18 s is wrong on an idle machine — only
that it was not reproduced here. (A previous attempt in this audit was killed when the agent was
parked; the numbers above are from the complete re-run.)

## 3. Claims: reproduced vs not reproduced

| Claim | Evidence from this audit | Status |
|---|---|---|
| Deterministic plan verifies before commit without an API key | `test_agent_plan_demo_overload_verifies`, `test_verify_action_structure_and_no_commit`, and agent shape/decision tests passed in the complete suite above | Reproduced as test assertions; not an independent proof of every proposed action |
| Iterative cascade, slack guard, no fabricated shedding | Integrity/remediation tests passed, including `test_cascade_is_iterative` and `test_load_shed_avoided_never_exceeds_total_load` | Reproduced within upstream test coverage |
| 24-step simulation and three-policy comparison execute | Timeseries simulation and comparison assertions passed | Reproduced functionality; relative cost/severity claims not independently benchmarked |
| Full suite passes within performance budget | 129 passed, one wall-clock assertion failed (77.1 s versus 30 s) | Not reproduced on this shared Windows host |
| Approximately 18 s for the 24-step demonstration | Observed 77.1 s for the suite's stress fixture; machines/workloads differ | Not reproduced; not a cross-machine disproof |
| “1,794 MW across 50 generators” in the README demonstration | Source and fixture inspection only; the separately drafted reproduction script was not executed to completion | Unverified numerical demonstration claim |
| Resulting state “holds N-1” | Source verifies only the three worst screened contingencies; the rest are not rechecked after action | Not established as exhaustive N-1 security |
| Competition winner / prize | No independent public results evidence collected | Unverified |

No Anthropic calls or paid services were used. The test result is upstream self-test evidence,
not independent validation of its competition claims. The optional demonstration reproduction
script outside this repository is not relied on as evidence.

## 4. Assessment and what GridStorm takes from it

Strengths worth keeping (concepts, re-implemented):

- **Verify before commit on a deep copy**: no action is reported as accepted unless an AC power
  flow of the modified copy says so; the live/input network is never mutated.
- **Honest rejection**: infeasible cases are reported as such instead of a best-effort action.
- **Minimal curtailment by bisection** on an AC check, with VOLL making shedding the expensive lever.
- **Slack-loss and islanding guards** before solving (unsupplied buses via `pandapower.topology`).

Limitations that the GridStorm advisor addresses differently:

| Warden | GridStorm advisor |
|---|---|
| Synthetic line ratings on pandapower `case118` (30 % base-loading target); trafos unrated | PGLib-OPF cases with their published `rateA` (MVA) for every branch, loading = max(|S_from|, |S_to|)/rateA |
| Uniform 0.95–1.05 p.u. band | Per-bus VMIN/VMAX from the case file |
| `runpp` defaults (Q limits not enforced) | Newton-Raphson with `enforce_q_lims=True`, tolerance 1e-8 MVA |
| One whole-system OPF action (dozens of generators move; e.g. "1,794 MW across 50 generators") | Targeted, operator-sized candidates: PTDF-ranked generator pairs, DC-relief-ranked load shedding, LODF-screened non-islanding switching, pairwise combinations; each sized by AC bisection |
| Load curtailment scales P only | P and Q scaled together (constant power factor) |
| "Secure" = base secure + top-3 offending contingencies not worse | "Accepted" = original violations cleared + no new violation + no extra islanded load; explicit statement that N-1 is checked only for the top candidates (full single-branch AC N-1, reported) |
| Ranking: redispatch first, curtailment fallback | Every accepted candidate ranked by an explicit objective (gencost + VOLL·shed + switching penalty), then by margin |

Unverified (not reproduced and not relied upon): the competition result ("Winner, E.ON track,
EUR 1,000") — no public results page was checked from this environment; it has no bearing on the
technical audit.
