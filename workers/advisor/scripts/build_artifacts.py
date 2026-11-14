"""Regenerate the Crisis Response Advisor artifacts (contract §5, kind ``advisor``).

Runs every crisis in ``presets/crises.json`` and writes ``data/artifacts/advisor/<id>.json`` plus
``index.json``. Run from ``workers/advisor``:

    uv run python scripts/build_artifacts.py                       # sources from data/networks
    uv run python scripts/build_artifacts.py --matpower-dir ../../../upstream/pglib-opf

``--matpower-dir`` is only used when ``data/networks/<id>/source/*.m`` does not exist.
Single-threaded BLAS is recommended (``OMP_NUM_THREADS=1``); every run is deterministic.
"""

from __future__ import annotations

import sys

from gridstorm_advisor.cli import main

if __name__ == "__main__":
    raise SystemExit(
        main(["build", *sys.argv[1:]], build_command="uv run python scripts/build_artifacts.py")
    )
