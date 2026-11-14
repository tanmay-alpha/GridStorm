"""Population resolution, deterministic state sampling, and sample -> StormSpec scenario mapping.

Sampling model (crude Monte Carlo, independent components):

* every asset ``k`` in the sampled population is out of service for the *whole horizon* with
  probability ``q_k`` (its class unavailability), independently of every other asset;
* optionally, a system-wide demand multiplier ``d`` is drawn independently of the outages.

Random numbers come exclusively from ``numpy.random.Generator(PCG64(seed))`` in a fixed order
(outage uniforms row by row in fixed-size chunks, then demand draws), so the same spec, base
scenario and network yield bit-identical sample sets.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import numpy as np
from stormspec import Scenario, canonical_dumps

from .spec import COMPONENT_EVENTS, DiscreteDemand, SamplingSpec, TruncatedNormalDemand

#: Rows of outage uniforms generated per chunk (fixed: part of the reproducibility contract).
CHUNK_ROWS = 4096
_OUTAGE_EVENTS = {"line_outage", "link_outage", "generator_outage"}


class StudyInputError(ValueError):
    """The base scenario / sampling spec / network combination cannot be studied as specified."""


@dataclass(frozen=True)
class PopulationAsset:
    component: str  # line | transformer | link | generator (ids are unique only per component)
    asset_id: str
    event_type: str
    unavailability: float
    class_name: str

    def event(self) -> dict[str, Any]:
        """Whole-horizon StormSpec outage event; line_outage carries its component list."""
        ev: dict[str, Any] = {"type": self.event_type, "asset_id": self.asset_id, "window": None}
        if self.event_type == "line_outage":
            ev["component"] = self.component
        return ev


@dataclass(frozen=True)
class Population:
    assets: tuple[PopulationAsset, ...]
    excluded_base_outaged: tuple[tuple[str, str], ...]  # (component, asset_id)
    class_counts: dict[str, int]

    @property
    def q(self) -> np.ndarray:
        return np.array([a.unavailability for a in self.assets], dtype=float)


@dataclass(frozen=True)
class SampledState:
    """One distinct sampled system state."""

    outage_idx: tuple[int, ...]  # indices into Population.assets, ascending
    demand_multiplier: float | None

    def outages(self, population: Population) -> list[tuple[str, str]]:
        """Sorted (component, asset_id) pairs (component disambiguates colliding ids)."""
        return sorted(
            (population.assets[i].component, population.assets[i].asset_id) for i in self.outage_idx
        )

    def key(self, population: Population) -> str:
        """sha256 of the canonical JSON of the state (outages + demand multiplier)."""
        doc = {
            "outages": [list(p) for p in self.outages(population)],
            "demand_multiplier": self.demand_multiplier,
        }
        return hashlib.sha256(canonical_dumps(doc)).hexdigest()


@dataclass(frozen=True)
class SampleSet:
    states: tuple[SampledState, ...]  # distinct states, in order of first appearance
    counts: tuple[int, ...]  # number of samples per state
    sample_state_index: tuple[int, ...]  # state index of every sample, in draw order

    @property
    def n_samples(self) -> int:
        return len(self.sample_state_index)


def _base_outaged_assets(base: Scenario) -> set[tuple[str, str]]:
    """(component, asset_id) of every outage already in the base scenario."""
    out: set[tuple[str, str]] = set()
    for ev in base.events:
        if ev.type == "line_outage":
            out.add((ev.component, ev.asset_id))
        elif ev.type == "link_outage":
            out.add(("link", ev.asset_id))
        elif ev.type == "generator_outage":
            out.add(("generator", ev.asset_id))
    return out


def resolve_population(base: Scenario, spec: SamplingSpec, network: dict[str, Any]) -> Population:
    """Map outage classes onto the network's assets (canonical-grid/1.0 dict).

    Raises :class:`StudyInputError` if a class matches no asset, names unknown asset ids, or an
    asset matches more than one class. Assets already outaged by the base scenario are excluded
    from sampling (they are out in every sample) and reported.
    """
    base_out = _base_outaged_assets(base)
    owner: dict[tuple[str, str], str] = {}
    assets: list[PopulationAsset] = []
    excluded: set[tuple[str, str]] = set()
    class_counts: dict[str, int] = {}
    for cls in spec.outage_classes:
        key, event_type = COMPONENT_EVENTS[cls.component]
        rows = network.get(key) or []
        known = {str(r["id"]) for r in rows}
        if cls.asset_ids is not None:
            missing = sorted(set(cls.asset_ids) - known)
            if missing:
                raise StudyInputError(
                    f"outage class {cls.name!r}: unknown {cls.component} ids {missing[:10]}"
                )
        n = 0
        for r in rows:
            aid = str(r["id"])
            if cls.asset_ids is not None and aid not in cls.asset_ids:
                continue
            if cls.carriers is not None and r.get("carrier") not in cls.carriers:
                continue
            if (cls.component, aid) in owner:
                raise StudyInputError(
                    f"{cls.component} {aid!r} matches outage classes "
                    f"{owner[(cls.component, aid)]!r} and {cls.name!r}"
                )
            owner[(cls.component, aid)] = cls.name
            n += 1
            if (cls.component, aid) in base_out:
                excluded.add((cls.component, aid))
                continue
            assets.append(
                PopulationAsset(cls.component, aid, event_type, cls.unavailability, cls.name)
            )
        if n == 0:
            raise StudyInputError(f"outage class {cls.name!r} matches no asset in the network")
        class_counts[cls.name] = n
    assets.sort(key=lambda a: (a.component, a.asset_id))
    return Population(tuple(assets), tuple(sorted(excluded)), class_counts)


def _demand_draws(rng: np.random.Generator, spec: SamplingSpec) -> list[float | None]:
    n = spec.n_samples
    dist = spec.demand_multiplier
    if dist is None:
        return [None] * n
    if isinstance(dist, DiscreteDemand):
        idx = rng.choice(len(dist.values), size=n, p=np.asarray(dist.probabilities))
        return [float(dist.values[i]) for i in idx]
    assert isinstance(dist, TruncatedNormalDemand)
    draws = rng.normal(dist.mean, dist.std, size=n)
    bad = (draws < dist.lower) | (draws > dist.upper)
    while bad.any():  # rejection sampling, deterministic given the stream
        draws[bad] = rng.normal(dist.mean, dist.std, size=int(bad.sum()))
        bad = (draws < dist.lower) | (draws > dist.upper)
    q = np.round(draws / dist.resolution) * dist.resolution
    q = np.clip(q, dist.lower, dist.upper)
    return [round(float(v), 10) for v in q]


def draw_samples(population: Population, spec: SamplingSpec) -> SampleSet:
    """Draw ``spec.n_samples`` states and collapse identical ones (frequency-weighted)."""
    rng = np.random.Generator(np.random.PCG64(spec.seed))
    q = population.q
    m = len(q)
    outage_rows: list[tuple[int, ...]] = []
    remaining = spec.n_samples
    while remaining > 0:
        rows = min(CHUNK_ROWS, remaining)
        if m:
            u = rng.random((rows, m))
            failed = u < q[None, :]
            outage_rows.extend(tuple(np.flatnonzero(r).tolist()) for r in failed)
        else:
            outage_rows.extend(() for _ in range(rows))
        remaining -= rows
    demand = _demand_draws(rng, spec)

    index: dict[tuple[tuple[int, ...], float | None], int] = {}
    states: list[SampledState] = []
    counts: list[int] = []
    seq: list[int] = []
    for out, d in zip(outage_rows, demand, strict=True):
        k = (out, d)
        j = index.get(k)
        if j is None:
            j = len(states)
            index[k] = j
            states.append(SampledState(out, d))
            counts.append(0)
        counts[j] += 1
        seq.append(j)
    return SampleSet(tuple(states), tuple(counts), tuple(seq))


def state_scenario(
    base: Scenario, state: SampledState, population: Population, state_key: str
) -> Scenario:
    """Concrete StormSpec scenario for one sampled state (whole-horizon outages, window null)."""
    doc = base.model_dump(mode="json")
    events = list(doc["events"])
    if state.demand_multiplier is not None:
        events.append(
            {
                "type": "demand_multiplier",
                "value": state.demand_multiplier,
                "buses": None,
                "window": None,
            }
        )
    for i in state.outage_idx:
        events.append(population.assets[i].event())
    doc["events"] = events
    prefix = base.id[:47].rstrip("-")
    doc["id"] = f"{prefix}-mc-{state_key[:12]}"
    doc["name"] = f"{base.name[:150]} | Monte Carlo state {state_key[:12]}"
    doc["assumptions"] = list(doc.get("assumptions") or []) + [
        "Monte Carlo sampled state (StormRisk): outages are whole-horizon and drawn independently "
        "with modelled unavailabilities; not an observed or forecast event."
    ]
    if len(doc["assumptions"]) > 100:
        doc["assumptions"] = doc["assumptions"][-100:]
    return Scenario.model_validate(doc)
