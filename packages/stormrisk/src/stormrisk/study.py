"""Run a Monte Carlo stress study: sample states -> StormSpec scenarios -> engine -> estimators.

The engine is any callable ``engine(scenario: stormspec.Scenario) -> dict`` returning a
gridstorm-result/1.0 document. Studies use :class:`stormrisk.engines.PypsaEngine` (the real
GridStorm PyPSA adapter); unit tests inject mock callables. With ``workers > 1`` the engine must
be picklable (module-level function or class instance) because solves run in worker processes.
"""

from __future__ import annotations

import math
import sys
import time
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from stormspec import Scenario, scenario_hash, validate

from .estimators import convergence_trace, importance_ranking, mc_statistics
from .sampling import (
    Population,
    SampleSet,
    StudyInputError,
    draw_samples,
    resolve_population,
    state_scenario,
)
from .spec import SamplingSpec

STUDY_SCHEMA_VERSION = "stormrisk-study/1.0"
NEGATIVE_TOL_MWH = 1e-6
MIN_SHED_SAMPLES_FOR_CLT = 10

Engine = Callable[[Scenario], dict]


class EngineRejected(Exception):
    """Raised by an engine binding when it refuses a scenario (classified ``invalid``)."""


STUDY_ASSUMPTIONS = [
    "Component unavailabilities are MODELLED inputs (see sampling_spec.outage_classes[].source); "
    "they are not observed failure statistics of the studied network.",
    "Components fail independently of each other and of demand (no common-mode or "
    "weather-correlated failures unless encoded in the class probabilities).",
    "Every sampled outage lasts the whole study horizon (the PyPSA adapter supports topology "
    "changes for the whole horizon only); no repair or restoration within the horizon.",
    "Each sampled state is solved as a DC linearised optimal power flow (PyPSA LOPF, HiGHS) with "
    "load shedding at VOLL; no AC feasibility, voltage, stability or protection behaviour.",
    "Crude (unstratified) Monte Carlo; uncertainty is sampling error only (CLT normal "
    "approximation). Model/parameter uncertainty is not included in the confidence interval.",
]

STUDY_LIMITATIONS = [
    "Not a reliability assessment of any real power system: the probabilities are generic "
    "modelled values and the network models are research/example datasets.",
    "EENS here is the expected unserved energy over the study horizon conditional on the base "
    "scenario (e.g. its snapshots and demand), not an annual adequacy index.",
    "Importance ranking is descriptive co-occurrence, not causal attribution.",
]


def peak_rss_mb() -> float | None:
    """Peak resident set size of the current process in MiB (None if unavailable)."""
    try:
        import psutil

        info = psutil.Process().memory_info()
        peak = getattr(info, "peak_wset", None)  # Windows
        if peak is not None:
            return peak / 2**20
    except Exception:  # pragma: no cover - psutil missing
        pass
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return ru / 2**20 if sys.platform == "darwin" else ru / 1024
    except Exception:  # pragma: no cover
        return None


def classify_result(result: dict) -> dict[str, Any]:
    """Reduce a gridstorm-result to the fields a study needs; classify the outcome explicitly."""
    solver = result.get("solver") or {}
    metrics = result.get("metrics") or {}
    rec: dict[str, Any] = {
        "outcome": None,
        "unserved_energy_mwh": None,
        "peak_load_shed_mw": None,
        "termination_condition": solver.get("termination_condition"),
        "solver_status": solver.get("status"),
        "solver_wall_time_s": solver.get("wall_time_s"),
        "error": None,
    }
    outcome = result.get("outcome")
    if outcome == "feasible":
        e = metrics.get("unserved_energy_mwh")
        if not isinstance(e, int | float) or not math.isfinite(e):
            rec.update(outcome="error", error="feasible result without finite unserved_energy_mwh")
        elif e < -NEGATIVE_TOL_MWH:
            rec.update(outcome="error", error=f"negative unserved energy {e} MWh")
        else:
            rec.update(outcome="feasible", unserved_energy_mwh=max(0.0, float(e)),
                       peak_load_shed_mw=metrics.get("peak_load_shed_mw"))
    elif outcome == "infeasible":
        rec["outcome"] = "infeasible"
    else:
        warnings = result.get("warnings") or []
        rec.update(outcome="error",
                   error=f"engine outcome {outcome!r}; " + "; ".join(map(str, warnings))[:400])
    return rec


def solve_state(engine: Engine, scenario: Scenario) -> dict[str, Any]:
    """Run one state through the engine (in a worker process when parallel)."""
    t0 = time.perf_counter()
    meta: dict[str, Any] = {}
    try:
        result = engine(scenario)
    except Exception as exc:  # classified, never dropped
        outcome = "invalid" if isinstance(exc, EngineRejected) else "error"
        rec = _unsolved(outcome, f"{type(exc).__name__}: {exc}"[:500])
    else:
        rec = classify_result(result)
        meta = {"engine": result.get("engine"),
                "solver": {k: (result.get("solver") or {}).get(k) for k in ("name", "version")}}
    rec["wall_time_s"] = time.perf_counter() - t0
    rec["worker_peak_rss_mb"] = peak_rss_mb()
    rec["engine_meta"] = meta
    return rec


def prepare_study(
    base: Scenario, spec: SamplingSpec, network: dict[str, Any]
) -> tuple[Population, SampleSet]:
    """Check inputs, resolve the population and draw the (deterministic) sample set."""
    report = validate(base, network)
    if not report.valid:
        raise StudyInputError(
            "base scenario invalid: " + "; ".join(f"{i.code}: {i.message}" for i in report.errors)
        )
    if not base.mitigation.load_shedding.enabled:
        raise StudyInputError(
            "base scenario must enable load shedding: without it unserved energy is undefined "
            "(states would be infeasible instead)"
        )
    if spec.demand_multiplier is not None and any(
        ev.type == "demand_multiplier" for ev in base.events
    ):
        raise StudyInputError(
            "sampling a demand multiplier on top of a base scenario that already has "
            "demand_multiplier events is ambiguous; remove one of them"
        )
    population = resolve_population(base, spec, network)
    return population, draw_samples(population, spec)


def run_study(
    base: Scenario,
    spec: SamplingSpec,
    network: dict[str, Any],
    engine: Engine,
    *,
    workers: int = 1,
    progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Execute the study and return the ``stormrisk-study/1.0`` payload (unrounded)."""
    t_start = time.perf_counter()
    population, samples = prepare_study(base, spec, network)

    # Build and validate one concrete scenario per distinct state.
    records: list[dict[str, Any] | None] = [None] * len(samples.states)
    keys: list[str] = []
    scen_hashes: list[str | None] = []
    to_solve: list[tuple[int, Scenario]] = []
    for j, state in enumerate(samples.states):
        key = state.key(population)
        keys.append(key)
        n_out = len(state.outage_idx)
        if n_out > spec.max_outages_per_sample:
            records[j] = _unsolved("invalid", f"{n_out} outages > max_outages_per_sample")
            scen_hashes.append(None)
            continue
        try:
            scen = state_scenario(base, state, population, key)
        except Exception as exc:
            records[j] = _unsolved("invalid", f"scenario construction failed: {exc}"[:500])
            scen_hashes.append(None)
            continue
        rep = validate(scen, network)
        scen_hashes.append(scenario_hash(scen))
        if not rep.valid:
            records[j] = _unsolved(
                "invalid", "; ".join(f"{i.code}: {i.message}" for i in rep.errors)[:500]
            )
            continue
        to_solve.append((j, scen))

    total = len(to_solve)
    if workers > 1 and total > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(solve_state, engine, scen) for _, scen in to_solve]
            for done, ((j, _), fut) in enumerate(zip(to_solve, futures, strict=True), start=1):
                records[j] = fut.result()
                if progress:
                    progress(done, total)
    else:
        for done, (j, scen) in enumerate(to_solve, start=1):
            records[j] = solve_state(engine, scen)
            if progress:
                progress(done, total)

    payload = _assemble(base, spec, population, samples, keys, scen_hashes, records)
    worker_rss = [r["worker_peak_rss_mb"] for r in records
                  if r and r.get("worker_peak_rss_mb") is not None]
    payload["runtime"] = {
        "wall_time_s": time.perf_counter() - t_start,
        "solves": total,
        "workers": workers,
        "solve_wall_time_s_sum": sum(r["wall_time_s"] for r in records if r and "wall_time_s" in r),
        "peak_rss_mb_main_process": peak_rss_mb(),
        "peak_rss_mb_max_worker": max(worker_rss) if (workers > 1 and worker_rss) else None,
        "python": sys.version.split()[0],
        "platform": sys.platform,
    }
    return payload


def _unsolved(outcome: str, error: str) -> dict[str, Any]:
    return {"outcome": outcome, "unserved_energy_mwh": None, "peak_load_shed_mw": None,
            "termination_condition": None, "solver_status": None, "solver_wall_time_s": None,
            "error": error, "engine_meta": {}}


def _assemble(
    base: Scenario,
    spec: SamplingSpec,
    population: Population,
    samples: SampleSet,
    keys: list[str],
    scen_hashes: list[str | None],
    records: list[dict[str, Any] | None],
) -> dict[str, Any]:
    tol = spec.shed_tolerance_mwh
    n = samples.n_samples
    counts = samples.counts
    by_outcome = {"feasible": 0, "infeasible": 0, "error": 0, "invalid": 0}
    states_out = []
    for j, (state, rec) in enumerate(zip(samples.states, records, strict=True)):
        assert rec is not None
        by_outcome[rec["outcome"]] += counts[j]
        states_out.append({
            "state_hash": keys[j],
            "scenario_hash": scen_hashes[j],
            "outages": [[population.assets[i].component, population.assets[i].asset_id]
                        for i in state.outage_idx],
            "demand_multiplier": state.demand_multiplier,
            "count": counts[j],
            "outcome": rec["outcome"],
            "unserved_energy_mwh": rec["unserved_energy_mwh"],
            "peak_load_shed_mw": rec["peak_load_shed_mw"],
            "termination_condition": rec["termination_condition"],
            "wall_time_s": rec.get("wall_time_s"),
            "error": rec["error"],
        })

    feas = [j for j, r in enumerate(records) if r and r["outcome"] == "feasible"]
    n_feas = by_outcome["feasible"]
    warnings: list[str] = []
    if n_feas < n:
        warnings.append(
            f"{n - n_feas} of {n} samples have no unserved-energy value "
            f"(infeasible={by_outcome['infeasible']}, error={by_outcome['error']}, "
            f"invalid={by_outcome['invalid']}); estimates are conditional on feasible samples "
            "and eens_lower_bound_all_samples_mwh treats them as zero."
        )
    # "EENS" labels ONLY this probability-weighted Monte Carlo estimate; per-state values are
    # single deterministic runs and are reported as unserved_energy_mwh, never as EENS.
    estimates: dict[str, Any] = {
        "metric": "EENS",
        "estimator": "crude_monte_carlo_frequency_weighted",
        "probability_model": {
            "provenance": "modeled",
            "description": "independent whole-horizon component unavailabilities "
            "(sampling_spec.outage_classes) and optional demand-multiplier distribution",
        },
        "basis": "all_samples" if n_feas == n else "feasible_samples_only",
        "provenance": "modeled",
    }
    convergence: list[dict] = []
    importance: list[dict] = []
    if feas:
        ys = [records[j]["unserved_energy_mwh"] for j in feas]
        cs = [counts[j] for j in feas]
        estimates.update(mc_statistics(ys, cs, tol=tol))
        estimates["eens_lower_bound_all_samples_mwh"] = (
            sum(y * c for y, c in zip(ys, cs, strict=True)) / n
        )
        if estimates["n_loss_of_load_samples"] < MIN_SHED_SAMPLES_FOR_CLT:
            warnings.append(
                f"only {estimates['n_loss_of_load_samples']} loss-of-load samples: the CLT "
                "confidence interval is unreliable (rare-event regime); increase n_samples."
            )
        feas_set = set(feas)
        seq = [records[j]["unserved_energy_mwh"] for j in samples.sample_state_index
               if j in feas_set]
        convergence = convergence_trace(seq)
        outs = [[(population.assets[i].component, population.assets[i].asset_id)
                 for i in samples.states[j].outage_idx] for j in feas]
        importance = importance_ranking(outs, ys, cs, tol=tol)
    else:
        warnings.append("no feasible samples: no estimates can be computed")

    expected_out = sum(a.unavailability for a in population.assets)
    meta = next((r["engine_meta"] for r in records if r and r.get("engine_meta")), {})
    return {
        "schema_version": STUDY_SCHEMA_VERSION,
        "network_id": base.dataset.network_id,
        "base_scenario": {"scenario_hash": scenario_hash(base),
                          "spec": base.model_dump(mode="json")},
        "sampling_spec": spec.model_dump(mode="json"),
        "engine": meta,
        "population": {
            "n_assets_sampled": len(population.assets),
            "expected_outages_per_sample": expected_out,
            "classes": [
                {"name": c.name, "component": c.component, "unavailability": c.unavailability,
                 "provenance": c.provenance, "source": c.source,
                 "n_assets_matched": population.class_counts.get(c.name, 0)}
                for c in spec.outage_classes
            ],
            "excluded_base_outaged": list(population.excluded_base_outaged),
        },
        "sample_accounting": {
            "n_samples": n,
            "n_distinct_states": len(samples.states),
            "n_feasible_samples": by_outcome["feasible"],
            "n_infeasible_samples": by_outcome["infeasible"],
            "n_error_samples": by_outcome["error"],
            "n_invalid_samples": by_outcome["invalid"],
            "n_distinct_states_by_outcome": {
                k: sum(1 for r in records if r and r["outcome"] == k) for k in by_outcome
            },
        },
        "estimates": estimates,
        "convergence": convergence,
        "importance": importance,
        "states": states_out,
        "sample_state_index": list(samples.sample_state_index),
        "assumptions": STUDY_ASSUMPTIONS + list(base.assumptions),
        "limitations": STUDY_LIMITATIONS,
        "warnings": warnings,
    }
