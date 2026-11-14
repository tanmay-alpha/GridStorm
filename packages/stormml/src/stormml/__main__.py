"""CLI: ``uv run python -m stormml {generate,assemble,evaluate}``.

1. ``generate --network case118 --n-train 60 --n-test 30``: AC N-1 labelling of seeded operating
   points; writes ``.cache/<network>.npz`` + ``.cache/<network>.json`` inside the package.
2. ``assemble``: merges the per-network caches into ``data/artifacts/stormml/dataset.npz`` and the
   ``ml-screening-dataset`` artifact (generation records, label statistics, input hashes).
3. ``evaluate``: trains / scores every model on every split and writes the
   ``ml-screening-results`` artifact plus ``index.json``.

All labels are simulator-generated (pandapower AC power flow), not historical outages.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

PKG_DIR = Path(__file__).resolve().parents[2]
REPO = PKG_DIR.parents[1]
CACHE = PKG_DIR / ".cache"
ART_DIR = REPO / "data" / "artifacts" / "stormml"
DATASET = ART_DIR / "dataset.npz"
SCHEMA = "gridstorm-artifact/1.0"


def _default_matpower_dir() -> Path | None:
    p = REPO.parent / "upstream" / "matpower" / "data"
    return p if p.is_dir() else None


def _pglib_dirs(extra: list[str]) -> list[Path]:
    dirs = [Path(d) for d in extra]
    dirs += sorted((REPO / "data" / "networks").glob("*/source"))
    up = REPO.parent / "upstream" / "pglib-opf"
    if up.is_dir():
        dirs.append(up)
    return dirs


def _canonical_sha(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _round(x, sig: int = 4):
    if isinstance(x, float):
        if not np.isfinite(x):
            return None
        return float(f"{x:.{sig}g}")
    if isinstance(x, dict):
        return {k: _round(v, sig) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_round(v, sig) for v in x]
    if isinstance(x, (np.floating,)):
        return _round(float(x), sig)
    if isinstance(x, (np.integer,)):
        return int(x)
    return x


def _versions() -> dict:
    import pandapower
    import scipy
    import sklearn

    return {
        "pandapower": pandapower.__version__,
        "scikit-learn": sklearn.__version__,
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "python": platform.python_version(),
    }


def _write_artifact(artifact_id: str, network_id: str, command: str, inputs: list, payload) -> dict:
    payload = _round(payload)
    v = _versions()
    doc = {
        "artifact": {
            "schema_version": SCHEMA,
            "artifact_id": artifact_id,
            "kind": "benchmark",
            "engine": "stormml",
            "engine_version": f"stormml 0.1.0; pandapower {v['pandapower']}; "
                              f"scikit-learn {v['scikit-learn']}",
            "network_id": network_id,
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "command": command,
            "inputs": inputs,
            "platform": f"{platform.system()} {platform.release()} {platform.machine()}; "
                        f"python {v['python']}",
            "execution_mode": "precomputed",
            "payload_sha256": _canonical_sha(payload),
        },
        "payload": payload,
    }
    ART_DIR.mkdir(parents=True, exist_ok=True)
    path = ART_DIR / f"{artifact_id}.json"
    path.write_text(json.dumps(doc, indent=1, sort_keys=False, allow_nan=False) + "\n")
    return doc


def _update_index(entry: dict) -> None:
    path = ART_DIR / "index.json"
    idx = (
        json.loads(path.read_text())
        if path.is_file()
        else {"schema_version": "gridstorm-artifact-index/1.0", "engine": "stormml", "artifacts": []}
    )
    idx["artifacts"] = [a for a in idx["artifacts"] if a["artifact_id"] != entry["artifact_id"]]
    idx["artifacts"].append(entry)
    idx["artifacts"].sort(key=lambda a: a["artifact_id"])
    path.write_text(json.dumps(idx, indent=2) + "\n")


def _sha_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cmd_generate(a) -> None:
    from .datagen import generate_network, prepare_network
    from .splits import TEST_SEED_BASE, TRAIN_SEED_BASE

    mp = Path(a.matpower_dir) if a.matpower_dir else _default_matpower_dir()
    prep = prepare_network(a.network, _pglib_dirs(a.pglib_dir), mp)
    seeds = [TRAIN_SEED_BASE + i for i in range(a.n_train)] + [
        TEST_SEED_BASE + i for i in range(a.n_test)
    ]
    t0 = time.perf_counter()
    ds, records = generate_network(prep, seeds, log=lambda s: print(s, flush=True))
    CACHE.mkdir(exist_ok=True)
    ds.save(CACHE / f"{a.network}.npz")
    meta = {
        "network": a.network,
        "network_id": prep.network_id,
        "reference_source": prep.reference_source,
        "inputs": prep.inputs,
        "n_bus": int(prep.case.bus.shape[0]),
        "n_branch": int(prep.case.branch.shape[0]),
        "bridges": int(prep.topo.is_bridge.sum()),
        "n_train_seeds": a.n_train,
        "n_test_seeds": a.n_test,
        "wall_seconds": time.perf_counter() - t0,
        "records": records,
        "command": " ".join(["python -m stormml", *sys.argv[1:]]),
    }
    (CACHE / f"{a.network}.json").write_text(json.dumps(meta, indent=1))
    print(f"wrote {CACHE / (a.network + '.npz')} rows={ds.X.shape[0]}")


def cmd_assemble(a) -> None:
    from .datagen import AGGRAVATION_PP, AGGRAVATION_PU, GEN_NOISE_SD, LABEL_NAMES, LOAD_NOISE_CLIP
    from .datagen import LOAD_NOISE_SD, LOAD_RANGE, Dataset

    metas, parts = [], []
    for net in a.networks:
        metas.append(json.loads((CACHE / f"{net}.json").read_text()))
        parts.append(Dataset.load(CACHE / f"{net}.npz"))
    ds = Dataset.concat(parts)
    ART_DIR.mkdir(parents=True, exist_ok=True)
    ds.save(DATASET)
    per_net = {}
    for meta in metas:
        net = meta["network"]
        sel = ds.network == net
        recs = meta["records"]
        okr = [r for r in recs if r["base_converged"]]
        per_net[net] = {
            "network_id": meta["network_id"],
            "reference_source": meta["reference_source"],
            "n_bus": meta["n_bus"],
            "n_branch": meta["n_branch"],
            "bridges": meta["bridges"],
            "operating_points_requested": len(recs),
            "operating_points_rejected_base_nonconvergence": len(recs) - len(okr),
            "operating_points_accepted": len(okr),
            "rows": int(sel.sum()),
            "label_rates": {n: float(ds.y[sel, i].mean()) if sel.any() else None
                            for i, n in enumerate(LABEL_NAMES)},
            "ac_n1_seconds_per_operating_point_mean": float(np.mean([r["ac_n1_seconds"] for r in okr]))
            if okr else None,
            "feature_seconds_per_operating_point_mean": float(
                np.mean([r["feature_seconds"] for r in okr])
            ) if okr else None,
            "generation_wall_seconds": meta["wall_seconds"],
            "command": meta["command"],
            "records": recs,
        }
    inputs = []
    for meta in metas:
        inputs += meta["inputs"]
    payload = {
        "description": "Simulator-generated dataset for ML contingency screening: one row per "
        "(network, operating point, outaged branch). Labels come from pandapower AC N-1 power "
        "flows, NOT from historical outages.",
        "provenance": "modeled",
        "dataset_file": {"path": "data/artifacts/stormml/dataset.npz", "sha256": _sha_file(DATASET),
                         "bytes": DATASET.stat().st_size},
        "rows": int(ds.X.shape[0]),
        "features": list(ds.feature_names),
        "labels": list(LABEL_NAMES),
        "sampling": {
            "load_factor_uniform": list(LOAD_RANGE),
            "per_bus_load_noise_sd": LOAD_NOISE_SD,
            "per_bus_load_noise_clip": list(LOAD_NOISE_CLIP),
            "generator_lognormal_sd": GEN_NOISE_SD,
            "rng": "numpy default_rng([seed, crc32(network)])",
        },
        "label_definition": {
            "primary": "Absolute post-outage thermal >100 % OR energised-bus voltage outside "
                       "case limits OR AC numerical non-convergence; tolerance 1e-6 in % and pu.",
            "secondary_aggravated": "Non-convergence OR new violation OR worsening of an existing "
                                    "thermal violation by 5 percentage points or voltage excess "
                                    "by 0.01 pu; this is NOT the primary absolute label.",
            "aggravation_pp": AGGRAVATION_PP,
            "aggravation_pu": AGGRAVATION_PU,
            "islanding": "Separate diagnostic; converged islands with unsupplied load are not "
                         "counted as numerical non-convergence. Disconnected MW retained per row.",
            "power_flow": "NR max_iteration=30, numba=True, enforce_q_lims=False; warm-start from "
                          "base AC then DC and flat retries. Only LoadflowNotConverged is caught.",
        },
        "networks": per_net,
        "versions": _versions(),
    }
    _write_artifact("ml-screening-dataset", "multi:pglib-case30/57/118/300-ieee",
                    "uv run python -m stormml assemble", inputs, payload)
    _update_index({"artifact_id": "ml-screening-dataset", "kind": "benchmark",
                   "network_id": "multi:pglib-case30/57/118/300-ieee",
                   "title": "ML contingency screening — simulator-labelled AC N-1 dataset",
                   "files": ["dataset.npz"]})
    print(f"assembled rows={ds.X.shape[0]} -> {DATASET}")


def cmd_evaluate(a) -> None:
    from .datagen import Dataset
    from .evaluate import evaluate_split, make_models
    from .splits import leave_network_out_split, operating_point_split

    ds = Dataset.load(DATASET)
    gen = json.loads((ART_DIR / "ml-screening-dataset.json").read_text())["payload"]
    ac = {n: v["ac_n1_seconds_per_operating_point_mean"] for n, v in gen["networks"].items()}
    ft = {n: v["feature_seconds_per_operating_point_mean"] for n, v in gen["networks"].items()}
    jobs = [(operating_point_split(ds.seed, ds.op_id), t) for t in ("label", "thermal", "aggravated")]
    for held in sorted(set(ds.network.tolist())):
        jobs += [(leave_network_out_split(ds.network, ds.op_id, held), t)
                 for t in ("label", "aggravated")]
    results = []
    for i, (split, target) in enumerate(jobs):
        t0 = time.perf_counter()
        r = evaluate_split(ds, split, target, ac, ft, n_boot=a.n_boot, boot_seed=a.boot_seed + i)
        print(f"{split.name} target={target}: {time.perf_counter() - t0:.0f}s", flush=True)
        if r["status"] != "ok":
            print(f"  unavailable: {r['reason']}", flush=True)
            results.append(r)
            continue
        for name, m in r["models"].items():
            print(f"  {name:14s} PR-AUC {m['pr_auc']:.3f} ROC {m['roc_auc']:.3f} "
                  f"R@P.9 {m['recall_at_precision_0.9']:.3f} R@10 {m['recall_at_10']:.3f} "
                  f"F1 {m['at_threshold']['f1']:.3f}", flush=True)
        results.append(r)
    for net, meta in gen["networks"].items():
        if not meta["operating_points_accepted"]:
            results.append({
                "split": f"leave_network_out:{net}", "target": "label", "status": "unavailable",
                "reason": "All requested base AC operating points failed; no valid N-1 test set.",
                "attempted_operating_points": meta["operating_points_requested"],
            })
    payload = {
        "provenance": "modeled",
        "question": "Does ML trained on simulator-generated AC N-1 labels beat transparent DC-LODF "
        "and pre-loading screening, across operating points and across networks?",
        "label_note": "All labels are simulator-generated (pandapower AC power flow on PGLib-OPF "
        "cases); they are not historical outages.",
        "dataset": {"artifact_id": "ml-screening-dataset", "sha256": _sha_file(DATASET)},
        "models": {m.name: m.description for m in make_models()},
        "results": results,
        "versions": _versions(),
        "threads": {k: os.environ.get(k) for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS")},
    }
    _write_artifact("ml-screening-results", "multi:pglib-case30/57/118/300-ieee",
                    f"uv run python -m stormml evaluate --n-boot {a.n_boot} --boot-seed {a.boot_seed}",
                    [{"path": "data/artifacts/stormml/dataset.npz", "sha256": _sha_file(DATASET)}],
                    payload)
    _update_index({"artifact_id": "ml-screening-results", "kind": "benchmark",
                   "network_id": "multi:pglib-case30/57/118/300-ieee",
                   "title": "ML contingency screening vs DC-LODF / pre-loading baselines"})


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="stormml")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--network", required=True, choices=["case30", "case57", "case118", "case300"])
    g.add_argument("--n-train", type=int, required=True)
    g.add_argument("--n-test", type=int, required=True)
    g.add_argument("--pglib-dir", action="append", default=[])
    g.add_argument("--matpower-dir")
    s = sub.add_parser("assemble")
    s.add_argument("--networks", nargs="+", default=["case30", "case57", "case118", "case300"])
    e = sub.add_parser("evaluate")
    e.add_argument("--n-boot", type=int, default=1000)
    e.add_argument("--boot-seed", type=int, default=20261114)
    a = p.parse_args(argv)
    {"generate": cmd_generate, "assemble": cmd_assemble, "evaluate": cmd_evaluate}[a.cmd](a)


if __name__ == "__main__":
    main()
