"""Integrity of the committed, real-run simulator-labelled benchmark (when present)."""

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from stormml.datagen import LABEL_NAMES, Dataset
from stormml.splits import leave_network_out_split, operating_point_split

ARTIFACTS = Path(__file__).resolve().parents[3] / "data" / "artifacts" / "stormml"


def test_real_run_artifacts_and_splits():
    if not (ARTIFACTS / "index.json").exists():
        pytest.skip("Benchmark artifacts not generated in this installation")
    index = json.loads((ARTIFACTS / "index.json").read_text())
    for entry in index["artifacts"]:
        doc = json.loads((ARTIFACTS / f"{entry['artifact_id']}.json").read_text())
        canonical = json.dumps(doc["payload"], sort_keys=True, separators=(",", ":"), allow_nan=False)
        assert hashlib.sha256(canonical.encode()).hexdigest() == doc["artifact"]["payload_sha256"]
        assert doc["artifact"]["execution_mode"] == "precomputed"
        assert doc["payload"]["provenance"] == "modeled"
    metadata = json.loads((ARTIFACTS / "ml-screening-dataset.json").read_text())["payload"]
    path = ARTIFACTS / "dataset.npz"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata["dataset_file"]["sha256"]
    ds = Dataset.load(path)
    assert len(ds.X) == metadata["rows"]
    assert np.isfinite(ds.X).all()
    split = operating_point_split(ds.seed, ds.op_id)
    assert len(split.train) and len(split.test)
    for net in np.unique(ds.network):
        held = leave_network_out_split(ds.network, ds.op_id, net)
        assert len(held.train) and len(held.test)
        count = metadata["networks"][net]["n_branch"]
        for op in np.unique(ds.op_id[ds.network == net]):
            np.testing.assert_array_equal(np.sort(ds.branch[ds.op_id == op]), np.arange(count))
    np.testing.assert_array_equal(
        ds.y[:, LABEL_NAMES.index("label")],
        ds.y[:, LABEL_NAMES.index("thermal")] | ds.y[:, LABEL_NAMES.index("voltage")]
        | ds.y[:, LABEL_NAMES.index("nonconv")],
    )
