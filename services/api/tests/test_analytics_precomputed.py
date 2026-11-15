"""Committed precomputed analytics (data/networks/<id>/analytics) against live gridstorm_analytics.

The API process must never import pypsa (docs/benchmarks/api-memory.md): served results come from
the committed files, and filtered results are derived from them. These tests recompute every
kind with ``gridstorm_analytics`` (this test process may import pypsa) and compare.
"""

from __future__ import annotations

import asyncio
import json
import math
import subprocess
import sys
from typing import Any

import pytest

from gridstorm_api.analytics import AnalyticsService
from gridstorm_api.catalog import NetworkCatalog
from gridstorm_api.config import REPO_ROOT
from gridstorm_api.errors import Unprocessable

DATA = REPO_ROOT / "data"
NETWORK_IDS = [
    n["id"] for n in json.loads((DATA / "networks" / "catalog.json").read_text())["networks"]
]
SERVED_ONLY = ("execution_mode", "precomputed")


@pytest.fixture(scope="module")
def catalog() -> NetworkCatalog:
    return NetworkCatalog(DATA / "networks")


def _served(entry, kind, carriers=None, countries=None) -> dict[str, Any]:
    result = asyncio.run(AnalyticsService().compute(entry, kind, carriers, countries))
    assert result["execution_mode"] == "precomputed"
    return {k: v for k, v in result.items() if k not in SERVED_ONLY}


def _live(n, kind, carriers=None, countries=None, cost_basis=None) -> dict[str, Any]:
    import gridstorm_analytics

    result = gridstorm_analytics.compute(
        kind, n, carriers=carriers, countries=countries, cost_basis=cost_basis
    )
    return json.loads(json.dumps(result))


def _assert_close(served: Any, live: Any, path: str = "$") -> None:
    if isinstance(served, float) or isinstance(live, float):
        assert isinstance(served, int | float) and isinstance(live, int | float), path
        assert math.isclose(served, live, rel_tol=1e-12, abs_tol=1e-9), (path, served, live)
    elif isinstance(live, dict):
        assert isinstance(served, dict) and set(served) == set(live), path
        for k in live:
            _assert_close(served[k], live[k], f"{path}.{k}")
    elif isinstance(live, list):
        assert isinstance(served, list) and len(served) == len(live), path
        for i, (a, b) in enumerate(zip(served, live, strict=True)):
            _assert_close(a, b, f"{path}[{i}]")
    else:
        assert served == live, (path, served, live)


def _filter_combos(summary: dict[str, Any]) -> list[tuple[list[str] | None, list[str] | None]]:
    carriers, countries = summary["carriers"], summary["countries"]
    combos: list[tuple[list[str] | None, list[str] | None]] = [([c], None) for c in carriers]
    combos.append((carriers[:2], None))
    combos += [(None, [c]) for c in countries]
    if countries:
        combos += [(None, countries[:2]), (carriers[:3], countries[:1])]
    return combos


@pytest.mark.parametrize("network_id", NETWORK_IDS)
def test_precomputed_analytics_match_gridstorm_analytics(catalog, network_id):
    import gridstorm_analytics
    import pypsa

    entry = catalog.get(network_id)
    n = pypsa.Network(str(entry.network_nc))
    index = json.loads((entry.directory / "analytics" / "index.json").read_text())
    assert list(index["kinds"]) == list(gridstorm_analytics.KINDS)
    summary = _served(entry, "summary")
    for kind in index["kinds"]:
        # unfiltered: the committed file is exactly what compute() returns today
        assert _served(entry, kind) == _live(
            n, kind, cost_basis=entry.manifest.get("cost_basis")
        ), f"{network_id}/{kind}: rerun precompute"
        if kind == "summary":
            continue
        for carriers, countries in _filter_combos(summary):
            _assert_close(
                _served(entry, kind, carriers, countries),
                _live(n, kind, carriers, countries, entry.manifest.get("cost_basis")),
            )

    invalid = (("capacity", ["no-such-carrier"], None), ("capacity", None, ["XX"]))
    for kind, carriers, countries in (*invalid, ("summary", ["AC"], None)):
        with pytest.raises(ValueError) as live_err:
            _live(n, kind, carriers, countries)
        with pytest.raises(Unprocessable) as served_err:
            _served(entry, kind, carriers, countries)
        assert served_err.value.message == str(live_err.value)
        assert served_err.value.code == "invalid_analytics_filter"


CHILD = r"""
import json, sys
from pathlib import Path
from fastapi.testclient import TestClient
from gridstorm_api.config import Settings
from gridstorm_api.main import create_app

data, state = Path(sys.argv[1]), Path(sys.argv[2])
statuses = {}
with TestClient(create_app(Settings(data_dir=data, state_dir=state, run_workers=False))) as c:
    for net in json.loads((data / "networks" / "catalog.json").read_text())["networks"]:
        index = json.loads((data / "networks" / net["path"] / "analytics/index.json").read_text())
        for kind in index["kinds"]:
            url = f"/api/v1/networks/{net['id']}/analytics/{kind}"
            statuses[url] = c.get(url).status_code
            statuses[url + "?carriers=AC"] = c.get(url, params={"carriers": "AC"}).status_code
heavy = ("pypsa", "gridstorm_analytics", "linopy", "xarray", "matplotlib")
print(json.dumps({"statuses": statuses, "loaded": [m for m in heavy if m in sys.modules]}))
"""


def test_api_process_never_imports_pypsa(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, str(DATA), str(tmp_path / "state")],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["loaded"] == [], out["loaded"]
    unfiltered = {u: s for u, s in out["statuses"].items() if "?" not in u}
    assert len(unfiltered) == 4 * len(NETWORK_IDS) and set(unfiltered.values()) == {200}
    filtered = {u: s for u, s in out["statuses"].items() if "?" in u}
    assert set(filtered.values()) <= {200, 422}, filtered  # summary rejects filters (422)
