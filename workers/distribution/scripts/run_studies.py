"""Reproduce every distribution artifact in data/artifacts/distribution/.

    cd workers/distribution
    uv run python scripts/run_studies.py            # all studies
    uv run python scripts/run_studies.py --only lv-rural1-2-high-pv

Single-threaded (OMP/OPENBLAS/MKL_NUM_THREADS=1); studies run one after another.
"""

from __future__ import annotations

import argparse
import os

for _var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_var, "1")

import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

import simbench  # noqa: E402
from stormspec import file_sha256  # noqa: E402

from gridstorm_distribution.artifact import build_artifact, write_artifact  # noqa: E402
from gridstorm_distribution.study import StudyConfig, run_study, versions  # noqa: E402

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = REPO / "data" / "artifacts" / "distribution"
WINDOW_START = "2016-07-25 00:00"  # Mon 25 Jul - Sun 31 Jul 2016 (week of min residual load)
WINDOW_STEPS = 7 * 96
TODAY = "1-LV-rural1--0-sw"  # SimBench scenario 0 (today)
FUTURE = "1-LV-rural1--2-sw"  # same feeder, SimBench scenario 2 (more PV, heat pumps, EVs, storage)
HEAT = 1.3  # heat-wave / high-load stress factor on load P and Q
HIGH_PV = 1.5  # additional PV build-out on top of SimBench scenario 2

# (artifact_id, title, config)
STUDIES: list[tuple[str, str, StudyConfig]] = [
    ("lv-rural1-0-baseline", "LV rural1 (today) - baseline week",
     StudyConfig(TODAY, WINDOW_START, WINDOW_STEPS)),
    ("lv-rural1-0-heatwave", f"LV rural1 (today) - heat-wave load x{HEAT}",
     StudyConfig(TODAY, WINDOW_START, WINDOW_STEPS, load_factor=HEAT)),
    ("lv-rural1-0-pv-loss-high-load", f"LV rural1 (today) - PV loss + load x{HEAT}",
     StudyConfig(TODAY, WINDOW_START, WINDOW_STEPS, load_factor=HEAT, pv_factor=0.0)),
    ("lv-rural1-2-baseline", "LV rural1 (SimBench scenario 2) - baseline week",
     StudyConfig(FUTURE, WINDOW_START, WINDOW_STEPS)),
    ("lv-rural1-2-pv-loss-high-load", f"LV rural1 (scenario 2) - PV loss + load x{HEAT}",
     StudyConfig(FUTURE, WINDOW_START, WINDOW_STEPS, load_factor=HEAT, pv_factor=0.0)),
    ("lv-rural1-2-high-pv", f"LV rural1 (scenario 2) - high PV x{HIGH_PV}",
     StudyConfig(FUTURE, WINDOW_START, WINDOW_STEPS, pv_factor=HIGH_PV)),
    ("lv-rural1-2-high-pv-cap70", f"LV rural1 (scenario 2) - high PV x{HIGH_PV} + 70 % feed-in cap",
     StudyConfig(FUTURE, WINDOW_START, WINDOW_STEPS, pv_factor=HIGH_PV, pv_feed_in_cap_pu=0.7)),
    ("lv-rural1-2-high-pv-qu", f"LV rural1 (scenario 2) - high PV x{HIGH_PV} + Q(U) control",
     StudyConfig(FUTURE, WINDOW_START, WINDOW_STEPS, pv_factor=HIGH_PV, q_u_control=True)),
]

# SimBench CSV tables the grids and profiles are read from (inside the pinned simbench wheel).
_TABLES = ("Node.csv", "Line.csv", "LineType.csv", "Transformer.csv", "TransformerType.csv",
           "ExternalNet.csv", "Switch.csv", "Load.csv", "LoadProfile.csv", "RES.csv",
           "RESProfile.csv", "Storage.csv", "StorageProfile.csv", "StudyCases.csv")


def _inputs(grid_code: str) -> list[dict[str, str]]:
    scenario = grid_code.split("--")[1][0]
    folder = (Path(simbench.__file__).parent / "networks"
              / f"1-complete_data-mixed-all-{scenario}-sw")
    out = []
    for name in _TABLES:
        p = folder / name
        if p.is_file():
            out.append({"path": f"simbench=={simbench.__version__}:networks/{folder.name}/{name}",
                        "sha256": file_sha256(p)})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", action="append", help="artifact_id(s) to run (default: all)")
    ap.add_argument("--out-dir", type=Path, default=OUT_DIR)
    args = ap.parse_args(argv)
    v = versions()
    engine_version = f"pandapower {v['pandapower']} / simbench {v['simbench']}"
    input_cache: dict[str, list[dict[str, str]]] = {}
    selected = [s for s in STUDIES if not args.only or s[0] in args.only]
    if args.only and len(selected) != len(set(args.only)):
        ap.error(f"unknown artifact id in {args.only}")
    for artifact_id, title, cfg in selected:
        t0 = time.perf_counter()
        payload = run_study(cfg)
        payload["title"] = title
        if cfg.grid_code not in input_cache:
            input_cache[cfg.grid_code] = _inputs(cfg.grid_code)
        art = build_artifact(
            payload, artifact_id=artifact_id, network_id=f"simbench-{cfg.grid_code}",
            engine_version=engine_version,
            command=f"uv run python scripts/run_studies.py --only {artifact_id}",
            inputs=input_cache[cfg.grid_code],
        )
        path = write_artifact(art, args.out_dir, title=title)
        s, c = payload["summary"], payload["convergence"]
        print(f"{artifact_id}: {c['converged_steps']}/{c['steps']} converged, "
              f"vm [{s['vm_min_pu']:.4f}, {s['vm_max_pu']:.4f}] pu, "
              f"line max {s['max_line_loading_pct']:.1f} %, trafo max "
              f"{s['max_trafo_loading_pct']:.1f} %, violation {s['any_violation']:.2f} h, "
              f"{payload['runtime_s']:.1f} s -> {path.name} ({path.stat().st_size} B, "
              f"{time.perf_counter() - t0:.1f} s total)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
