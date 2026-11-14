"""Small, fully specified electrical networks; no external data or solver mocks."""

import numpy as np
import pytest

from stormml.cases import MatpowerCase


@pytest.fixture
def triangle():
    # Equal-reactance ring, 80 MW total demand, 100 MVA branch ratings, one linear-cost generator.
    bus = np.array(
        [
            [1, 3, 0, 0, 0, 0, 1, 1, 0, 110, 1, 1.2, 0.8],
            [2, 1, 50, 10, 0, 0, 1, 1, 0, 110, 1, 1.2, 0.8],
            [3, 1, 30, 5, 0, 0, 1, 1, 0, 110, 1, 1.2, 0.8],
        ],
        dtype=float,
    )
    branch = np.array(
        [
            [1, 2, 0.01, 0.1, 0, 100, 100, 100, 0, 0, 1, -360, 360],
            [2, 3, 0.01, 0.1, 0, 100, 100, 100, 0, 0, 1, -360, 360],
            [3, 1, 0.01, 0.1, 0, 100, 100, 100, 0, 0, 1, -360, 360],
        ],
        dtype=float,
    )
    gen = np.array([[1, 80, 0, 300, -300, 1, 100, 1, 300, 0]], dtype=float)
    gencost = np.array([[2, 0, 0, 3, 0, 10, 0]], dtype=float)
    return MatpowerCase("triangle", 100, bus, gen, branch, gencost=gencost)


@pytest.fixture
def congested_triangle():
    # Cheap generator at bus 1, expensive one at bus 3, 40 MVA ratings: the cheap unit alone would
    # need ~80 MW over two 40 MVA branches, so the OPF branch limits must bind.
    bus = np.array(
        [
            [1, 3, 0, 0, 0, 0, 1, 1, 0, 110, 1, 1.1, 0.9],
            [2, 1, 50, 10, 0, 0, 1, 1, 0, 110, 1, 1.1, 0.9],
            [3, 2, 30, 5, 0, 0, 1, 1, 0, 110, 1, 1.1, 0.9],
        ],
        dtype=float,
    )
    branch = np.array(
        [
            [1, 2, 0.01, 0.1, 0, 40, 40, 40, 0, 0, 1, -360, 360],
            [2, 3, 0.01, 0.1, 0, 40, 40, 40, 0, 0, 1, -360, 360],
            [3, 1, 0.01, 0.1, 0, 40, 40, 40, 0, 0, 1, -360, 360],
        ],
        dtype=float,
    )
    gen = np.array(
        [
            [1, 80, 0, 300, -300, 1, 100, 1, 300, 0],
            [3, 0, 0, 300, -300, 1, 100, 1, 300, 0],
        ],
        dtype=float,
    )
    gencost = np.array([[2, 0, 0, 3, 0, 10, 0], [2, 0, 0, 3, 0, 50, 0]], dtype=float)
    return MatpowerCase("congested-triangle", 100, bus, gen, branch, gencost=gencost)
