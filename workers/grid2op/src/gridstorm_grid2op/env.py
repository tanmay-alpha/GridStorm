"""Grid2Op environment construction, dataset provenance and grid layout extraction."""

from __future__ import annotations

import hashlib
import platform
from importlib import metadata
from pathlib import Path
from typing import Any

import grid2op

#: Supported Grid2Op environment (dataset) and the GridStorm network id it maps to.
ENV_NAME = "l2rpn_case14_sandbox"
NETWORK_ID = "l2rpn-case14-sandbox"

#: Upstream distribution facts for the dataset (from grid2op-datasets/datasets.json).
DATASET_SOURCE = {
    "index_url": "https://github.com/Grid2Op/grid2op-datasets/blob/master/datasets.json",
    "url": "https://huggingface.co/datasets/grid2op/l2rpn-datasets/resolve/main/"
    "l2rpn_case14_sandbox.tar.bz2",
    "archive_sha256_published": "1c3b2d73bcfda03c2fc0e977e16e695f303e856752d8b280443accb7248b5827",
}

BACKENDS = ("lightsim2grid", "pandapower")


def _version(dist: str) -> str | None:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return None


def make_backend(name: str | None):
    """Return a Grid2Op backend instance. ``None`` selects lightsim2grid."""
    name = name or "lightsim2grid"
    if name == "lightsim2grid":
        from lightsim2grid import LightSimBackend

        return LightSimBackend()
    if name == "pandapower":
        from grid2op.Backend import PandaPowerBackend

        return PandaPowerBackend()
    raise ValueError(f"unknown backend {name!r}; expected one of {BACKENDS}")


def make_env(backend: str | None = None, env_name: str = ENV_NAME):
    """Create the Grid2Op environment (downloads the dataset to ~/data_grid2op on first use).

    The dataset is never stored inside the GridStorm repository.
    """
    return grid2op.make(env_name, backend=make_backend(backend))


def dataset_dir_sha256(path: str | Path) -> tuple[str, int]:
    """sha256 over (relative path, file sha256) of every file in the extracted dataset directory.

    Returns ``(digest, n_files)``. Deterministic: files are visited in sorted order.
    """
    root = Path(path)
    h = hashlib.sha256()
    n = 0
    for f in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = f.relative_to(root).as_posix()
        if "__pycache__" in rel or rel.endswith(".pyc"):
            continue
        fh = hashlib.sha256(f.read_bytes()).hexdigest()
        h.update(f"{rel}\0{fh}\n".encode())
        n += 1
    return h.hexdigest(), n


def env_info(env, backend: str | None) -> dict[str, Any]:
    """Versions, parameters and dataset provenance of an environment (JSON-compatible)."""
    params = env.parameters
    path = Path(env.get_path_env())
    digest, n_files = dataset_dir_sha256(path)
    return {
        "name": env.env_name,
        "network_id": NETWORK_ID,
        "grid2op_version": grid2op.__version__,
        "backend": backend or "lightsim2grid",
        "backend_version": _version(
            "lightsim2grid" if (backend or "lightsim2grid") == "lightsim2grid" else "pandapower"
        ),
        "pandapower_version": _version("pandapower"),
        "reward_class": type(env.get_reward_instance()).__name__,
        "delta_time_min": float(env.delta_time_seconds) / 60.0,
        "n_line": int(env.n_line),
        "n_sub": int(env.n_sub),
        "n_gen": int(env.n_gen),
        "n_load": int(env.n_load),
        "parameters": {
            "NB_TIMESTEP_OVERFLOW_ALLOWED": int(params.NB_TIMESTEP_OVERFLOW_ALLOWED),
            "HARD_OVERFLOW_THRESHOLD": float(params.HARD_OVERFLOW_THRESHOLD),
            "NO_OVERFLOW_DISCONNECTION": bool(params.NO_OVERFLOW_DISCONNECTION),
            "NB_TIMESTEP_RECONNECTION": int(params.NB_TIMESTEP_RECONNECTION),
            "NB_TIMESTEP_COOLDOWN_LINE": int(params.NB_TIMESTEP_COOLDOWN_LINE),
            "NB_TIMESTEP_COOLDOWN_SUB": int(params.NB_TIMESTEP_COOLDOWN_SUB),
            "MAX_LINE_STATUS_CHANGED": int(params.MAX_LINE_STATUS_CHANGED),
            "MAX_SUB_CHANGED": int(params.MAX_SUB_CHANGED),
        },
        "dataset": {
            **DATASET_SOURCE,
            "extracted_dir_sha256": digest,
            "extracted_files": n_files,
            "license": DATASET_LICENSE,
            "provenance_class": "synthetic",
        },
        "platform": f"{platform.system()} {platform.release()} / Python {platform.python_version()}",
    }


DATASET_LICENSE = {
    "spdx": "MPL-2.0",
    "url": "https://github.com/Grid2op/grid2op-datasets/blob/master/LICENSE",
    "note": "The Grid2op/grid2op-datasets repository (which indexes and distributes "
    "l2rpn_case14_sandbox; archive hosted on huggingface.co/datasets/grid2op/l2rpn-datasets) is "
    "licensed MPL-2.0; the Hugging Face dataset card declares no licence. GridStorm does NOT "
    "redistribute the dataset; only small derived episode traces are committed.",
}


def grid_layout(env) -> dict[str, Any]:
    """Schematic layout for the frontend: substations with (x, y) layout coordinates, lines,
    generators and loads with the substation they connect to. Coordinates come from the
    environment's ``grid_layout.json`` and are NOT geographic."""
    layout = env.grid_layout or {}
    subs = []
    for i, name in enumerate(env.name_sub):
        xy = layout.get(str(name))
        subs.append(
            {
                "id": str(name),
                "index": i,
                "x": float(xy[0]) if xy is not None else None,
                "y": float(xy[1]) if xy is not None else None,
            }
        )
    thermal = env.get_thermal_limit()
    lines = [
        {
            "id": str(name),
            "index": i,
            "sub_or": str(env.name_sub[env.line_or_to_subid[i]]),
            "sub_ex": str(env.name_sub[env.line_ex_to_subid[i]]),
            "thermal_limit_a": round(float(thermal[i]), 4),
        }
        for i, name in enumerate(env.name_line)
    ]
    gens = [
        {
            "id": str(name),
            "sub": str(env.name_sub[env.gen_to_subid[i]]),
            "type": str(env.gen_type[i]),
            "pmax_mw": round(float(env.gen_pmax[i]), 4),
            "redispatchable": bool(env.gen_redispatchable[i]),
        }
        for i, name in enumerate(env.name_gen)
    ]
    loads = [
        {"id": str(name), "sub": str(env.name_sub[env.load_to_subid[i]])}
        for i, name in enumerate(env.name_load)
    ]
    return {
        "coordinate_kind": "schematic",
        "coordinate_note": "Schematic layout from the Grid2Op environment's grid_layout.json — "
        "not geographic",
        "substations": subs,
        "lines": lines,
        "generators": gens,
        "loads": loads,
    }
