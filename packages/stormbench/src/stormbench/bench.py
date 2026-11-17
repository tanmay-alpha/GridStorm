"""StormBench runner: DC PTDF/LODF screening vs exact DC and AC N-1 re-solves on PGLib-OPF cases.

Every in-service branch outage is one contingency. Pipeline per case:

1. operating point: DC-OPF on the PGLib case (``opf.solve_dc_opf``) or, where that dispatch has no
   AC power-flow solution, the published IEEE dispatch (see ``OPERATING_POINT``);
2. screening: build B matrices, PTDF, LODF, f_k^(l) = f_k + LODF_kl f_l, bridge (islanding) check;
3. exact DC: refactorise the reduced B matrix per outage;
4. exact AC: pandapower Newton-Raphson ``runpp`` per outage with convergence classification;
5. metrics (``metrics.compare``), runtimes (median of ``repeats``), tracemalloc peaks (own pass).

Determinism: no random numbers are used; HiGHS LP and all linear algebra are deterministic for a
fixed platform/library build. Thread count is pinned to 1 by the caller (env vars). Across
platforms (OpenBLAS kernel dispatch by CPU, compilers) severities differ by round-off
(~1e-13 pp on case14/case30), so every ranking uses ``metrics`` tie groups (``TOL_PCT``).
"""

from __future__ import annotations

import gc
import hashlib
import json
import logging
import os
import platform
import statistics
import subprocess
import sys
import time
import tracemalloc
import warnings
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

import numpy as np

from . import dc, metrics, opf
from .matpower import BR_STATUS, BUS_I, GEN_BUS, PG, VG, VMAX, VMIN, MatpowerCase, parse_matpower

REPO_ROOT = Path(__file__).resolve().parents[4]
CASES_DIR = REPO_ROOT / "benchmarks" / "stormbench" / "cases"
DEFAULT_CASES = [
    "case14_ieee",
    "case30_ieee",
    "case57_ieee",
    "case118_ieee",
    "case300_ieee",
    "case1354_pegase",
]
CI_CASES = ["case14_ieee", "case30_ieee"]
PGLIB_COMMIT = "dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3"
#: case300_ieee: the DC-OPF dispatch (and the PGLib file's own PG with VG = 1) has no AC Newton
#: solution (measured: pandapower runpp LoadflowNotConverged with dc and flat init), so the
#: published IEEE 300-bus dispatch / generator voltage set-points (pandapower.networks.case300)
#: are used.
OPERATING_POINT = {"case300_ieee": "ieee_published_dispatch"}
THRESHOLD = 100.0
AC_ATTEMPTS = ({"init": "dc", "max_iteration": 30}, {"init": "flat", "max_iteration": 60})


def _sig(x, digits: int = 4):
    """Round floats to ``digits`` significant digits (contract §5); recurse into containers."""
    if isinstance(x, dict):
        return {k: _sig(v, digits) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_sig(v, digits) for v in x]
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, float | np.floating):
        x = float(x)
        if not np.isfinite(x):
            return None
        return float(f"{x:.{digits}g}")
    return x


def environment() -> dict:
    import psutil

    vers = {}
    for pkg in ("numpy", "scipy", "pandapower", "numba", "psutil"):
        try:
            vers[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            vers[pkg] = None
    cpu = platform.processor()
    if sys.platform == "win32":
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "(Get-CimInstance Win32_Processor).Name"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            ).stdout.strip()
            cpu = out or cpu
        except OSError:
            pass
    return {
        "python": platform.python_version(),
        "packages": vers,
        "os": platform.platform(),
        "cpu": cpu,
        "logical_cpus": psutil.cpu_count(logical=True),
        "ram_gib": round(psutil.virtual_memory().total / 2**30, 1),
        "threads": {
            k: os.environ.get(k)
            for k in (
                "OMP_NUM_THREADS",
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "NUMBA_NUM_THREADS",
            )
        },
    }


# ----------------------------------------------------------------------------- operating point
def published_case300_dispatch(case: MatpowerCase) -> MatpowerCase:
    import pandapower as pp
    import pandapower.networks as pn

    ref = pn.case300()
    pp.runpp(ref)
    per_bus: dict[int, list[float]] = {}
    names = ref.bus["name"]
    for b, vm, p in zip(
        names.loc[ref.gen.bus].to_numpy(), ref.gen.vm_pu, ref.gen.p_mw, strict=True
    ):
        per_bus.setdefault(int(b), [0.0, float(vm)])[0] += float(p)
    for b, vm, p in zip(
        names.loc[ref.ext_grid.bus].to_numpy(),
        ref.ext_grid.vm_pu,
        ref.res_ext_grid.p_mw,
        strict=True,
    ):
        per_bus.setdefault(int(b), [0.0, float(vm)])[0] += float(p)
    counts: dict[int, int] = {}
    for b in case.gen[:, GEN_BUS].astype(int):
        counts[int(b)] = counts.get(int(b), 0) + 1
    gb = case.gen[:, GEN_BUS].astype(int)
    case.gen[:, PG] = [per_bus[int(b)][0] / counts[int(b)] for b in gb]
    case.gen[:, VG] = [per_bus[int(b)][1] for b in gb]
    return case


def operating_point(case: MatpowerCase) -> dict:
    method = OPERATING_POINT.get(case.name, "dc_opf_highs")
    if method == "ieee_published_dispatch":
        published_case300_dispatch(case)
        return {
            "method": method,
            "note": "DC-OPF dispatch has no AC power-flow solution for this case; IEEE published "
            "dispatch and voltage set-points (pandapower.networks.case300) used instead. The DC "
            "base case then has pre-existing overloads, excluded from contingency flagging.",
        }
    net = dc.build_dc_network(case)
    r = opf.solve_dc_opf(case, net)
    if r.pg_mw is None:
        raise RuntimeError(f"{case.name}: DC-OPF failed: {r.status}")
    case.gen[:, PG] = r.pg_mw
    return {
        "method": method,
        "note": "DC-OPF (B-theta, PGLib costs as 10-segment piecewise-linear, HiGHS); N-0 secure "
        "in DC only. Generator voltage set-points: PGLib VG.",
        "objective": r.objective,
        "dc_max_base_loading_pct": r.max_loading_pct,
    }


# ----------------------------------------------------------------------------- screening / exact
def screen(case: MatpowerCase) -> dict:
    """Timed screening pipeline: everything from case data to per-contingency severity."""
    net = dc.build_dc_network(case)
    H = dc.ptdf(net)
    lr = dc.lodf(net, H)
    f0 = dc.solve_dc_flows(net)
    outages = np.flatnonzero(~lr.islanding)
    post = f0[:, None] + lr.lodf[:, outages] * f0[outages][None, :]
    base_ld = metrics.loading_pct(f0, net.rate_a_mw)
    sev = metrics.contingency_severity(metrics.loading_pct(post, net.rate_a_mw), base_ld, outages)
    return {
        "net": net,
        "H": H,
        "lodf": lr,
        "f0": f0,
        "outages": outages,
        "post": post,
        "base_loading": base_ld,
        "severity": sev,
    }


def exact_dc(net: dc.DCNetwork, outages: np.ndarray, base_loading: np.ndarray) -> dict:
    post = dc.dc_n1_resolve(net, outages)
    sev = metrics.contingency_severity(
        metrics.loading_pct(post, net.rate_a_mw), base_loading, outages
    )
    return {"post": post, "severity": sev}


def _runpp(pp, net) -> str:
    for i, kw in enumerate(AC_ATTEMPTS):
        try:
            pp.runpp(net, algorithm="nr", calculate_voltage_angles=True, numba=True, **kw)
            return "converged" if i == 0 else "converged_retry"
        except pp.LoadflowNotConverged:
            continue
    return "not_converged"


def exact_ac(case: MatpowerCase, dcnet: dc.DCNetwork, outages: np.ndarray) -> dict:
    """AC N-1 re-solve; outages are internal DC branch indices (mapped to mpc.branch rows)."""
    import pandapower as pp

    from .pp_bridge import branch_results, build_pp_net, set_branch_in_service

    net, bmap = build_pp_net(case)
    rows = dcnet.branch_rows
    rate = dcnet.rate_a_mw
    vmin = case.bus[:, VMIN]
    vmax = case.bus[:, VMAX]
    base_status = _runpp(pp, net)
    if base_status == "not_converged":
        raise RuntimeError(f"{case.name}: AC base case does not converge")
    _, s0 = branch_results(net, bmap)
    base_ld = metrics.loading_pct(s0[rows], rate)
    vm0 = net.res_bus.vm_pu.to_numpy()
    base_vviol = (vm0 < vmin - 1e-6) | (vm0 > vmax + 1e-6)
    sev = np.full(outages.shape[0], np.nan)
    vviol_new = np.zeros(outages.shape[0], dtype=bool)
    status = []
    for j, l in enumerate(outages):
        row = int(rows[l])
        set_branch_in_service(net, bmap, row, False)
        st = _runpp(pp, net)
        status.append(st)
        if st != "not_converged":
            _, s = branch_results(net, bmap)
            ld = metrics.loading_pct(s[rows], rate)
            sev[j] = metrics.contingency_severity(ld[:, None], base_ld, np.array([l]))[0]
            vm = net.res_bus.vm_pu.to_numpy()
            ok = np.isfinite(vm)
            vv = ok & ((vm < vmin - 1e-6) | (vm > vmax + 1e-6)) & ~base_vviol
            vviol_new[j] = bool(vv.any())
        set_branch_in_service(net, bmap, row, True)
    return {
        "severity": sev,
        "status": np.array(status),
        "base_status": base_status,
        "base_loading": base_ld,
        "base_voltage_violations": int(base_vviol.sum()),
        "voltage_violation_new": vviol_new,
    }


def contingency_rows(s: dict, d: dict, a: dict) -> list[dict]:
    """Aligned, full-precision scores for independent metric reconstruction.

    Do not round these scores: rounding nearly tied severities changes rank correlations.
    Islanding and AC non-convergence remain explicit rather than receiving zero scores.
    """
    net = s["net"]
    positions = {int(l): j for j, l in enumerate(s["outages"])}
    rows = []
    for l in range(net.n_branch):
        j = positions.get(l)
        row = {
            "branch_id": f"branch-{int(net.branch_rows[l]) + 1}",
            "islanding": bool(s["lodf"].islanding[l]),
            "screening_severity_pct": None,
            "dc_exact_severity_pct": None,
            "ac_exact_severity_pct": None,
            "ac_status": "islanding",
            "new_voltage_violation": None,
        }
        if j is not None:
            converged = a["status"][j] != "not_converged"
            row.update(
                screening_severity_pct=float(s["severity"][j]),
                dc_exact_severity_pct=float(d["severity"][j]),
                ac_exact_severity_pct=float(a["severity"][j]) if converged else None,
                ac_status=str(a["status"][j]),
                new_voltage_violation=bool(a["voltage_violation_new"][j]) if converged else None,
            )
        rows.append(row)
    return rows


def pandapower_reference(case: MatpowerCase, net: dc.DCNetwork) -> tuple[np.ndarray, np.ndarray]:
    """pandapower makePTDF/makeLODF on the same in-service network, renumbered 0..n-1."""
    from pandapower.pypower.idx_brch import branch_cols
    from pandapower.pypower.idx_bus import bus_cols
    from pandapower.pypower.makeLODF import makeLODF
    from pandapower.pypower.makePTDF import makePTDF

    n, m = net.n_bus, net.n_branch
    bus = np.zeros((n, bus_cols))
    bus[:, BUS_I] = np.arange(n)
    bus[:, 1] = 1
    bus[net.slack, 1] = 3
    br = np.zeros((m, branch_cols))
    br[:, :13] = case.branch[net.branch_rows, :13]
    br[:, 0] = net.f
    br[:, 1] = net.t
    br[:, BR_STATUS] = 1
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        H = makePTDF(net.base_mva, bus, br, slack=net.slack, using_sparse_solver=True)
        L = makeLODF(br, H)
    return np.asarray(H), np.asarray(L)


# ----------------------------------------------------------------------------- one case
def _median_time(fn, repeats: int) -> tuple[float, object]:
    ts, out = [], None
    for _ in range(repeats):
        gc.collect()
        t0 = time.perf_counter()
        out = fn()
        ts.append(time.perf_counter() - t0)
    return statistics.median(ts), out


def _peak_mib(fn) -> float:
    gc.collect()
    tracemalloc.start()
    try:
        fn()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return peak / 2**20


def load_case(name: str, cases_dir: Path = CASES_DIR) -> MatpowerCase:
    case = parse_matpower(cases_dir / f"pglib_opf_{name}.m")
    case.name = name
    return case


def run_case(name: str, repeats: int = 3, memory: bool = True, log=print) -> dict:
    import psutil

    case = load_case(name)
    src = {
        "file": f"benchmarks/stormbench/cases/pglib_opf_{name}.m",
        "sha256": case.source_sha256,
        "pglib_commit": PGLIB_COMMIT,
    }
    op = operating_point(case)

    t_scr, s = _median_time(lambda: screen(case), repeats)
    net, outages = s["net"], s["outages"]
    lr = s["lodf"]
    log(f"  {name}: screening {t_scr:.4f}s, {outages.size} non-islanding outages")
    t_dc, d = _median_time(lambda: exact_dc(net, outages, s["base_loading"]), repeats)
    log(f"  {name}: exact DC {t_dc:.3f}s")
    t_ac, a = _median_time(lambda: exact_ac(case, net, outages), repeats)
    log(f"  {name}: exact AC {t_ac:.2f}s")

    # validation
    Hpp, Lpp = pandapower_reference(case, net)
    ok = ~lr.islanding
    lodf_diff = np.abs(lr.lodf[:, ok] - Lpp[:, ok])
    err = np.abs(s["post"] - d["post"])
    err[outages, np.arange(outages.size)] = (
        0.0  # outaged branch: estimate f+(-1)f = 0 by construction
    )
    validation = {
        "ptdf_max_abs_diff_vs_pandapower": float(np.max(np.abs(s["H"] - Hpp))),
        "lodf_max_abs_diff_vs_pandapower": float(lodf_diff.max()) if lodf_diff.size else None,
        "lodf_vs_dc_resolve_max_abs_mw": float(err.max()) if err.size else None,
        "islanding_structural_vs_numeric_mismatch": int(
            np.sum(lr.islanding != lr.numeric_islanding)
        ),
    }

    acst = a["status"]
    conv = acst != "not_converged"
    sev_s, sev_d, sev_a = s["severity"], d["severity"], a["severity"]
    over = THRESHOLD + metrics.TOL_PCT
    flag_s = sev_s > over
    vnew = a["voltage_violation_new"] & conv
    mon = net.rate_a_mw > 0
    islanding_idx = np.flatnonzero(lr.islanding)
    island_info = [dc.island_effect(net, int(l)) for l in islanding_idx]

    payload = {
        "schema_version": "stormbench-result/1.0",
        "provenance": "calculated",
        "case": name,
        "source": src,
        "operating_point": op,
        "counts": {
            "buses": int(net.n_bus),
            "branches": int(net.n_branch),
            "monitored_branches": int(mon.sum()),
            "rate_a_zero": int((~mon).sum()),
            "contingencies": int(net.n_branch),
            "islanding": int(lr.islanding.sum()),
            "screened": int(outages.size),
            "dc_base_overloaded_branches": int(np.sum(s["base_loading"] > over)),
            "ac_base_overloaded_branches": int(np.sum(a["base_loading"] > over)),
            "ac_base_voltage_violations": a["base_voltage_violations"],
        },
        "islanding_outages": {
            "branch_ids": [f"branch-{int(net.branch_rows[l]) + 1}" for l in islanding_idx],
            "max_islanded_buses": max((i["islanded_bus_count"] for i in island_info), default=0),
            "max_abs_islanded_injection_mw": max(
                (abs(i["islanded_net_injection_mw"]) for i in island_info), default=0.0
            ),
        },
        "validation": validation,
        "flow_error_mw": {
            "max": float(err.max()) if err.size else 0.0,
            "mean": float(err.mean()) if err.size else 0.0,
        },
        "overloading_contingencies": {
            "screening": int(flag_s.sum()),
            "dc_exact": int(np.sum(sev_d > over)),
            "ac_exact": int(np.sum(sev_a[conv] > over)),
        },
        "screening_vs_dc": metrics.compare(sev_s, sev_d, THRESHOLD),
        "screening_vs_ac": metrics.compare(sev_s[conv], sev_a[conv], THRESHOLD),
        "ac": {
            "base_converged": a["base_status"],
            "converged": int(np.sum(acst == "converged")),
            "converged_retry": int(np.sum(acst == "converged_retry")),
            "not_converged": int(np.sum(acst == "not_converged")),
            "not_converged_branch_ids": [
                f"branch-{int(net.branch_rows[l]) + 1}" for l in outages[~conv]
            ],
            "new_voltage_violation_contingencies": int(vnew.sum()),
            "new_voltage_violation_not_flagged_by_screening": int(np.sum(vnew & ~flag_s)),
        },
        "runtime": {
            "repeats": repeats,
            "screening_median_s": t_scr,
            "dc_exact_median_s": t_dc,
            "ac_exact_median_s": t_ac,
        },
        "memory": {},
        "top_contingencies": [],
        "platform": environment(),
    }
    # AC non-convergence (NaN) sorts last; severities within TOL_PCT are ties broken by index.
    order = metrics.top_k_order(np.nan_to_num(sev_a, nan=-1.0))[:10]
    payload["top_contingencies"] = [
        {
            "branch_id": f"branch-{int(net.branch_rows[outages[j]]) + 1}",
            "ac_severity_pct": float(sev_a[j]) if np.isfinite(sev_a[j]) else None,
            "dc_exact_severity_pct": float(sev_d[j]),
            "screening_severity_pct": float(sev_s[j]),
        }
        for j in order
    ]
    if memory:
        payload["memory"] = {
            "screening_peak_tracemalloc_mib": _peak_mib(lambda: screen(case)),
            "dc_exact_peak_tracemalloc_mib": _peak_mib(
                lambda: exact_dc(net, outages, s["base_loading"])
            ),
            "ac_exact_peak_tracemalloc_mib": _peak_mib(lambda: exact_ac(case, net, outages)),
            "process_rss_end_mib": psutil.Process().memory_info().rss / 2**20,
        }
    payload = _sig(payload)
    payload["contingencies"] = contingency_rows(s, d, a)
    return payload


# ----------------------------------------------------------------------------- artifacts
def _canon(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def make_artifact(
    payload: dict, artifact_id: str, network_id: str, command: str, inputs: list[dict]
) -> dict:
    import pandapower

    return {
        "artifact": {
            "schema_version": "gridstorm-artifact/1.0",
            "artifact_id": artifact_id,
            "kind": "benchmark",
            "engine": "stormbench",
            "engine_version": f"stormbench {metadata.version('stormbench')} / pandapower "
            f"{pandapower.__version__}",
            "network_id": network_id,
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "command": command,
            "inputs": inputs,
            "platform": f"{platform.system()} {platform.release()} {platform.machine()}, "
            f"Python {platform.python_version()}",
            "execution_mode": "precomputed",
            "payload_sha256": hashlib.sha256(_canon(payload)).hexdigest(),
        },
        "payload": payload,
    }


def write_outputs(
    results: list[dict], artifacts_dir: Path, results_dir: Path | None, command: str, summary: bool
) -> list[Path]:
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    written = []
    index = []
    for p in results:
        aid = f"stormbench-{p['case'].replace('_', '-')}"
        nid = f"pglib-{p['case'].replace('_', '-')}"
        inputs = [{"path": p["source"]["file"], "sha256": p["source"]["sha256"]}]
        art = make_artifact(p, aid, nid, command, inputs)
        path = artifacts_dir / f"{aid}.json"
        path.write_text(json.dumps(art, indent=1) + "\n", encoding="utf-8")
        written.append(path)
        index.append(
            {
                "artifact_id": aid,
                "kind": "benchmark",
                "network_id": nid,
                "title": f"StormBench DC screening vs exact N-1: {p['case']}",
            }
        )
        if results_dir is not None:
            results_dir.mkdir(parents=True, exist_ok=True)
            rp = results_dir / f"{p['case']}.json"
            rp.write_text(json.dumps(p, indent=1) + "\n", encoding="utf-8")
            written.append(rp)
    if summary:
        sp_ = {
            "schema_version": "stormbench-summary/1.0",
            "provenance": "calculated",
            "threshold_pct": THRESHOLD,
            "cases": results,
            "platform": results[0]["platform"] if results else None,
        }
        art = make_artifact(
            sp_,
            "stormbench-summary",
            "multiple",
            command,
            [{"path": r["source"]["file"], "sha256": r["source"]["sha256"]} for r in results],
        )
        path = artifacts_dir / "stormbench-summary.json"
        path.write_text(json.dumps(art, indent=1) + "\n", encoding="utf-8")
        written.append(path)
        index.insert(
            0,
            {
                "artifact_id": "stormbench-summary",
                "kind": "benchmark",
                "network_id": "multiple",
                "title": "StormBench summary: DC PTDF/LODF screening vs exact DC/AC N-1",
            },
        )
        if results_dir is not None:
            (results_dir / "summary.json").write_text(
                json.dumps(sp_, indent=1) + "\n", encoding="utf-8"
            )
        (artifacts_dir / "index.json").write_text(
            json.dumps(
                {
                    "schema_version": "gridstorm-artifact-index/1.0",
                    "engine": "stormbench",
                    "artifacts": index,
                },
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        written.append(artifacts_dir / "index.json")
    return written


def quiet() -> None:
    warnings.filterwarnings("ignore")
    logging.getLogger("pandapower").setLevel(logging.ERROR)


def main(argv: list[str] | None = None, command: str | None = None) -> int:
    """CLI entry; ``command`` (recorded in artifact headers) defaults to the invocation."""
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "data" / "artifacts" / "stormbench",
        help="artifact directory (contract §5)",
    )
    ap.add_argument(
        "--results-dir",
        type=Path,
        default=None,
        help="also write raw payloads here (benchmarks/stormbench/results)",
    )
    ap.add_argument("--cases", default=",".join(DEFAULT_CASES))
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--no-memory", action="store_true", help="skip the tracemalloc pass")
    args = ap.parse_args(argv)
    quiet()
    cases = [c for c in args.cases.split(",") if c]
    if command is None:
        command = "uv run python " + " ".join([Path(sys.argv[0]).name, *(argv or sys.argv[1:])])
    results = []
    for name in cases:
        print(f"[stormbench] {name}", flush=True)
        results.append(run_case(name, repeats=args.repeats, memory=not args.no_memory))
    summary = set(cases) == set(DEFAULT_CASES)
    for p in write_outputs(results, args.out_dir, args.results_dir, command, summary):
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
