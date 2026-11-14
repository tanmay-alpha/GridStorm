"""MODELED mapping of an observed stress day onto the network's own 24-hour profiles.

Notation (hour ``h`` = 0..23 of a UTC day; network snapshot ``h`` = 2011-01-01 ``h``:00):

* ``L_net(h)``  - total network load (sum of ``loads_t.p_set``) at snapshot ``h``.
* ``F(d,h)``    - ENTSO-E day-ahead total load forecast for Germany (Reg. 543/2013 Art. 6.1.b,
  CC BY 4.0) on the stress day ``d``. The *actual* load (Art. 6.1.a) is not openly licensed and
  is never used here.
* ``F(r,h)``    - the same forecast on the *reference day* ``r`` = the 1 January (UTC) nearest to
  ``d`` with complete data. The network's snapshots are 1 January 2011, so ``r`` is the observed
  analogue of the network's own day (same calendar day, same public holiday, same season) and
  absorbs the level difference between the network's demand data and the observed year.

Demand (shape **and** level relative to the reference day)::

    m_h = [F(d,h) / mean_h F(r,h)] / [L_net(h) / mean_h L_net(h)]

so the scaled network load ``m_h * L_net(h)`` follows the forecast stress-day shape exactly and
its level relative to the network's 1-January mean equals the forecast stress-day level relative
to the forecast 1-January mean. ``m_h`` is clipped to the StormSpec range ``(0, 5]``.

Renewables, per carrier ``c`` (network carriers ``Wind Onshore``, ``Wind Offshore``, ``Solar``),
one MODELED daily multiplier::

    CF_net,c(h) = sum_g p_max_pu_g(h) * p_nom_g / sum_g p_nom_g      (variable gens of carrier c)
    CF_obs,c(h) = observed generation_c(h) / observed capacity_c(h)
    w_c         = min(round(mean_h CF_obs,c / mean_h CF_net,c / STEP) * STEP, 1)

Observed generation is not openly licensed (Art. 16.1), so no hourly ratio is published: an
hourly ratio, even rounded to 0.05, returns the observed hourly CF to within 0.025 * CF_net. The
daily ratio keeps the network's own hourly shape and only scales its level, so the modeled day
carries the observed day's renewable *shortfall*, not its hourly profile. StormSpec only allows
``0 <= w <= 1``: days with more renewable output than the network day keep ``w = 1``
(``clipped``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

DEMAND_MAX = 5.0  # StormSpec DemandMultiplier.value upper bound (exclusive lower bound 0)
DECIMALS = 4
RENEWABLE_STEP = 0.05  # quantum of the daily renewable multiplier


@dataclass
class DemandMapping:
    multipliers: list[float]
    raw: list[float]
    clipped_hours: list[int]
    reference_mean_mw: float
    network_mean_mw: float


@dataclass
class RenewableMapping:
    carrier: str
    multiplier: float  # daily, on the RENEWABLE_STEP grid, in [0, 1]
    clipped: bool  # unrounded ratio above 1 -> multiplier 1
    network_cf: list[float]


def _as24(x, name: str) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    if a.shape != (24,):
        raise ValueError(f"{name} must have 24 hourly values, got shape {a.shape}")
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{name} contains missing/non-finite values (no interpolation allowed)")
    return a


def demand_multipliers(day, ref_day, net_load) -> DemandMapping:
    obs = _as24(day, "day")
    ref = _as24(ref_day, "ref_day")
    net = _as24(net_load, "net_load")
    if np.any(net <= 0) or np.any(ref <= 0) or np.any(obs < 0):
        raise ValueError("loads must be positive")
    ref_mean = float(ref.mean())
    net_mean = float(net.mean())
    raw = (net_mean * obs / ref_mean) / net
    clipped = np.clip(raw, 10.0**-DECIMALS, DEMAND_MAX)
    clipped_hours = [int(h) for h in np.flatnonzero(clipped != raw)]
    return DemandMapping(
        multipliers=[round(float(v), DECIMALS) for v in clipped],
        raw=[float(v) for v in raw],
        clipped_hours=clipped_hours,
        reference_mean_mw=ref_mean,
        network_mean_mw=net_mean,
    )


def renewable_daily_multiplier(carrier: str, obs_cf, net_cf) -> RenewableMapping:
    obs = _as24(obs_cf, f"obs_cf[{carrier}]")
    net = _as24(net_cf, f"net_cf[{carrier}]")
    if np.any(obs < 0) or np.any(net < 0):
        raise ValueError("capacity factors must be >= 0")
    if net.mean() <= 0.0:
        raise ValueError(f"{carrier}: network CF is zero all day; multiplier undefined")
    ratio = float(obs.mean() / net.mean())
    w = min(round(ratio / RENEWABLE_STEP) * RENEWABLE_STEP, 1.0)
    return RenewableMapping(
        carrier=carrier,
        multiplier=round(w, 2),
        clipped=ratio > 1.0,
        network_cf=[float(v) for v in net],
    )


def effective_cf(mapping: RenewableMapping) -> list[float]:
    """Network CF after applying the daily multiplier: w * CF_net."""
    return [float(n) * mapping.multiplier for n in mapping.network_cf]


def capacity_weighted_cf(p_max_pu: np.ndarray, p_nom: np.ndarray) -> np.ndarray:
    """``(T, G)`` per-unit availability and ``(G,)`` capacities -> ``(T,)`` aggregate CF."""
    p_max_pu = np.asarray(p_max_pu, dtype=float)
    p_nom = np.asarray(p_nom, dtype=float)
    if p_max_pu.ndim != 2 or p_max_pu.shape[1] != p_nom.shape[0]:
        raise ValueError("shape mismatch")
    total = p_nom.sum()
    if total <= 0:
        raise ValueError("total capacity must be positive")
    return p_max_pu @ p_nom / total
