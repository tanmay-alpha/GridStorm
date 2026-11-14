from __future__ import annotations

import math

import numpy as np
import pytest

from stormrisk import Z_975, convergence_trace, importance_ranking, mc_statistics


def test_mc_statistics_hand_computed():
    # 10 samples: five at 0 MWh, three at 10 MWh, two at 30 MWh.
    s = mc_statistics([0.0, 10.0, 30.0], [5, 3, 2])
    assert s["n_samples"] == 10
    assert s["eens_mwh"] == pytest.approx(9.0)  # (0*5 + 10*3 + 30*2) / 10
    var = (5 * 81 + 3 * 1 + 2 * 441) / 9  # sum c (y - 9)^2 / (N - 1) = 1290 / 9
    assert s["std_unserved_mwh"] == pytest.approx(math.sqrt(var))
    se = math.sqrt(var / 10)
    assert s["se_eens_mwh"] == pytest.approx(se)
    assert s["ci95_low_mwh"] == pytest.approx(9.0 - Z_975 * se)
    assert s["ci95_high_mwh"] == pytest.approx(9.0 + Z_975 * se)
    assert s["cv_eens"] == pytest.approx(se / 9.0)
    assert s["lolp"] == pytest.approx(0.5)
    assert s["se_lolp"] == pytest.approx(math.sqrt(0.25 / 10))
    assert s["n_loss_of_load_samples"] == 5
    assert s["mean_unserved_given_shed_mwh"] == pytest.approx(18.0)  # 90 / 5
    assert s["p95_unserved_mwh"] == pytest.approx(30.0)
    assert s["max_unserved_mwh"] == 30.0


def test_weighted_equals_expanded_samples():
    rng = np.random.default_rng(3)
    vals = rng.exponential(5.0, size=7)
    cnts = rng.integers(1, 20, size=7)
    s = mc_statistics(vals, cnts)
    flat = np.repeat(vals, cnts)
    assert s["eens_mwh"] == pytest.approx(flat.mean())
    assert s["std_unserved_mwh"] == pytest.approx(flat.std(ddof=1))
    assert s["p95_unserved_mwh"] == pytest.approx(np.percentile(flat, 95))


def test_zero_eens_has_undefined_cv_and_clipped_ci():
    s = mc_statistics([0.0], [50])
    assert s["eens_mwh"] == 0.0 and s["cv_eens"] is None
    assert s["ci95_low_mwh"] == 0.0 and s["ci95_high_mwh"] == 0.0
    assert s["lolp"] == 0.0 and s["mean_unserved_given_shed_mwh"] is None


def test_shed_tolerance():
    s = mc_statistics([1e-9, 2.0], [1, 1], tol=1e-6)
    assert s["n_loss_of_load_samples"] == 1


@pytest.mark.parametrize(
    "vals,cnts", [([], []), ([-1.0], [1]), ([float("nan")], [1]), ([1.0], [0]), ([1.0, 2.0], [1])]
)
def test_rejects_bad_input(vals, cnts):
    with pytest.raises(ValueError):
        mc_statistics(vals, cnts)


def test_convergence_trace_matches_running_mean():
    seq = [0.0, 10.0, 0.0, 30.0, 0.0, 0.0, 10.0, 30.0, 0.0, 10.0]
    tr = convergence_trace(seq)
    assert tr[0] == {"n": 1, "eens_mwh": 0.0, "ci95_half_width_mwh": None}
    assert tr[-1]["n"] == 10
    assert tr[-1]["eens_mwh"] == pytest.approx(np.mean(seq))
    half = Z_975 * np.std(seq, ddof=1) / math.sqrt(10)
    assert tr[-1]["ci95_half_width_mwh"] == pytest.approx(half)
    for p in tr:
        assert p["eens_mwh"] == pytest.approx(np.mean(seq[: p["n"]]))
    assert [p["n"] for p in tr] == sorted({p["n"] for p in tr})


def test_importance_ranking_hand_computed():
    outs = [[], [("line", "A")], [("line", "A"), ("line", "B")], [("line", "B")]]
    vals = [0.0, 10.0, 30.0, 0.0]
    cnts = [6, 2, 1, 1]  # total unserved = 20 + 30 = 50 over N = 10
    rows = importance_ranking(outs, vals, cnts)
    assert [r["asset_id"] for r in rows] == ["A", "B"]
    a, b = rows
    assert a["n_samples_out"] == 3 and a["n_samples_out_with_shed"] == 3
    assert a["share_of_sampled_unserved_energy"] == pytest.approx(1.0)
    assert a["conditional_mean_unserved_if_out_mwh"] == pytest.approx(50 / 3)
    assert a["conditional_mean_unserved_if_in_service_mwh"] == pytest.approx(0.0)
    assert b["n_samples_out"] == 2 and b["n_samples_out_with_shed"] == 1
    assert b["share_of_sampled_unserved_energy"] == pytest.approx(30 / 50)
    assert b["conditional_mean_unserved_if_in_service_mwh"] == pytest.approx(20 / 8)


# --- stormspec.eens contract (EENS = sum_s p_s E_s over a complete, normalised scenario set) ---


def test_stormspec_eens_rejects_improperly_weighted_inputs():
    from stormspec import eens

    assert eens([(0.25, 8.0), (0.75, 0.0)]) == pytest.approx(2.0)
    with pytest.raises(ValueError, match="sum"):
        eens([(0.5, 8.0), (0.4, 0.0)])  # does not sum to 1: rejected, never renormalised
    with pytest.raises(ValueError, match="sum"):
        eens([(0.6, 1.0), (0.6, 2.0)])
    with pytest.raises(ValueError, match="outside"):
        eens([(1.2, 1.0), (-0.2, 0.0)])
    with pytest.raises(ValueError, match="negative"):
        eens([(1.0, -1.0)])
    with pytest.raises(ValueError, match="finite"):
        eens([(1.0, float("nan"))])
    with pytest.raises(ValueError):
        eens([])


def test_mc_statistics_normalises_counts_before_eens():
    # mc_statistics normalises counts to p_s = c_s / N before calling stormspec.eens
    s = mc_statistics([4.0, 0.0], [1, 3])
    assert s["eens_mwh"] == pytest.approx(1.0)
