"""MODELED mapping of an observed stress day onto the network's own 24-hour profiles.

Notation (hour ``h`` = 0..23 of a UTC day; network snapshot ``h`` = 2011-01-01 ``h``:00):

* ``L_net(h)``  - total network load (sum of ``loads_t.p_set``) at snapshot ``h``.
* ``L_obs(d,h)`` - observed national load on the stress day ``d``.
* ``L_obs(r,h)`` - observed national load on the *reference day* ``r`` = the 1 January (UTC)
  nearest to ``d`` with complete data. The network's snapshots are 1 January 2011, so ``r`` is
  the observed analogue of the network's own day (same calendar day, same public holiday, same
  season) and absorbs both the level difference between the ENTSO-E data used to build the
  network (scaled by 1.12 in the PyPSA example) and the observed year.

Demand (shape **and** level relative to the reference day)::

    T(h)  = mean_h L_net(h) * L_obs(d,h) / mean_h L_obs(r,h)      # target network load
    m_h   = T(h) / L_net(h)
          = [L_obs(d,h) / mean_h L_obs(r,h)] / [L_net(h) / mean_h L_net(h)]

so the scaled network load ``m_h * L_net(h)`` follows the observed stress-day shape exactly and
its level relative to the network's 1-January mean equals the observed stress-day level relative
to the observed 1-January mean. ``m_h`` is clipped to the StormSpec range ``(0, 5]``.

Renewables, per carrier ``c`` (network carriers ``Wind Onshore``, ``Wind Offshore``, ``Solar``)::

    CF_net,c(h) = sum_g p_max_pu_g(h) * p_nom_g / sum_g p_nom_g      (variable gens of carrier c)
    CF_obs,c(h) = observed generation_c(h) / observed capacity_c(h)
    w_c,h       = clip(CF_obs,c(h) / CF_net,c(h), 0, 1)

Applied uniformly to every generator of the carrier, the capacity-weighted network CF becomes
exactly ``w * CF_net = CF_obs`` whenever no clipping occurs. StormSpec only allows
``0 <= w <= 1`` (availability must stay within [0, 1] per unit), so hours where the observed CF
exceeds the network CF are clipped to 1 and reported. Where ``CF_net,c(h) = 0`` (e.g. solar at
night) the multiplier has no effect on the model and no event is emitted (reported as
``undefined``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

DEMAND_MAX = 5.0  # StormSpec DemandMultiplier.value upper bound (exclusive lower bound 0)
DECIMALS = 4


@dataclass
class DemandMapping:
    multipliers: list[float]
    raw: list[float]
    clipped_hours: list[int]
    reference_mean_obs_mw: float
    network_mean_mw: float
    target_load_mw: list[float]


@dataclass
class RenewableMapping:
    carrier: str
    multipliers: list[float | None]  # None = undefined (network CF == 0) -> no event
    raw: list[float | None]
    clipped_hours: list[int] = field(default_factory=list)
    undefined_hours: list[int] = field(default_factory=list)
    observed_cf: list[float] = field(default_factory=list)
    network_cf: list[float] = field(default_factory=list)


def _as24(x, name: str) -> np.ndarray:
    a = np.asarray(x, dtype=float)
    if a.shape != (24,):
        raise ValueError(f"{name} must have 24 hourly values, got shape {a.shape}")
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{name} contains missing/non-finite values (no interpolation allowed)")
    return a


def demand_multipliers(obs_day, obs_ref_day, net_load) -> DemandMapping:
    obs = _as24(obs_day, "obs_day")
    ref = _as24(obs_ref_day, "obs_ref_day")
    net = _as24(net_load, "net_load")
    if np.any(net <= 0) or np.any(ref <= 0) or np.any(obs < 0):
        raise ValueError("loads must be positive")
    ref_mean = float(ref.mean())
    net_mean = float(net.mean())
    target = net_mean * obs / ref_mean
    raw = target / net
    clipped = np.clip(raw, 10.0 ** -DECIMALS, DEMAND_MAX)
    clipped_hours = [int(h) for h in np.flatnonzero(clipped != raw)]
    return DemandMapping(
        multipliers=[round(float(v), DECIMALS) for v in clipped],
        raw=[float(v) for v in raw],
        clipped_hours=clipped_hours,
        reference_mean_obs_mw=ref_mean,
        network_mean_mw=net_mean,
        target_load_mw=[float(v) for v in target],
    )


def renewable_multipliers(carrier: str, obs_cf, net_cf) -> RenewableMapping:
    obs = _as24(obs_cf, f"obs_cf[{carrier}]")
    net = _as24(net_cf, f"net_cf[{carrier}]")
    if np.any(obs < 0) or np.any(net < 0):
        raise ValueError("capacity factors must be >= 0")
    out = RenewableMapping(carrier=carrier, multipliers=[], raw=[],
                           observed_cf=[float(v) for v in obs], network_cf=[float(v) for v in net])
    for h in range(24):
        if net[h] <= 0.0:
            out.multipliers.append(None)
            out.raw.append(None)
            out.undefined_hours.append(h)
            continue
        r = float(obs[h] / net[h])
        w = min(max(r, 0.0), 1.0)
        if w != r:
            out.clipped_hours.append(h)
        out.raw.append(r)
        out.multipliers.append(round(w, DECIMALS))
    return out


def effective_cf(mapping: RenewableMapping) -> list[float]:
    """Network CF after applying the (rounded, clipped) multipliers: w * CF_net."""
    return [
        float(n) * (1.0 if w is None else float(w))
        for w, n in zip(mapping.multipliers, mapping.network_cf, strict=True)
    ]


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
