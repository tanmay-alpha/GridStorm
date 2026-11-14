"""Prove ``data/networks/pypsa-eur-be/network.nc`` solves in the GridStorm core env.

Runs one LOPF (``n.optimize``, HiGHS, threads=1) over the full horizon exactly as stored (capacity
expansion included, no PyPSA-Eur extra_functionality) and prints objective, wall time and the
process peak RSS as JSON. Optionally compares with the objective stored in the upstream
``solved_2050.nc``.

    uv run --project services/api python pipelines/pypsa-eur/solve_check.py \
        [--upstream-solved <build-out>/solved_2050.nc]
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import time
from importlib.metadata import version
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import linopy  # noqa: E402
import psutil  # noqa: E402
import pypsa  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
NETWORK = REPO_ROOT / "data" / "networks" / "pypsa-eur-be" / "network.nc"


def peak_rss_mb() -> float:
    mi = psutil.Process().memory_info()
    peak = getattr(mi, "peak_wset", None)  # Windows
    if peak is None:
        import resource

        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024  # Linux: KiB
    return round(peak / 2**20, 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--network", type=Path, default=NETWORK)
    ap.add_argument("--upstream-solved", type=Path)
    args = ap.parse_args()

    n = pypsa.Network(args.network)
    t0 = time.perf_counter()
    status, condition = n.optimize(
        solver_name="highs", solver_options={"threads": 1, "random_seed": 0}
    )
    wall = time.perf_counter() - t0
    report = {
        "network": str(args.network.relative_to(REPO_ROOT)) if args.network.is_relative_to(
            REPO_ROOT) else str(args.network),
        "snapshots": len(n.snapshots),
        "status": status,
        "termination_condition": condition,
        "objective_eur": n.objective,
        "optimize_wall_s": round(wall, 2),
        "peak_rss_mb": peak_rss_mb(),
        "pypsa": pypsa.__version__,
        "linopy": linopy.__version__,
        "highspy": version("highspy"),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }
    if args.upstream_solved:
        up = pypsa.Network(args.upstream_solved)
        report["upstream_solved_objective_eur"] = up.objective
        report["relative_difference"] = (n.objective - up.objective) / up.objective
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
