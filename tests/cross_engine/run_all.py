"""Reproduce the whole cross-engine agreement benchmark (docs/benchmarks/cross-engine.md).

    python tests/cross_engine/run_all.py [<network_id> ...]      # from the repo root; stdlib only

Each engine runs in its own component environment (contracts.md §1 — environments are never
merged), via ``uv run --project``:
  1. workers/pandapower       -> pp_side.py     (rundcpp / runpp / rundcopp + numpy reference)
  2. pipelines/network-import -> pypsa_side.py  (PyPSA lpf / optimize with HiGHS on network.nc)
  3. pipelines/network-import -> compare.py     (metrics, verdicts, data/artifacts/cross-engine/*)
  4. pipelines/network-import -> test_harness.py (analytical physics + artifact integrity tests)
Solvers are pinned to one thread. Raw PGLib files come from data/networks/<id>/source/ or, if the
importer output is not committed, from GRIDSTORM_PGLIB_DIR (default ../upstream/pglib-opf).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STEPS = (
    ("workers/pandapower", "pp_side.py"),
    ("pipelines/network-import", "pypsa_side.py"),
    ("pipelines/network-import", "compare.py"),
    ("pipelines/network-import", "test_harness.py"),
)


def main(ids: list[str]) -> int:
    env = {
        **os.environ,
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMBA_NUM_THREADS": "1",
        "PYTHONHASHSEED": "0",
    }
    for project, script in STEPS:
        cmd = ["uv", "run", "--frozen", "--project", project, "python", str(HERE / script), *ids]
        print("+", " ".join(cmd), flush=True)
        rc = subprocess.run(cmd, cwd=REPO, env=env).returncode
        if rc:
            print(f"step {script} failed with exit code {rc}", file=sys.stderr)
            return rc
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
