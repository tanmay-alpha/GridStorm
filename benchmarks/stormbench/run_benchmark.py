"""Full StormBench run (all six cases) -> benchmarks/stormbench/results/*.json and
data/artifacts/stormbench/*.json + index.json.

    cd packages/stormbench && uv run python ../../benchmarks/stormbench/run_benchmark.py
"""

import os
import sys
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

from stormbench.bench import main  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

if __name__ == "__main__":
    raise SystemExit(
        main(
            [
                "--out-dir",
                str(ROOT / "data" / "artifacts" / "stormbench"),
                "--results-dir",
                str(ROOT / "benchmarks" / "stormbench" / "results"),
                *sys.argv[1:],
            ]
        )
    )
