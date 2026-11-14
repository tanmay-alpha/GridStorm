"""AC power-flow reference validation against MATPOWER / PYPOWER.

Three comparisons, all with the fixed :data:`~gridstorm_pandapower.powerflow.PF_OPTIONS`
(Newton-Raphson, mismatch tolerance 1e-8 MVA, generator Q limits not enforced):

1. ``matpower_testsuite`` — MATPOWER's own stored solution ``soln9_pf.mat`` for ``t_case9_pf.m``
   (MATPOWER test suite, ``lib/t``). Independent reference implementation (MATLAB/Octave).
2. ``matpower_cases`` — MATPOWER ``data/case{9,14,30,57,118,300}.m`` converted with this package's
   loader vs PYPOWER ``runpf`` on the identical case dict. PYPOWER is the Python port of MATPOWER;
   pandapower's NR solver derives from it, so this checks the conversion and id map (branch
   orientation, transformer model, shunts, loads) rather than the NR algorithm itself. The VM/VA
   columns stored in the MATPOWER files are also compared, for information only: they are not a
   consistent solved state for every case.
3. ``pandapower_builtin`` — ``pandapower.networks.case*`` (pandapower's bundled conversions) vs
   PYPOWER ``runpf`` on PYPOWER's bundled case of the same name (bus voltages, losses, slack P).

Power balance ``Σgen − Σload − Σshunt − losses`` is reported for every pandapower solution.
"""

from __future__ import annotations

import copy
import warnings

import numpy as np
import pandapower as pp
import pandapower.networks as pn
import scipy.io
from pypower import api as pypower_api
from pypower.api import ppoption, runpf

from .model import BUS_I, REFERENCE_DATA, VA, VM, model_from_ppc, read_mpc
from .powerflow import PF_OPTIONS, branch_flows, power_balance, run_pf

MATPOWER_DIR = REFERENCE_DATA / "matpower"
CASES = ("case9", "case14", "case30", "case57", "case118", "case300")

#: Acceptance tolerances for the reference comparisons.
TOLERANCES = {"vm_pu": 1e-6, "va_deg": 1e-4, "p_mw": 1e-3, "q_mvar": 1e-3}

# MATPOWER result columns
PG_COL, QG_COL = 1, 2
PF_COL, QF_COL, PT_COL, QT_COL = 13, 14, 15, 16


def _pypower_runpf(ppc: dict) -> dict:
    opt = ppoption(VERBOSE=0, OUT_ALL=0, PF_ALG=1,
                   PF_TOL=PF_OPTIONS["tolerance_mva"] / float(ppc["baseMVA"]),
                   PF_MAX_IT=PF_OPTIONS["max_iteration"], ENFORCE_Q_LIMS=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res, ok = runpf(copy.deepcopy(ppc), opt)
    if not ok:
        raise RuntimeError("PYPOWER runpf did not converge")
    return res


def _max_abs(a, b) -> float:
    return float(np.max(np.abs(np.asarray(a, float) - np.asarray(b, float))))


def _angle_diff(a, b) -> float:
    d = (np.asarray(a, float) - np.asarray(b, float) + 180.0) % 360.0 - 180.0
    return float(np.max(np.abs(d)))


def _compare_model(model, bus_ref: np.ndarray, branch_ref: np.ndarray | None,
                   gen_ref: np.ndarray | None) -> dict:
    """Compare a solved ``model.net`` with MATPOWER-format result arrays (rows in case order)."""
    net = model.net
    ids = bus_ref[:, BUS_I].astype(int)
    out = {
        "max_abs_dvm_pu": _max_abs(net.res_bus.vm_pu.loc[ids].values, bus_ref[:, VM]),
        "max_abs_dva_deg": _angle_diff(net.res_bus.va_degree.loc[ids].values, bus_ref[:, VA]),
    }
    if branch_ref is not None:
        flows = branch_flows(model)
        on = np.array([f["p_from_mw"] is not None for f in flows])
        pp_pq = np.array([[f["p_from_mw"], f["q_from_mvar"], f["p_to_mw"], f["q_to_mvar"]]
                          for f in flows if f["p_from_mw"] is not None], float)
        ref = branch_ref[on][:, [PF_COL, QF_COL, PT_COL, QT_COL]]
        out["max_abs_dp_branch_mw"] = _max_abs(pp_pq[:, [0, 2]], ref[:, [0, 2]])
        out["max_abs_dq_branch_mvar"] = _max_abs(pp_pq[:, [1, 3]], ref[:, [1, 3]])
        out["losses_mw"] = float(np.sum(pp_pq[:, 0] + pp_pq[:, 2]))
        out["reference_losses_mw"] = float(np.sum(ref[:, 0] + ref[:, 2]))
    if gen_ref is not None:
        pg, qg = [], []
        for g in model.gens:
            res = net[f"res_{g.table}"]
            pg.append(float(res.at[g.index, "p_mw"]))
            qg.append(float(res.at[g.index, "q_mvar"]))
        on = gen_ref[:, 7] > 0
        # Q is shared arbitrarily between several generators at one PV bus: compare per bus.
        out["max_abs_dpg_mw"] = _max_abs(np.array(pg)[on], gen_ref[on, PG_COL])
        qbus_pp: dict[int, float] = {}
        qbus_ref: dict[int, float] = {}
        for k in np.flatnonzero(on):
            b = int(gen_ref[k, 0])
            qbus_pp[b] = qbus_pp.get(b, 0.0) + qg[k]
            qbus_ref[b] = qbus_ref.get(b, 0.0) + gen_ref[k, QG_COL]
        out["max_abs_dqg_bus_mvar"] = _max_abs(list(qbus_pp.values()),
                                               [qbus_ref[b] for b in qbus_pp])
    bal = power_balance(net)
    out["balance_residual_mw"] = bal["residual_mw"]
    return out


def _passes(row: dict) -> bool:
    checks = [row["max_abs_dvm_pu"] <= TOLERANCES["vm_pu"],
              row["max_abs_dva_deg"] <= TOLERANCES["va_deg"]]
    for key, tol in (("max_abs_dp_branch_mw", "p_mw"), ("max_abs_dq_branch_mvar", "q_mvar"),
                     ("max_abs_dpg_mw", "p_mw"), ("max_abs_dqg_bus_mvar", "q_mvar")):
        if key in row:
            checks.append(row[key] <= TOLERANCES[tol])
    checks.append(abs(row["balance_residual_mw"]) <= TOLERANCES["p_mw"])
    return all(checks)


def _solve(model) -> None:
    pf = run_pf(model.net, init="flat")
    if not pf.converged:
        raise RuntimeError(f"pandapower power flow failed for {model.network_id}: {pf.error}")


def matpower_testsuite() -> dict:
    ppc = read_mpc(MATPOWER_DIR / "t_case9_pf.m")
    soln = scipy.io.loadmat(MATPOWER_DIR / "soln9_pf.mat")
    model = model_from_ppc(ppc, "t-case9-pf")
    _solve(model)
    row = {"case": "t_case9_pf", "reference": "MATPOWER soln9_pf.mat (lib/t)"}
    row.update(_compare_model(model, soln["bus_soln"], soln["branch_soln"], soln["gen_soln"]))
    row["pass"] = _passes(row)
    return row


def matpower_cases(cases: tuple[str, ...] = CASES) -> list[dict]:
    rows = []
    for name in cases:
        ppc = read_mpc(MATPOWER_DIR / f"{name}.m")
        ref = _pypower_runpf(ppc)
        model = model_from_ppc(ppc, name)
        _solve(model)
        row = {"case": name, "reference": "PYPOWER runpf on the same MATPOWER case"}
        row.update(_compare_model(model, ref["bus"], ref["branch"], ref["gen"]))
        row["pass"] = _passes(row)
        ids = ppc["bus"][:, BUS_I].astype(int)
        row["file_state_max_abs_dvm_pu"] = _max_abs(
            model.net.res_bus.vm_pu.loc[ids].values, ppc["bus"][:, VM])
        row["file_state_max_abs_dva_deg"] = _angle_diff(
            model.net.res_bus.va_degree.loc[ids].values, ppc["bus"][:, VA])
        row["conversion_notes"] = model.notes
        rows.append(row)
    return rows


def pandapower_builtin(cases: tuple[str, ...] = CASES) -> list[dict]:
    rows = []
    for name in cases:
        net = getattr(pn, name)()
        ref = _pypower_runpf(getattr(pypower_api, name)())
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pp.runpp(net, init="flat", **{k: v for k, v in PF_OPTIONS.items()})
        names = net.bus.name.astype(int).values
        refmap = {int(b): (vm, va) for b, vm, va in zip(ref["bus"][:, BUS_I], ref["bus"][:, VM],
                                                          ref["bus"][:, VA], strict=True)}
        rvm = np.array([refmap[b][0] for b in names])
        rva = np.array([refmap[b][1] for b in names])
        bal = power_balance(net)
        ref_losses = float(np.sum(ref["branch"][:, PF_COL] + ref["branch"][:, PT_COL]))
        slack_ref = float(sum(ref["gen"][k, PG_COL] for k in range(ref["gen"].shape[0])
                              if int(ref["gen"][k, 0]) in set(
                                  ref["bus"][ref["bus"][:, 1] == 3, BUS_I].astype(int))))
        row = {
            "case": name,
            "reference": "PYPOWER runpf on PYPOWER's bundled case",
            "max_abs_dvm_pu": _max_abs(net.res_bus.vm_pu.values, rvm),
            "max_abs_dva_deg": _angle_diff(net.res_bus.va_degree.values, rva),
            "losses_mw": bal["losses_mw"],
            "reference_losses_mw": ref_losses,
            "abs_dlosses_mw": abs(bal["losses_mw"] - ref_losses),
            "slack_p_mw": float(net.res_ext_grid.p_mw.sum()),
            "reference_slack_p_mw": slack_ref,
            "balance_residual_mw": bal["residual_mw"],
        }
        row["pass"] = (_passes(row) and row["abs_dlosses_mw"] <= TOLERANCES["p_mw"]
                       and abs(row["slack_p_mw"] - slack_ref) <= TOLERANCES["p_mw"])
        rows.append(row)
    return rows


def _fmt(obj):
    if isinstance(obj, float):
        return float(f"{obj:.4e}")
    if isinstance(obj, dict):
        return {k: _fmt(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fmt(v) for v in obj]
    return obj


def reference_payload(cases: tuple[str, ...] = CASES) -> dict:
    suite = matpower_testsuite()
    mp = matpower_cases(cases)
    builtin = pandapower_builtin(cases)
    return _fmt({
        "title": "AC power flow reference validation (pandapower vs MATPOWER/PYPOWER)",
        "method": {
            "power_flow": "pandapower.runpp Newton-Raphson, flat start",
            "tolerance_mva": PF_OPTIONS["tolerance_mva"],
            "max_iteration": PF_OPTIONS["max_iteration"],
            "enforce_q_lims": PF_OPTIONS["enforce_q_lims"],
            "reference_pypower": "pypower.runpf (PF_ALG=1 Newton, PF_TOL = tolerance_mva/baseMVA)",
            "angles": "differences wrapped to [-180, 180) degrees",
            "tolerances": TOLERANCES,
        },
        "matpower_testsuite": suite,
        "matpower_cases": mp,
        "pandapower_builtin": builtin,
        "summary": {
            "all_pass": bool(suite["pass"] and all(r["pass"] for r in mp)
                             and all(r["pass"] for r in builtin)),
            "max_abs_dvm_pu": max(r["max_abs_dvm_pu"] for r in [suite, *mp, *builtin]),
            "max_abs_dva_deg": max(r["max_abs_dva_deg"] for r in [suite, *mp, *builtin]),
            "max_abs_dp_branch_mw": max(r["max_abs_dp_branch_mw"] for r in [suite, *mp]),
            "max_abs_balance_residual_mw": max(abs(r["balance_residual_mw"])
                                               for r in [suite, *mp, *builtin]),
        },
    })
