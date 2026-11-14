"""Shared fixtures: PyPSA example networks, unsolved and solved with HiGHS (single-threaded)."""

from __future__ import annotations

import logging
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import pypsa  # noqa: E402
import pytest  # noqa: E402

logging.getLogger("pypsa").setLevel(logging.ERROR)
logging.getLogger("linopy").setLevel(logging.ERROR)

HIGHS_OPTIONS = {"threads": 1, "output_flag": False}


def _solve(n: pypsa.Network) -> pypsa.Network:
    status, condition = n.optimize(solver_name="highs", solver_options=HIGHS_OPTIONS)
    assert status == "ok" and condition == "optimal", (status, condition)
    return n


@pytest.fixture(scope="session")
def ac_dc() -> pypsa.Network:
    return pypsa.examples.ac_dc_meshed()


@pytest.fixture(scope="session")
def ac_dc_solved() -> pypsa.Network:
    return _solve(pypsa.examples.ac_dc_meshed())


@pytest.fixture(scope="session")
def scigrid() -> pypsa.Network:
    return pypsa.examples.scigrid_de()


@pytest.fixture(scope="session")
def scigrid_solved() -> pypsa.Network:
    return _solve(pypsa.examples.scigrid_de())
