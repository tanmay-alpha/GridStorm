"""pandapower side of the cross-engine harness (run inside the pandapower worker env).

    uv run --project workers/pandapower python tests/cross_engine/pp_side.py <network_id>

Loads the raw PGLib ``.m`` exactly as ``pandapower.converter.from_mpc`` does — ``_m2ppc`` (parsed by
``matpowercaseframes``) followed by ``from_ppc`` — with only the generator PG column replaced by the
harness fixed dispatch in between. The matpowercaseframes parse is cross-checked against the harness
parser (mpc.load_case) element by element. Then it runs:
  * ``rundcpp``  -> DC branch flows / angles / injections
  * ``runpp``    -> AC Newton-Raphson branch flows (same P setpoints, PGLib Vg setpoints)
  * ``rundcopp`` -> DC OPF with the PGLib polynomial costs converted by from_ppc
plus the numpy MATPOWER-formula reference DC PF and scipy-HiGHS DC OPF (engine-free arbiter).
Writes tests/cross_engine/_work/<id>.pandapower.json and <id>.reference.json.
"""

from __future__ import annotations

import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mpc  # noqa: E402
import numpy as np  # noqa: E402
import pandapower as pp  # noqa: E402
from pandapower.converter.matpower.from_mpc import _m2ppc  # noqa: E402
from pandapower.converter.pypower.from_ppc import from_ppc  # noqa: E402

# from_mpc's _adjust_ppc_indices subtracts 1 from BUS_I, so pandapower bus index = BUS_I - 1.
BUS_OFFSET = 1


def _parser_crosscheck(ppc: dict, case: dict) -> dict:
    """Exact comparison of matpowercaseframes' parse (as adjusted by from_mpc) with load_case."""

    def adj(a: np.ndarray, cols: list[int]) -> np.ndarray:
        a = a.copy()
        a[:, cols] -= BUS_OFFSET
        return a

    branch = adj(case["branch"], [mpc.F_BUS, mpc.T_BUS])
    branch[:, mpc.TAP] = np.where(
        branch[:, mpc.TAP] == 0.0, 1.0, branch[:, mpc.TAP]
    )  # from_mpc does too
    pairs = {
        "bus": (np.asarray(ppc["bus"], float)[:, :13], adj(case["bus"], [mpc.BUS_I])[:, :13]),
        "gen": (np.asarray(ppc["gen"], float)[:, :10], adj(case["gen"], [mpc.GEN_BUS])[:, :10]),
        "branch": (np.asarray(ppc["branch"], float)[:, :13], branch[:, :13]),
        "gencost": (np.asarray(ppc["gencost"], float), case["gencost"]),
    }
    out = {"baseMVA_equal": float(ppc["baseMVA"]) == case["baseMVA"]}
    for k, (a, b) in pairs.items():
        if a.shape != b.shape:
            raise ValueError(f"parser cross-check: {k} shape {a.shape} != {b.shape}")
        out[f"{k}_max_abs_diff"] = float(np.max(np.abs(a - b)))
    if not out["baseMVA_equal"] or any(v != 0.0 for k, v in out.items() if k.endswith("diff")):
        raise ValueError(f"matpowercaseframes and harness parser disagree: {out}")
    return out


def _branch_results(net, case: dict, ac: bool) -> dict:
    lookup = net._from_ppc_lookups["branch"]
    out_from, out_to = {}, {}
    for row, (elem, etype) in enumerate(
        zip(lookup["element"], lookup["element_type"], strict=True)
    ):
        fbus = int(case["branch"][row, mpc.F_BUS]) - BUS_OFFSET
        e = int(elem)
        if etype == "line":
            pf, pt = net.res_line.at[e, "p_from_mw"], net.res_line.at[e, "p_to_mw"]
            assert int(net.line.at[e, "from_bus"]) == fbus
        elif etype == "trafo":
            hv_is_from = int(net.trafo.at[e, "hv_bus"]) == fbus
            pf = net.res_trafo.at[e, "p_hv_mw" if hv_is_from else "p_lv_mw"]
            pt = net.res_trafo.at[e, "p_lv_mw" if hv_is_from else "p_hv_mw"]
        elif etype == "impedance":
            pf, pt = net.res_impedance.at[e, "p_from_mw"], net.res_impedance.at[e, "p_to_mw"]
        else:
            raise ValueError(f"unmapped branch row {row + 1}: {etype!r}")
        out_from[mpc.branch_id(row)] = float(pf)
        out_to[mpc.branch_id(row)] = float(pt)
    res = {"branch_flow_mw": out_from}
    if ac:
        res["branch_flow_to_mw"] = out_to
    return res


def _bus_results(net) -> dict:
    return {
        "bus_angle_deg": {
            mpc.bus_id(i + BUS_OFFSET): float(v) for i, v in net.res_bus["va_degree"].items()
        },
        # pandapower res_bus.p_mw is consumption-positive; contract injections are
        # generation-positive.
        "bus_injection_mw": {
            mpc.bus_id(i + BUS_OFFSET): float(-v) for i, v in net.res_bus["p_mw"].items()
        },
    }


def _gen_results(net) -> dict:
    lookup = net._from_ppc_lookups["gen"]
    out = {}
    for row, (elem, etype) in enumerate(
        zip(lookup["element"], lookup["element_type"], strict=True)
    ):
        if etype == "":
            continue
        out[mpc.gen_id(row)] = float(net[f"res_{etype}"].at[int(elem), "p_mw"])
    return out


def main(network_id: str) -> None:
    src = mpc.source_path(network_id)
    case = mpc.load_case(src)
    dispatch = mpc.fixed_dispatch(case)

    ppc = _m2ppc(str(src))
    crosscheck = _parser_crosscheck(ppc, case)
    for gid, p in dispatch["gen_p_mw"].items():
        ppc["gen"][int(gid.split("-")[1]) - 1, mpc.PG] = p
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        net = from_ppc(ppc, f_hz=60)
    lookup = net._from_ppc_lookups["branch"]
    conversion = {
        "lines": int((lookup["element_type"] == "line").sum()),
        "trafos": int((lookup["element_type"] == "trafo").sum()),
        "impedances": int((lookup["element_type"] == "impedance").sum()),
        "ext_grids": int(len(net.ext_grid)),
        "gens": int(len(net.gen)),
        "sgens": int(len(net.sgen)),
        "loads": int(len(net.load)),
        "shunts": int(len(net.shunt)),
        "ext_grid_bus": mpc.bus_id(net.ext_grid.bus.iloc[0] + BUS_OFFSET),
        "loader": "pandapower.converter.matpower.from_mpc steps "
        "(_m2ppc via matpowercaseframes, from_ppc)",
        "parser_crosscheck": crosscheck,
    }

    out = {
        "network_id": network_id,
        "source": {"path": mpc.display_path(src), "sha256": mpc.sha256_file(src)},
        "engine": {"name": "pandapower", "version": pp.__version__},
        "dispatch": dispatch,
        "conversion": conversion,
    }

    t0 = time.perf_counter()
    pp.rundcpp(net, calculate_voltage_angles=True)
    out["dc"] = {
        "converged": bool(net.converged),
        "wall_time_s": time.perf_counter() - t0,
        **_branch_results(net, case, ac=False),
        **_bus_results(net),
        "gen_p_mw": _gen_results(net),
    }

    t0 = time.perf_counter()
    try:
        pp.runpp(
            net,
            algorithm="nr",
            calculate_voltage_angles=True,
            init="dc",
            max_iteration=50,
            enforce_q_lims=False,
        )
        ac = {"converged": bool(net.converged)}
    except pp.LoadflowNotConverged:
        ac = {"converged": False}
    ac["wall_time_s"] = time.perf_counter() - t0
    if ac["converged"]:
        ac.update(_branch_results(net, case, ac=True))
        ac.update(_bus_results(net))
        ac["gen_p_mw"] = _gen_results(net)
        ac["vm_pu_min"] = float(net.res_bus.vm_pu.min())
        ac["vm_pu_max"] = float(net.res_bus.vm_pu.max())
        ac["total_losses_mw"] = float(net.res_line.pl_mw.sum() + net.res_trafo.pl_mw.sum())
        ac["ext_grid_p_mw"] = float(net.res_ext_grid.p_mw.sum())
        ac["settings"] = {
            "algorithm": "nr",
            "init": "dc",
            "enforce_q_lims": False,
            "voltage_setpoints": "PGLib Vg (flat start case)",
        }
    out["ac"] = ac

    t0 = time.perf_counter()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pp.rundcopp(net)
        opf = {"converged": bool(net.OPF_converged)}
    except Exception as exc:  # pandapower raises OPFNotConverged and solver errors
        opf = {"converged": False, "error": f"{type(exc).__name__}: {exc}"}
    opf["wall_time_s"] = time.perf_counter() - t0
    if opf["converged"]:
        opf["objective"] = float(net.res_cost)
        opf["gen_p_mw"] = _gen_results(net)
        opf.update(_branch_results(net, case, ac=False))
        opf["solver"] = "pandapower rundcopp (PIPS interior point)"
    out["dcopf"] = opf

    mpc.write_json(mpc.WORK / f"{network_id}.pandapower.json", out)

    ref = {
        "network_id": network_id,
        "engine": {"name": "matpower-formula-numpy", "version": f"numpy {np.__version__}"},
        "dispatch": dispatch,
        "dc": mpc.reference_dcpf(case, dispatch),
        "dcopf": mpc.reference_dcopf(case),
        "branch_meta": [
            {
                "id": mpc.branch_id(i),
                "from": mpc.bus_id(r[mpc.F_BUS]),
                "to": mpc.bus_id(r[mpc.T_BUS]),
                "x_pu": float(r[mpc.BR_X]),
                "r_pu": float(r[mpc.BR_R]),
                "b_pu": float(r[mpc.BR_B]),
                "rate_a_mva": float(r[mpc.RATE_A]),
                "tap": float(r[mpc.TAP]),
                "shift_deg": float(r[mpc.SHIFT]),
                "status": int(r[mpc.BR_STATUS]),
            }
            for i, r in enumerate(case["branch"])
        ],
        "case_features": {
            "n_bus": int(len(case["bus"])),
            "n_branch": int(len(case["branch"])),
            "n_gen": int(len(case["gen"])),
            "n_tap_ne_1": int(
                np.sum((case["branch"][:, mpc.TAP] != 0) & (case["branch"][:, mpc.TAP] != 1))
            ),
            "n_phase_shifters": int(np.sum(case["branch"][:, mpc.SHIFT] != 0)),
            "n_bus_gs_nonzero": int(np.sum(case["bus"][:, mpc.GS] != 0)),
            "n_bus_bs_nonzero": int(np.sum(case["bus"][:, mpc.BS] != 0)),
            "n_branch_out_of_service": int(np.sum(case["branch"][:, mpc.BR_STATUS] == 0)),
            "n_parallel_branch_pairs": int(
                len(case["branch"]) - len({tuple(sorted((r[0], r[1]))) for r in case["branch"]})
            ),
            "base_kv_values": sorted({float(v) for v in case["bus"][:, mpc.BASE_KV]}),
            "gencost_max_order": int(case["gencost"][:, 3].max()) - 1
            if case["gencost"] is not None
            else None,
            "gencost_has_quadratic_terms": bool(
                case["gencost"] is not None
                and np.any(case["gencost"][:, 3] >= 3)
                and np.any(case["gencost"][case["gencost"][:, 3] >= 3, 4] != 0)
            ),
        },
    }
    mpc.write_json(mpc.WORK / f"{network_id}.reference.json", ref)
    print(
        f"pandapower side done: {network_id} dc={out['dc']['converged']} ac={ac['converged']} "
        f"dcopf={opf['converged']}"
    )


if __name__ == "__main__":
    for nid in sys.argv[1:] or list(mpc.CASES):
        main(nid)
