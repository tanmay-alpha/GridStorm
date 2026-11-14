"""PyPSA side of the cross-engine harness (run inside a PyPSA env, e.g. the network importer's).

    uv run --project pipelines/network-import python tests/cross_engine/pypsa_side.py <network_id>

Loads ``data/networks/<id>/network.nc`` (the artifact GridStorm actually simulates on).
The file must already exist: this harness does not rebuild or modify the imported network.
It runs both the original PGLib PG/PD power flow and a headroom-balanced dispatch / loads
on the first snapshot, then runs:
  * ``n.lpf()``      -> linear (DC) power flow branch flows / angles / injections
  * ``n.optimize()`` -> linear OPF (HiGHS) with the importer's cost model, same loads
It also exports, per branch, the effective series reactance PyPSA uses (``x_pu_eff`` re-based to
the MATPOWER baseMVA) so that disagreements can be traced to a parameter rather than guessed.
Writes tests/cross_engine/_work/<id>.pypsa.json.
"""

from __future__ import annotations

import logging
import sys
import time
import warnings
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mpc  # noqa: E402
import numpy as np  # noqa: E402
import pypsa  # noqa: E402

logging.getLogger("pypsa").setLevel(logging.WARNING)
logging.getLogger("linopy").setLevel(logging.WARNING)


def _set_injections(n: pypsa.Network, dispatch: dict, sns, *, fix_generators: bool) -> dict:
    """Force load p_set (and, for power flow, generator p_set) to the harness values.

    PyPSA 1.x treats a non-NaN generator ``p_set`` as a FIXED dispatch inside ``optimize()``, so for
    the OPF run (``fix_generators=False``) generator p_set is reset to NaN (free dispatch) and the
    number of generators that arrived from network.nc with a non-NaN p_set is reported.
    """
    issues: list[str] = []
    gens = n.c.generators.static
    loads = n.c.loads.static
    gen_dyn = n.c.generators.dynamic["p_set"]
    importer_fixed = int(gens.p_set.notna().sum()) + int(len(gen_dyn.columns))
    targets = [("loads", dispatch["load_p_mw"])]
    if fix_generators:
        targets.append(("generators", dispatch["gen_p_mw"]))
    else:
        if len(gen_dyn.columns):
            gen_dyn.drop(columns=list(gen_dyn.columns), inplace=True)
        gens["p_set"] = np.nan
    for comp, values in targets:
        static = n.c[comp].static
        dyn = n.c[comp].dynamic["p_set"]
        if len(dyn.columns):
            dyn.drop(columns=list(dyn.columns), inplace=True)
        static["p_set"] = 0.0
        for k, v in values.items():
            if k in static.index:
                static.loc[k, "p_set"] = v
            elif v != 0.0:
                issues.append(f"{comp[:-1]} {k} with p={v} MW is missing from network.nc")
    extra_gens = sorted(set(gens.index) - set(dispatch["gen_p_mw"]))
    extra_loads = sorted(set(loads.index) - set(dispatch["load_p_mw"]))
    if extra_gens:
        issues.append(f"generators not in the MATPOWER case (PF p_set forced to 0): {extra_gens}")
    if extra_loads:
        issues.append(f"loads not in the MATPOWER case (p_set forced to 0): {extra_loads}")
    # Read back exactly what PyPSA will use.
    g = n.get_switchable_as_dense("Generator", "p_set", sns).iloc[0]
    ld = n.get_switchable_as_dense("Load", "p_set", sns).iloc[0]
    return {
        "issues": issues,
        "generators_with_p_set_in_network_nc": importer_fixed,
        "total_gen_p_set_mw": float(g.sum()) if fix_generators else None,
        "total_load_p_set_mw": float(ld.sum()),
    }


def _branches(n: pypsa.Network, case: dict) -> tuple[dict, list[str]]:
    """Map MATPOWER branch rows to PyPSA passive branches; return orientation sign per id."""
    issues = []
    sign: dict[str, tuple[str, float]] = {}
    lines, trafos = n.c.lines.static, n.c.transformers.static
    for row, br in enumerate(case["branch"]):
        bid = mpc.branch_id(row)
        if bid in lines.index:
            comp, s = "Line", lines.loc[bid]
        elif bid in trafos.index:
            comp, s = "Transformer", trafos.loc[bid]
        else:
            if br[mpc.BR_STATUS] > 0:
                issues.append(f"in-service {bid} missing from network.nc")
            continue
        fb, tb = mpc.bus_id(br[mpc.F_BUS]), mpc.bus_id(br[mpc.T_BUS])
        if (s.bus0, s.bus1) == (fb, tb):
            sign[bid] = (comp, 1.0)
        elif (s.bus0, s.bus1) == (tb, fb):
            sign[bid] = (comp, -1.0)
            issues.append(
                f"{bid} stored reversed (bus0={s.bus0}); flow sign flipped for comparison"
            )
        else:
            issues.append(f"{bid} connects {s.bus0}-{s.bus1}, MATPOWER says {fb}-{tb}")
    return sign, issues


def _param_audit(n: pypsa.Network, sign: dict, base: float) -> dict:
    """Effective series reactance used by LPF, on the MATPOWER system base (pu)."""
    lines, trafos = n.c.lines.static, n.c.transformers.static
    out = {}
    for bid, (comp, _) in sign.items():
        if comp == "Line":
            r = lines.loc[bid]
            out[bid] = {
                "component": comp,
                "x_eff_pu": float(r.x_pu_eff * base),
                "s_nom_mva": float(r.s_nom),
                "s_max_pu": float(r.s_max_pu),
                "num_parallel": float(r.num_parallel),
                "v_nom_kv": float(r.v_nom),
            }
        else:
            r = trafos.loc[bid]
            out[bid] = {
                "component": comp,
                "x_eff_pu": float(r.x_pu_eff * base),
                "s_nom_mva": float(r.s_nom),
                "s_max_pu": float(r.s_max_pu),
                "tap_ratio": float(r.tap_ratio),
                "tap_side": int(r.tap_side),
                "phase_shift_deg": float(r.phase_shift),
            }
    return out


def _flows(n: pypsa.Network, sign: dict, sn, which: str = "p0") -> dict:
    lines_p = n.c.lines.dynamic[which]
    tr_p = n.c.transformers.dynamic[which]
    out = {}
    for bid, (comp, s) in sign.items():
        df = lines_p if comp == "Line" else tr_p
        out[bid] = float(s * df.at[sn, bid])
    return out


def _load(nc: Path) -> pypsa.Network:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return pypsa.Network(str(nc))


def _network_file(network_id: str) -> tuple[Path, str]:
    nc = mpc.NETWORKS / network_id / "network.nc"
    if not nc.is_file():
        raise FileNotFoundError(f"{nc}: run the network importer before this benchmark")
    return nc, "data/networks network.nc"


def _dc_results(n: pypsa.Network, sign: dict, sn, base: float) -> dict:
    sub = n.c.sub_networks.static
    vang = n.c.buses.dynamic.v_ang.loc[sn]
    return {
        "sub_networks": int(len(sub)),
        "slack_buses": sorted(str(b) for b in sub.slack_bus),
        "branch_flow_mw": _flows(n, sign, sn),
        "bus_angle_deg": {str(b): float(np.rad2deg(v)) for b, v in vang.items()},
        "bus_injection_mw": {str(b): float(v) for b, v in n.c.buses.dynamic.p.loc[sn].items()},
        "gen_p_mw": {str(g): float(v) for g, v in n.c.generators.dynamic.p.loc[sn].items()},
        "param_audit": _param_audit(n, sign, base),
    }


def main(network_id: str) -> None:
    src = mpc.source_path(network_id)
    nc, nc_origin = _network_file(network_id)
    case = mpc.load_case(src)
    dispatch = mpc.fixed_dispatch(case)
    base = case["baseMVA"]

    n = _load(nc)
    sns = n.snapshots[:1]
    sn = sns[0]
    sign, branch_issues = _branches(n, case)
    inj = _set_injections(n, dispatch, sns, fix_generators=True)

    gens = n.c.generators.static
    model = {
        "snapshots_in_file": int(len(n.snapshots)),
        "snapshot_used": str(sn),
        "snapshot_weighting_objective_h": float(n.snapshot_weightings.objective.iloc[0]),
        "counts": {
            c: int(len(n.c[c].static))
            for c in (
                "buses",
                "lines",
                "transformers",
                "generators",
                "loads",
                "shunt_impedances",
                "links",
                "storage_units",
                "stores",
            )
        },
        "generator_control": {k: str(v) for k, v in gens.control.items() if v != "PQ"},
        "generator_cost": {
            k: {
                "marginal_cost": float(r.marginal_cost),
                "marginal_cost_quadratic": float(r.get("marginal_cost_quadratic", 0.0)),
                "p_nom_mw": float(r.p_nom),
                "p_min_pu": float(r.p_min_pu),
                "p_max_pu": float(r.p_max_pu),
                "committable": bool(r.get("committable", False)),
            }
            for k, r in gens.iterrows()
        },
        "generator_carriers": sorted({str(c) for c in gens.carrier}),
    }

    out = {
        "network_id": network_id,
        "source": {"path": mpc.display_path(src), "sha256": mpc.sha256_file(src)},
        "network_nc": {
            "path": mpc.display_path(nc),
            "sha256": mpc.sha256_file(nc),
            "origin": nc_origin,
        },
        "engine": {"name": "pypsa", "version": pypsa.__version__},
        "dispatch": dispatch,
        "model": model,
        "mapping_issues": branch_issues + inj["issues"],
        "injection_readback": {k: v for k, v in inj.items() if k != "issues"},
    }
    raw_dispatch = mpc.fixed_dispatch(case, balance=False)
    raw_n = _load(nc)
    raw_inj = _set_injections(raw_n, raw_dispatch, sns, fix_generators=True)
    if raw_inj["issues"]:
        raise ValueError(raw_inj["issues"])
    raw_n.lpf(snapshots=sns)
    out["raw_dispatch"] = raw_dispatch
    out["raw_dc"] = _dc_results(raw_n, sign, sn, base)

    t0 = time.perf_counter()
    n.lpf(snapshots=sns)
    out["dc"] = {
        "wall_time_s": time.perf_counter() - t0,
        **_dc_results(n, sign, sn, base),
    }

    # Linear OPF with the importer's own cost model on a freshly loaded copy (no PF side effects);
    # loads at PD, generator dispatch free.
    n = _load(nc)
    inj_opf = _set_injections(n, dispatch, sns, fix_generators=False)
    t0 = time.perf_counter()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            status, cond = n.optimize(
                snapshots=sns, solver_name="highs", solver_options={"threads": 1, "random_seed": 0}
            )
        opf = {"status": str(status), "termination_condition": str(cond)}
    except Exception as exc:
        opf = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    opf["wall_time_s"] = time.perf_counter() - t0
    opf["injection_readback"] = {k: v for k, v in inj_opf.items() if k != "issues"}
    if opf.get("status") == "ok":
        w = model["snapshot_weighting_objective_h"]
        opf["objective"] = float(n.objective) / w
        opf["objective_constant"] = float(getattr(n, "objective_constant", 0.0) or 0.0) / w
        opf["gen_p_mw"] = {str(g): float(v) for g, v in n.c.generators.dynamic.p.loc[sn].items()}
        opf["branch_flow_mw"] = _flows(n, sign, sn)
        opf["solver"] = (
            f"HiGHS (highspy {metadata.version('highspy')}) via linopy {metadata.version('linopy')}"
        )
    out["dcopf"] = opf

    mpc.write_json(mpc.WORK / f"{network_id}.pypsa.json", out)
    print(
        f"pypsa side done: {network_id} issues={len(out['mapping_issues'])} opf={opf.get('status')}"
    )


if __name__ == "__main__":
    for nid in sys.argv[1:] or list(mpc.CASES):
        main(nid)
