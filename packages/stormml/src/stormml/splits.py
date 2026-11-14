"""Train/test splits. The leakage unit is the operating point (``op_id``): every contingency of
one operating point is on the same side of a split.

* ``operating_point``: seeds are drawn from two disjoint ranges at generation time
  (``TRAIN_SEED_BASE + i`` vs ``TEST_SEED_BASE + i``); train = first range, test = second, all
  networks pooled (each network appears on both sides with different operating points).
* ``leave_network_out``: train on every operating point of the other networks, test on all
  operating points of the held-out network.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TRAIN_SEED_BASE = 1_000_000
TEST_SEED_BASE = 2_000_000


class LeakageError(AssertionError):
    pass


@dataclass(frozen=True)
class Split:
    name: str
    train: np.ndarray  # row indices
    test: np.ndarray


def check_no_leakage(split: Split, op_id: np.ndarray, network: np.ndarray | None = None) -> None:
    if np.intersect1d(split.train, split.test).size:
        raise LeakageError(f"{split.name}: rows shared between train and test")
    shared = np.intersect1d(op_id[split.train], op_id[split.test])
    if shared.size:
        raise LeakageError(f"{split.name}: operating points in both train and test: {shared[:5]}")
    if network is not None and split.name.startswith("leave_network_out"):
        nets = np.intersect1d(network[split.train], network[split.test])
        if nets.size:
            raise LeakageError(f"{split.name}: networks in both train and test: {nets}")


def operating_point_split(seed: np.ndarray, op_id: np.ndarray) -> Split:
    train = np.flatnonzero((seed >= TRAIN_SEED_BASE) & (seed < TEST_SEED_BASE))
    test = np.flatnonzero(seed >= TEST_SEED_BASE)
    s = Split("operating_point", train, test)
    check_no_leakage(s, op_id)
    return s


def leave_network_out_split(network: np.ndarray, op_id: np.ndarray, held_out: str) -> Split:
    test = np.flatnonzero(network == held_out)
    train = np.flatnonzero(network != held_out)
    if test.size == 0:
        raise ValueError(f"no rows for network {held_out!r}")
    s = Split(f"leave_network_out:{held_out}", train, test)
    check_no_leakage(s, op_id, network)
    return s
