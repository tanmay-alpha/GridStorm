"""Independently reconstruct published Monte Carlo quantities from solved state frequencies."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import NormalDist

import pytest

ARTIFACTS = Path(__file__).resolve().parents[3] / "data" / "artifacts" / "stormrisk"


def test_published_studies_have_consistent_probability_weighted_results():
    index = json.loads((ARTIFACTS / "index.json").read_text(encoding="utf-8"))
    assert index["artifacts"], "At least one real Monte Carlo study must be published"
    for entry in index["artifacts"]:
        artifact = json.loads((ARTIFACTS / entry["path"]).read_text(encoding="utf-8"))
        payload = artifact["payload"]
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        assert hashlib.sha256(canonical.encode()).hexdigest() == artifact["artifact"]["payload_sha256"]
        assert payload["engine"]["engine"]["name"] == "pypsa"
        states = payload["states"]
        accounting = payload["sample_accounting"]
        n = accounting["n_samples"]
        assert sum(s["count"] for s in states) == n
        assert len(payload["sample_state_index"]) == n
        assert accounting["n_distinct_states"] == len(states) == payload["runtime"]["solves"]
        for i, state in enumerate(states):
            assert payload["sample_state_index"].count(i) == state["count"]
        for outcome in ("feasible", "infeasible", "error", "invalid"):
            assert accounting[f"n_{outcome}_samples"] == sum(
                s["count"] for s in states if s["outcome"] == outcome
            )
        feasible = [s for s in states if s["outcome"] == "feasible"]
        nf = sum(s["count"] for s in feasible)
        assert nf > 1
        # Frequencies are the empirical probability measure, not equiprobable distinct states.
        expected = math.fsum(s["count"] * s["unserved_energy_mwh"] for s in feasible) / nf
        variance = math.fsum(
            s["count"] * (s["unserved_energy_mwh"] - expected) ** 2 for s in feasible
        ) / (nf - 1)
        se = math.sqrt(variance / nf)
        estimates = payload["estimates"]
        assert estimates["eens_mwh"] == pytest.approx(expected, rel=2e-5, abs=1e-6)
        assert estimates["se_eens_mwh"] == pytest.approx(se, rel=2e-5, abs=1e-6)
        half = NormalDist().inv_cdf(0.975) * se
        assert estimates["ci95_low_mwh"] == pytest.approx(max(0, expected - half), rel=2e-5)
        assert estimates["ci95_high_mwh"] == pytest.approx(expected + half, rel=2e-5)
        shed = sum(s["count"] for s in feasible
                   if s["unserved_energy_mwh"] > payload["sampling_spec"]["shed_tolerance_mwh"])
        assert estimates["lolp"] == pytest.approx(shed / nf, rel=2e-5)
        assert payload["convergence"][-1]["n"] == nf
        assert payload["convergence"][-1]["eens_mwh"] == pytest.approx(expected, rel=2e-5)
        assert payload["runtime"]["wall_time_s"] > 0
        assert payload["runtime"]["peak_rss_mb_main_process"] > 0
