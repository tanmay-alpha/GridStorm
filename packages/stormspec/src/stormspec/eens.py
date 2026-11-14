"""Expected Energy Not Served (EENS) over a discrete set of mutually exclusive scenarios.

    EENS = sum_s p_s * E_unserved,s          [MWh]

where ``p_s`` is the probability of scenario ``s`` and ``E_unserved,s`` its unserved energy
(``metrics.unserved_energy_mwh`` of a feasible gridstorm-result). The scenarios must form a
complete, mutually exclusive set: probabilities are each in [0, 1] and must sum to 1 within
``tol``. The result is only as meaningful as the probabilities supplied; GridStorm does not
estimate outage probabilities itself. Infeasible scenarios have no unserved-energy number and
must not be passed in (an infeasible state is not "zero unserved energy").
"""

from __future__ import annotations

import math
from collections.abc import Iterable


def eens(results: Iterable[tuple[float, float]], *, tol: float = 1e-9) -> float:
    """Return the probability-weighted unserved energy in MWh.

    Raises ``ValueError`` for empty input, non-finite values, probabilities outside [0, 1],
    negative unserved energy, or probabilities not summing to 1 (|sum - 1| > tol).
    """
    pairs = list(results)
    if not pairs:
        raise ValueError("eens requires at least one (probability, unserved_mwh) pair")
    total_p = 0.0
    expected = 0.0
    for i, (p, e) in enumerate(pairs):
        p = float(p)
        e = float(e)
        if not (math.isfinite(p) and math.isfinite(e)):
            raise ValueError(f"pair {i}: probability and unserved energy must be finite")
        if not 0.0 <= p <= 1.0:
            raise ValueError(f"pair {i}: probability {p} outside [0, 1]")
        if e < 0.0:
            raise ValueError(f"pair {i}: unserved energy {e} MWh is negative")
        total_p += p
        expected += p * e
    if abs(total_p - 1.0) > tol:
        raise ValueError(f"probabilities sum to {total_p!r}, expected 1 (tolerance {tol})")
    return expected
