#!/usr/bin/env python3
"""Self-test for scripts/compare_artifacts.py (stdlib only; run in CI `scripts` job)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_artifacts import DEFAULT_IGNORE, compare, main  # noqa: E402


def diffs(a: object, b: object, rel: float = 1e-4, abs_: float = 1e-6) -> list[str]:
    return list(compare(a, b, rel_tol=rel, abs_tol=abs_, ignore=DEFAULT_IGNORE))


def run() -> None:
    assert diffs({"x": 100.0}, {"x": 100.005}) == []  # rel 5e-5 < 1e-4
    assert len(diffs({"x": 100.0}, {"x": 100.02})) == 1  # rel 2e-4 > 1e-4
    assert diffs({"x": 0.0}, {"x": 5e-7}) == []  # abs tol near zero
    assert diffs({"n": 3}, {"n": 3.0}) == []  # int vs float numeric compare
    assert len(diffs({"s": "feasible"}, {"s": "infeasible"})) == 1
    assert len(diffs({"b": True}, {"b": 1})) == 1  # bool is not a number
    assert len(diffs([1, 2], [1, 2, 3])) == 1
    assert len(diffs({"a": 1}, {"a": 1, "extra": 2})) == 1
    assert diffs({"created_at": "2026-01-01", "v": 1}, {"created_at": "2026-02-02", "v": 1}) == []
    assert diffs({"m": {"platform": "linux"}}, {"m": {"platform": "win32"}}) == []
    assert diffs(float("nan"), float("nan")) == []

    with tempfile.TemporaryDirectory() as tmp:
        ref, new = Path(tmp, "ref"), Path(tmp, "new")
        (ref / "sub").mkdir(parents=True)
        (new / "sub").mkdir(parents=True)
        doc = {"artifact": {"created_at": "t0"}, "payload": {"eens_mwh": 12.3456}}
        (ref / "sub" / "a.json").write_text(json.dumps(doc))
        doc["artifact"]["created_at"] = "t1"
        (new / "sub" / "a.json").write_text(json.dumps(doc))
        assert main([str(ref), str(new)]) == 0
        doc["payload"]["eens_mwh"] = 13.0
        (new / "sub" / "a.json").write_text(json.dumps(doc))
        assert main([str(ref), str(new)]) == 1
        (ref / "b.json").write_text("{}")
        assert main([str(ref), str(new), "--rel-tol", "0.1"]) == 1  # b.json missing
        assert main([str(ref), str(new), "--rel-tol", "0.1", "--allow-missing"]) == 0
        assert main([str(ref / "nope"), str(new)]) == 2
    print("compare_artifacts self-test: OK")


if __name__ == "__main__":
    run()
