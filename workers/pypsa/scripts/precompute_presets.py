"""Precompute every StormSpec preset with PyPSA into gridstorm-artifact/1.0 files (contract §5).

    cd workers/pypsa
    uv run python scripts/precompute_presets.py --out-dir ../../data/artifacts/pypsa \
        --benchmark-md ../../docs/benchmarks/pypsa-presets.md

Each preset runs in its own child process (so peak RSS is measured per preset, not accumulated)
against ``<network-root>/<network_id>/network.nc``. The child reports wall time and its own peak
resident set size (Windows: peak working set; Linux/macOS: ``getrusage`` ru_maxrss). The artifact
payload is the unmodified gridstorm-result/1.0 document; measurements go into the header.
``index.json`` is rebuilt from every artifact present in the output directory.

Exit code: 0 if every selected preset produced an artifact, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
INDEX_SCHEMA = "gridstorm-artifact-index/1.0"
ARTIFACT_SCHEMA = "gridstorm-artifact/1.0"
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
COMMAND = (
    "cd workers/pypsa && uv run python scripts/precompute_presets.py "
    "--out-dir ../../data/artifacts/pypsa --benchmark-md ../../docs/benchmarks/pypsa-presets.md"
)


def _peak_rss_mb() -> tuple[float, str]:
    if sys.platform == "win32":
        import psutil

        return psutil.Process().memory_info().peak_wset / 2**20, "psutil peak_wset (Windows)"
    import resource

    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    scale = 1 if sys.platform == "darwin" else 1024  # bytes on macOS, KiB on Linux
    return maxrss * scale / 2**20, "getrusage ru_maxrss"


def _child(scenario_path: str, network_dir: str, out_path: str) -> int:
    """Run one preset in this (fresh) process and print a measurement JSON line."""
    import logging

    logging.disable(logging.WARNING)
    from stormspec import load_scenario

    from gridstorm_pypsa import run_scenario

    t0 = time.perf_counter()
    result = run_scenario(load_scenario(scenario_path), network_dir)
    wall = time.perf_counter() - t0
    Path(out_path).write_text(
        json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    peak, method = _peak_rss_mb()
    print(
        json.dumps(
            {"wall_time_s": round(wall, 3), "peak_rss_mb": round(peak, 1), "rss_method": method}
        )
    )
    return 0


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _run_one(preset_path: Path, network_root: Path, out_dir: Path) -> dict:
    import pypsa
    import stormspec

    scenario = stormspec.load_scenario(preset_path)
    network_dir = network_root / scenario.dataset.network_id
    nc = network_dir / "network.nc"
    if not nc.is_file():
        raise FileNotFoundError(f"{nc} not found (network {scenario.dataset.network_id!r})")

    env = {
        **os.environ,
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    with tempfile.TemporaryDirectory() as tmp:
        result_path = Path(tmp) / "result.json"
        t0 = time.perf_counter()
        proc = subprocess.run(
            [
                sys.executable,
                __file__,
                "--_child",
                str(preset_path),
                str(network_dir),
                str(result_path),
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        process_wall = time.perf_counter() - t0
        if proc.returncode != 0:
            raise RuntimeError(f"child failed ({proc.returncode}): {proc.stderr.strip()[-2000:]}")
        measure = json.loads(proc.stdout.strip().splitlines()[-1])
        result = json.loads(result_path.read_text(encoding="utf-8"))

    header = {
        "schema_version": ARTIFACT_SCHEMA,
        "artifact_id": scenario.id,
        "kind": "simulation",
        "engine": "pypsa",
        "engine_version": pypsa.__version__,
        "network_id": scenario.dataset.network_id,
        "created_at": stormspec.manifest.utc_now_iso(),
        "command": COMMAND,
        "inputs": [
            {"path": _rel(nc), "sha256": stormspec.file_sha256(nc)},
            {"path": _rel(preset_path), "sha256": stormspec.file_sha256(preset_path)},
        ],
        "platform": platform.platform(),
        "execution_mode": "precomputed",
        "payload_sha256": stormspec.payload_sha256(result),
        "title": scenario.name,
        "preset_id": scenario.id,
        "scenario_hash": result["scenario_hash"],
        "outcome": result["outcome"],
        "measurements": {
            "run_scenario_wall_time_s": measure["wall_time_s"],
            "solver_wall_time_s": result["solver"]["wall_time_s"],
            "process_wall_time_s": round(process_wall, 3),
            "peak_rss_mb": measure["peak_rss_mb"],
            "rss_method": measure["rss_method"],
            "cpu": platform.processor() or platform.machine(),
            "threads": scenario.execution.solver_options.threads,
        },
    }
    doc = {"artifact": header, "payload": result}
    data = json.dumps(doc, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(data.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        raise RuntimeError(f"artifact {scenario.id} exceeds {MAX_ARTIFACT_BYTES} bytes")
    (out_dir / f"{scenario.id}.json").write_text(data, encoding="utf-8")
    return header


def _rebuild_index(out_dir: Path) -> list[dict]:
    entries = []
    for path in sorted(out_dir.glob("*.json")):
        if path.name == "index.json":
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        h = doc.get("artifact") or {}
        if h.get("engine") != "pypsa":
            continue
        payload = doc.get("payload") or {}
        metrics = payload.get("metrics") or {}
        entries.append(
            {
                "artifact_id": h["artifact_id"],
                "kind": h["kind"],
                "network_id": h["network_id"],
                "title": h.get("title"),
                "scenario_id": payload.get("scenario_id"),
                "scenario_hash": payload.get("scenario_hash"),
                "outcome": payload.get("outcome"),
                "objective_eur": (payload.get("solver") or {}).get("objective_eur"),
                "unserved_energy_mwh": metrics.get("unserved_energy_mwh"),
                "measurements": h.get("measurements"),
                "payload_sha256": h.get("payload_sha256"),
                "created_at": h.get("created_at"),
            }
        )
    index = {"schema_version": INDEX_SCHEMA, "engine": "pypsa", "artifacts": entries}
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    return entries


def _fmt(x, nd=1) -> str:
    return "—" if x is None else f"{x:,.{nd}f}"


def _write_benchmark_md(path: Path, entries: list[dict]) -> None:
    rows = [
        "| Preset | Network | Outcome | Objective (EUR) | Unserved (MWh) | Solver wall (s) "
        "| run_scenario wall (s) | Peak RSS (MB) |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    plat = cpu = method = None
    for e in entries:
        m = e.get("measurements") or {}
        cpu = cpu or m.get("cpu")
        method = method or m.get("rss_method")
        rows.append(
            f"| `{e['artifact_id']}` | {e['network_id']} | {e['outcome']} | "
            f"{_fmt(e['objective_eur'], 0)} | {_fmt(e['unserved_energy_mwh'], 1)} | "
            f"{_fmt(m.get('solver_wall_time_s'), 2)} | "
            f"{_fmt(m.get('run_scenario_wall_time_s'), 2)} | "
            f"{_fmt(m.get('peak_rss_mb'), 0)} |"
        )
    plat = platform.platform()
    peaks = [(e.get("measurements") or {}).get("peak_rss_mb") for e in entries]
    peaks = [p for p in peaks if p is not None]
    over = [
        e["artifact_id"]
        for e in entries
        if ((e.get("measurements") or {}).get("peak_rss_mb") or 0) > 512
    ]
    text = [
        "# PyPSA preset benchmarks",
        "",
        "Generated by `workers/pypsa/scripts/precompute_presets.py` (do not edit by hand):",
        "",
        f"```\n{COMMAND}\n```",
        "",
        f"Platform: `{plat}`, CPU `{cpu}`, HiGHS single-threaded (`threads=1`). "
        "Each preset runs in a "
        f"fresh Python process; peak RSS = {method} of that process (includes the Python "
        "interpreter, PyPSA/linopy/xarray imports, the network, the linopy model and HiGHS).",
        "",
        *rows,
        "",
        "## 512 MB instance check (e.g. Render free tier)",
        "",
        f"Largest measured peak RSS: **{_fmt(max(peaks), 0) if peaks else '—'} MB**. "
        + (
            "Presets above 512 MB: " + ", ".join(f"`{i}`" for i in over) + ". These do NOT fit a "
            "512 MB instance for live execution; serve their precomputed artifacts instead, or "
            "run live on a larger instance."
            if over
            else "All presets stay below 512 MB."
        ),
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(text), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--_child":
        return _child(*argv[1:4])

    import stormspec

    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "data" / "artifacts" / "pypsa")
    ap.add_argument("--network-root", type=Path, default=REPO_ROOT / "data" / "networks")
    ap.add_argument("--presets-dir", type=Path, default=stormspec.PRESETS_DIR)
    ap.add_argument("--only", nargs="*", default=None, help="preset ids to run (default: all)")
    ap.add_argument(
        "--benchmark-md",
        type=Path,
        default=None,
        help="also write a markdown benchmark table to this path",
    )
    args = ap.parse_args(argv)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    paths = stormspec.preset_paths(args.presets_dir)
    if args.only:
        paths = [p for p in paths if p.stem in set(args.only)]
    failures = 0
    for p in paths:
        scenario = stormspec.load_scenario(p)
        if scenario.execution.engine != "pypsa":
            continue
        print(f"PRESET {p.stem} ...", flush=True)
        try:
            h = _run_one(p, args.network_root, args.out_dir)
        except Exception as exc:  # report and continue with the other presets
            failures += 1
            print(f"  FAILED: {type(exc).__name__}: {exc}", flush=True)
            continue
        m = h["measurements"]
        print(
            f"  {h['outcome']}  solver {m['solver_wall_time_s']} s  "
            f"run {m['run_scenario_wall_time_s']}"
            f" s  peak RSS {m['peak_rss_mb']} MB",
            flush=True,
        )
    entries = _rebuild_index(args.out_dir)
    if args.benchmark_md:
        _write_benchmark_md(args.benchmark_md, entries)
    print(f"index: {len(entries)} artifacts; failures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
