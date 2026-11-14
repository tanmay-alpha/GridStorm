"""Run a StormRisk Monte Carlo study with the real PyPSA engine and write a contract-§5 artifact.

Usage (from packages/stormrisk):

    uv run python scripts/run_study.py studies/ac-dc-meshed-storm-stress.json --workers 1

A study file is JSON: ``{"artifact_id", "title", "base_scenario": <stormspec/1.0>,
"sampling": <stormrisk-sampling/1.0>}``. Optional ``--n-samples``/``--seed`` override the file.
The artifact is written to ``data/artifacts/stormrisk/<artifact_id>.json`` and ``index.json``.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from stormspec import Scenario, file_sha256

from stormrisk import SamplingSpec, run_study
from stormrisk.artifact import build_artifact, write_artifact
from stormrisk.engines import PypsaEngine

REPO = Path(__file__).resolve().parents[3]


def _rel(p: Path) -> str:
    try:
        return p.resolve().relative_to(REPO).as_posix()
    except ValueError:
        return p.as_posix()


def _network_dict(network_dir: Path, network_id: str) -> dict:
    """canonical-grid/1.0 if present, else the adapter's index of the loaded network.nc."""
    canon = network_dir / "canonical.json"
    if canon.exists():
        return json.loads(canon.read_text(encoding="utf-8"))
    from gridstorm_pypsa import load_network, network_index

    return network_index(load_network(network_dir), network_id)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("study", type=Path)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--n-samples", type=int, default=None)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--networks-root", type=Path, default=REPO / "data" / "networks")
    ap.add_argument("--out-dir", type=Path, default=REPO / "data" / "artifacts" / "stormrisk")
    args = ap.parse_args(argv)

    study = json.loads(args.study.read_text(encoding="utf-8"))
    base = Scenario.model_validate(study["base_scenario"])
    sampling = dict(study["sampling"])
    if args.n_samples is not None:
        sampling["n_samples"] = args.n_samples
    if args.seed is not None:
        sampling["seed"] = args.seed
    spec = SamplingSpec.model_validate(sampling)

    network_id = base.dataset.network_id
    network_dir = args.networks_root / network_id
    network = _network_dict(network_dir, network_id)

    t0 = time.perf_counter()

    def progress(done: int, total: int) -> None:
        if done == total or done % max(1, total // 20) == 0:
            print(f"solved {done}/{total} distinct states  ({time.perf_counter() - t0:.1f} s)",
                  flush=True)

    payload = run_study(base, spec, network, PypsaEngine(network_dir), workers=args.workers,
                        progress=progress)
    versions = PypsaEngine.versions()
    payload["engine"]["package_versions"] = versions
    payload["study_title"] = study["title"]

    cmd = [
        "uv run --project packages/stormrisk python packages/stormrisk/scripts/run_study.py",
        _rel(args.study), f"--workers {args.workers}",
        f'--networks-root "{_rel(args.networks_root)}"',
        f'--out-dir "{_rel(args.out_dir)}"',
    ]
    if args.n_samples is not None:
        cmd.append(f"--n-samples {args.n_samples}")
    if args.seed is not None:
        cmd.append(f"--seed {args.seed}")
    inputs = [{"path": _rel(args.study), "sha256": file_sha256(args.study)}]
    for name in ("network.nc", "canonical.json"):
        p = network_dir / name
        if p.exists():
            inputs.append({"path": _rel(p), "sha256": file_sha256(p)})

    art = build_artifact(payload, artifact_id=study["artifact_id"], network_id=network_id,
                         engine_version=versions.get("pypsa"), command=" ".join(cmd),
                         inputs=inputs)
    path = write_artifact(art, args.out_dir, title=study["title"])

    e = payload["estimates"]
    acc = payload["sample_accounting"]
    rt = payload["runtime"]
    print(json.dumps({
        "artifact": _rel(path), "bytes": path.stat().st_size,
        "n_samples": acc["n_samples"], "distinct_states": acc["n_distinct_states"],
        "feasible": acc["n_feasible_samples"], "infeasible": acc["n_infeasible_samples"],
        "error": acc["n_error_samples"], "invalid": acc["n_invalid_samples"],
        "eens_mwh": e.get("eens_mwh"), "ci95": [e.get("ci95_low_mwh"), e.get("ci95_high_mwh")],
        "se_eens_mwh": e.get("se_eens_mwh"), "cv": e.get("cv_eens"), "lolp": e.get("lolp"),
        "p95_unserved_mwh": e.get("p95_unserved_mwh"),
        "wall_time_s": rt["wall_time_s"], "solves": rt["solves"],
        "peak_rss_mb_main": rt["peak_rss_mb_main_process"],
        "peak_rss_mb_worker": rt["peak_rss_mb_max_worker"], "warnings": payload["warnings"],
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
