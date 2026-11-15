"""Evaluate committed artifacts / live results against all invariants (cached per artifact)."""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import stormspec

import netmodel
from invariants import Report, run_all
from provenance import check_provenance


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def evaluate_result(res: dict, scenario: stormspec.Scenario, label: str) -> Report:
    exp = netmodel.build(scenario) if res.get("outcome") == "feasible" else None
    return run_all(res, exp, scenario, label)


@cache
def evaluate_artifact(path: Path) -> Report:
    doc = load(path)
    tmp = Report(path.stem)
    scenario = check_provenance(doc, tmp)
    rep = evaluate_result(doc["payload"], scenario, path.stem)
    rep.checks = {"provenance": tmp.checks["provenance"], **rep.checks}
    rep.facts.update(tmp.facts)
    return rep
