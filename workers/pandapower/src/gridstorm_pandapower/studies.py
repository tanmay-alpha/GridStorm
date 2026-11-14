"""N-1 study payloads and gridstorm-artifact/1.0 wrapping (contract §5)."""

from __future__ import annotations

import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandapower as pp
from stormspec import file_sha256, payload_sha256

from .contingency import (
    LOADING_TOL_PCT,
    VM_TOL_PU,
    contingency_study,
    energised_buses,
    evaluate_state,
    total_load_mw,
)
from .model import GridModel, load_matpower
from .operating_point import apply_acopf_dispatch
from .powerflow import PF_OPTIONS, power_balance, run_pf

REPO_ROOT = Path(__file__).resolve().parents[4]

N1_ASSUMPTIONS = [
    "Steady-state balanced AC power flow (Newton-Raphson); no protection, dynamics or transient "
    "stability.",
    "Base operating point: pandapower AC-OPF (PIPS) generator set points; contingencies are not "
    "re-dispatched (generators keep P and voltage set points, the single slack absorbs imbalance).",
    "Generator reactive limits are not enforced in the post-contingency power flow.",
    "Thermal limit: apparent power at either branch end vs MATPOWER RATE_A (MVA); RATE_A = 0 means "
    "unlimited.",
]


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def wrap_artifact(*, artifact_id: str, kind: str, network_id: str | None, command: str,
                  inputs: list[Path], payload: dict) -> dict:
    return {
        "artifact": {
            "schema_version": "gridstorm-artifact/1.0",
            "artifact_id": artifact_id,
            "kind": kind,
            "engine": "pandapower",
            "engine_version": pp.__version__,
            "network_id": network_id,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "command": command,
            "inputs": [{"path": rel(p), "sha256": file_sha256(p)} for p in inputs],
            "platform": f"{platform.system()}-{platform.release()}-{platform.machine()} "
                        f"Python {sys.version.split()[0]}",
            "execution_mode": "precomputed",
            "payload_sha256": payload_sha256(payload),
        },
        "payload": payload,
    }


def prepare_base(model: GridModel) -> dict:
    """AC-OPF dispatch + base AC power flow; returns the base-case summary block."""
    opf = apply_acopf_dispatch(model)
    pf = run_pf(model.net, init="dc")
    if not pf.converged:
        raise RuntimeError(f"base-case power flow failed for {model.network_id}: {pf.error}")
    st = evaluate_state(model, model.net, total_load_mw=total_load_mw(model.net),
                        base_energised=energised_buses(model.net))
    bal = power_balance(model.net)
    return {
        "operating_point": "acopf" if opf["converged"] else "case_file_setpoints",
        "acopf": {
            "converged": opf["converged"],
            "objective_cost": round(opf["objective"], 2) if opf["objective"] is not None else None,
            "opf_wall_time_s": round(opf["wall_time_s"], 3),
            "message": opf["message"],
        },
        "converged": True,
        "classes": st["flags"] or ["secure"],
        "max_loading_pct": round(st["max_loading_pct"], 2),
        "max_loading_element": st["max_loading_element"],
        "min_vm_pu": round(st["min_vm_pu"], 4),
        "max_vm_pu": round(st["max_vm_pu"], 4),
        "overloads": st["overloads"],
        "voltage_violations": st["voltage_violations"],
        "losses_mw": round(bal["losses_mw"], 3),
        "load_mw": round(bal["load_mw"], 3),
        "generation_mw": round(bal["generation_mw"], 3),
        "balance_residual_mw": float(f"{bal['residual_mw']:.3e}"),
    }


def n1_payload(network_id: str, case_path: Path, *, title: str, n2_top_k: int) -> dict:
    model = load_matpower(case_path, network_id)
    base = prepare_base(model)
    study = contingency_study(model, n2_top_k=n2_top_k)
    n_lines = sum(b.component == "line" for b in model.branches)
    return {
        "network_id": network_id,
        "title": title,
        "source": {
            "case_file": rel(case_path),
            "sha256": file_sha256(case_path),
            "bus_count": len(model.buses),
            "line_count": n_lines,
            "transformer_count": len(model.branches) - n_lines,
            "generator_count": len(model.gens),
            "load_count": len(model.loads),
            "conversion_notes": model.notes,
        },
        "method": {
            "power_flow": "pandapower.runpp Newton-Raphson",
            "algorithm": PF_OPTIONS["algorithm"],
            "tolerance_mva": PF_OPTIONS["tolerance_mva"],
            "max_iteration": PF_OPTIONS["max_iteration"],
            "enforce_q_lims": PF_OPTIONS["enforce_q_lims"],
            "init": "results (base-case solution)",
            "vm_limits_source": model.vm_limits_source,
            "vm_tolerance_pu": VM_TOL_PU,
            "rating": "RATE_A (MVA), loading = 100*max(|S_from|,|S_to|)/RATE_A",
            "loading_tolerance_pct": LOADING_TOL_PCT,
            "severity": "sum((L/100-1)^2 over overloads) + sum((dV/0.05)^2) + 100*islanded_load/"
                        "total_load; null for non_convergent/error (ranked first)",
            "class_precedence": "error > non_convergent > islanding > thermal_overload > "
                                "voltage_violation > secure",
        },
        "base_case": base,
        "summary": study["summary"],
        "contingencies": study["contingencies"],
        "n_minus_2": study["n_minus_2"],
        "assumptions": N1_ASSUMPTIONS,
    }
