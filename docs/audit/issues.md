# GridStorm verification issue log

Maintained by the independent verifier (Agent F). Every entry has reproducible evidence.
Severity: **S1** blocks a claim/demo or is a security hole · **S2** wrong/misleading output or
contract deviation · **S3** quality/robustness · **S4** nit.
Status: OPEN · FIXED (verified by re-running the repro) · WONTFIX (owner rationale recorded) ·
OBSOLETE.

Paths are relative to the repository root; commands are run from the repository root in bash.
Verifier probe scripts live outside the repository in `D:/New folder (4)/_verifier_tmp/` (referred
to as `$VT`); their full source is reproduced in the details where they are short.

| ID | Sev | Component | Summary | Status |
|---|---|---|---|---|
| VER-001 | S1 | packages/stormrisk | Sampled transformer outages emitted as line outages; base outages excluded same-id assets of every component type | FIXED |
| VER-002 | S1 | workers/pypsa | Curtailment metrics count unused capacity of dispatchable (gas) generators whenever a generator event is applied | OPEN |
| VER-003 | S2 | packages/stormspec | No preset scenarios in `packages/stormspec/presets/`; own test `test_presets_parse_and_are_unique` fails | OPEN |
| VER-004 | S2 | workers/pypsa | No test suite (`workers/pypsa/tests/` empty) although TODO P2-02 acceptance requires outage/demand/storage tests | OPEN |
| VER-005 | S3 | workers/advisor | DC sensitivity failure silently yields zero candidates (no warning in the payload) | OPEN |
| VER-006 | S4 | workers/pypsa | `generation_cost_eur` also contains link/storage marginal costs; `solver.objective_eur` omits `objective_constant` while `total_system_cost_eur` includes it | OPEN |

## Details

### VER-001 — stormrisk: component lost for colliding ids (S1, FIXED)

Contract §3: asset ids are unique only per component type; `line_outage.component` selects
`line | transformer`. `stormrisk.sampling.state_scenario` emitted every `line_outage` without
`component` (→ default `line`), and `_base_outaged_assets` keyed outages by `asset_id` only.

Repro (`$VT/sr_probe.py`: toy network with line `5`, transformer `5`, generator `5`; base scenario
outages transformer `5`; sampling classes for lines, generators, and transformers):

```bash
cd packages/stormrisk && uv run python "D:/New folder (4)/_verifier_tmp/sr_probe.py"
```

Before the fix: `population: []`, `excluded_base_outaged=('5',)` (line 5 and generator 5 wrongly
dropped) and `transformer sample -> [{'type': 'line_outage', 'asset_id': '5', 'component': 'line'}]`
(a transformer outage silently applied to the line with the same id).

Fix (StormRisk owner): `PopulationAsset.event()` emits `component`; base outages keyed by
`(component, asset_id)`; regression test `tests/test_study.py::test_ids_colliding_across_components`.
Re-verified: probe now prints `population: [('generator', '5'), ('line', '5')]`,
`excluded_base_outaged=()`, and `component: 'transformer'`; `uv run pytest -q` → `28 passed`.

### VER-002 — pypsa: curtailment includes dispatchable generators (S1, OPEN)

`gridstorm_pypsa.runner.variable_generators(n)` returns the columns of `n.generators_t.p_max_pu`.
`_apply_events` replaces that frame with the dense frame of **all** generators whenever a
`generator_outage`, `renewable_availability_multiplier`, or `curtailment: false` is applied, so after
the solve every gas unit is "variable" and `curtailment_mwh`, `curtailment_by_carrier_mwh`, and
`series.curtailment_mw` count unused gas capacity.

Repro (`$VT/pypsa/stress.json`: ac-dc-meshed, demand ×1.6, wind ×0.3 on [2,8), line `0` out,
`Manchester Gas` out on [3,7), load shedding on):

```bash
cd workers/pypsa && uv run python -m gridstorm_pypsa run \
  --scenario "D:/New folder (4)/_verifier_tmp/pypsa/stress.json" \
  --network-dir ../../data/networks/ac-dc-meshed --out /tmp/stress.result.json
jq -c '.series.curtailment_mw, [.assets.generators[] | select(.carrier=="wind") | .available_mw]' /tmp/stress.result.json
```

Observed: `curtailment_mw` = `[145166, 143800, 147320, 94844, …]` MW. The wind farms only have ~6–97 MW
each available per snapshot. 145 166 = 150 000 MW gas `p_nom` (50 000 + 20 000 + 80 000) − 4 835 MW gas
dispatch at t=0. `curtailment_mwh` = 1 251 614 MWh, which is 24× the 52 076 MWh total load. The same
network with no events (`$VT/pypsa/base.json`) reports curtailment 0.

Suggested fix: determine the variable-generator set once from the unmodified network, or from canonical
`is_variable`, before `_apply_events`. Carry it in `_Applied` and use it in `_generation_metrics`. Add a
regression test that applies a generator outage and asserts curtailment ≤ Σ available wind/solar −
dispatched wind/solar.

Everything else checked on the same result passes:
* An independent plain-PyPSA re-solve (`$VT/pypsa/indep.py`, no GridStorm code) gives objective
  28 477 328.814 EUR. The runner gives 28 477 328.8135 EUR.
* Unserved energy is 2 826.8713 MWh in both, and the shed series is identical.
* Σ shed·Δt = metric; Σ bus shed = metric; generation ≤ available (max excess 0).
* The outaged generator has p = 0 inside its window; `balance_residual_max_mw` = 0.
* `max_line_loading_pct` matches recomputation from asset rows.
* Partial-window line outage (`$VT/pypsa/partial.json`) is rejected with `unsupported_operation`.

### VER-003 — stormspec: presets missing (S2, OPEN)

```bash
cd packages/stormspec && uv run pytest -q
```
→ `FAILED tests/test_stormspec.py::test_presets_parse_and_are_unique - assert 0 >= 4` (29 passed,
1 failed). `packages/stormspec/presets/` is empty; contract §3 and TODO P2-03 require ≥ 4 presets that
reference real asset ids. This blocks the API preset/job integration tests (`acdc_preset` fixture).

### VER-004 — pypsa worker without tests (S2, OPEN)

`ls workers/pypsa/tests` → empty. Nothing guards the claims in TODO P2-02 (balance residual,
outage/demand/storage). VER-002 would have been caught by a single generator-outage test.

### VER-005 — advisor: silent empty candidate set (S3, OPEN)

`workers/advisor/src/gridstorm_advisor/sensitivity.py::compute` returns `None` on any `pp.rundcpp`
exception (`except Exception: return None`). `advisor.py` (around line 379) then skips all candidate
generation (`if sens is not None:`), adds no warning, and the payload reads as if no remedial action
existed. Check: `grep -n "sens is None\|warnings" workers/advisor/src/gridstorm_advisor/advisor.py` →
no handling. Suggested fix: record a warning/status such as `dc_sensitivity_failed` with the
exception type in the payload, and add a test.

### VER-006 — pypsa: cost labels (S4, OPEN)

`runner.py` `_postprocess`: `generation_cost_eur = objective - shed_cost`, which also includes
link/storage marginal costs. `solver.objective_eur = n.objective`, while `total_system_cost_eur =
n.objective + n.objective_constant`. On ac-dc-meshed both are equal (the constant is 0 after fixing
capacities), but the definitions differ. Suggested fix: rename or document the field as "operating cost
excluding load shedding" and use one objective definition.
