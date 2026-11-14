"""Regenerate StormBench artifacts (CI default: case14_ieee, case30_ieee).

    uv run --locked python scripts/generate_artifacts.py --out-dir DIR [--cases a,b] [--repeats N]

Non-deterministic fields: keys ending ``_s`` / ``_mib``, ``created_at``, ``platform``,
``payload_sha256``, ``artifact.command``.
"""

import os
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

from stormbench.bench import CI_CASES, main  # noqa: E402

if __name__ == "__main__":
    argv = sys.argv[1:]
    if not any(a.startswith("--cases") for a in argv):
        argv += ["--cases", ",".join(CI_CASES)]
    raise SystemExit(main(argv))
