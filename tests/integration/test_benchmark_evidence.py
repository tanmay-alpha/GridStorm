"""Independent arithmetic checks of committed benchmark evidence, without engine imports.

These do not independently validate classifications: full aligned contingency vectors are required
for that. They detect inconsistent published ratios, sample counts, and comparison summaries.
"""

from __future__ import annotations

import json
from collections import Counter

import pytest

from conftest import REPO_ROOT

RESULTS = REPO_ROOT / "benchmarks" / "stormbench" / "results"
CASES = sorted(RESULTS.glob("case*.json"))
CROSS_ENGINE = sorted(
    (REPO_ROOT / "data" / "artifacts" / "cross-engine").glob("cross-engine-*.json")
)


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_benchmark_published_ratios(path):
    result = json.loads(path.read_text("utf-8"))
    for reference in ("dc", "ac"):
        comparison = result[f"screening_vs_{reference}"]
        tp, fp, fn, tn = (comparison[k] for k in ("tp", "fp", "fn", "tn"))
        assert all(isinstance(v, int) and v >= 0 for v in (tp, fp, fn, tn))
        assert tp + fp + fn + tn == comparison["n"]
        for key, numerator, denominator in (("precision", tp, tp + fp), ("recall", tp, tp + fn)):
            expected = numerator / denominator if denominator else None
            if expected is None:
                assert comparison[key] is None
            else:
                assert comparison[key] == pytest.approx(expected, abs=5.1e-5)
    counts = result["counts"]
    assert counts["islanding"] + counts["screened"] == counts["contingencies"]
    assert result["screening_vs_dc"]["n"] == result["counts"]["screened"]
    ac = result["ac"]
    assert ac["converged"] + ac["not_converged"] == result["counts"]["screened"]


@pytest.mark.parametrize("path", CROSS_ENGINE, ids=lambda p: p.stem)
def test_cross_engine_summary_matches_checks(path):
    payload = json.loads(path.read_text("utf-8"))["payload"]
    counts = Counter(check["verdict"] for check in payload["checks"])
    assert {key: counts[key] for key in payload["summary"]} == payload["summary"]
    assert sum(payload["summary"].values()) == len(payload["checks"])
