"""Command line: ``gridstorm-advisor advise`` (one crisis) and ``gridstorm-advisor build``
(every preset crisis -> ``data/artifacts/advisor/*.json`` + ``index.json``).

Network resolution (``--network-id``):
- ``pandapower-<case>`` -> pandapower built-in case (``pandapower.networks.<case>()``);
- otherwise the single MATPOWER file ``<networks-dir>/<id>/source/*.m`` (contract layout), or
  ``--matpower-file``, or ``<matpower-dir>/pglib_opf_<case>.m`` derived from a ``pglib-<case>`` id.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from gridstorm_advisor import artifact
from gridstorm_advisor.advisor import AdvisorConfig, advise
from gridstorm_advisor.crisis import Crisis
from gridstorm_advisor.network import (
    AdvisorNetwork,
    find_matpower_source,
    load_matpower,
    load_pandapower_case,
    set_opf_operating_point,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_PRESETS = Path(__file__).resolve().parents[2] / "presets" / "crises.json"


def _pglib_file_name(network_id: str) -> str:
    if not network_id.startswith("pglib-"):
        raise ValueError(f"cannot derive a PGLib file name from {network_id!r}")
    return "pglib_opf_" + network_id.removeprefix("pglib-").replace("-", "_") + ".m"


def resolve_matpower(
    network_id: str,
    *,
    networks_dir: Path,
    matpower_file: Path | None = None,
    matpower_dir: Path | None = None,
) -> Path:
    if matpower_file is not None:
        return matpower_file
    net_dir = networks_dir / network_id
    if (net_dir / "source").is_dir():
        return find_matpower_source(net_dir)
    if matpower_dir is not None:
        path = matpower_dir / _pglib_file_name(network_id)
        if path.is_file():
            return path
    raise FileNotFoundError(
        f"no MATPOWER source for {network_id}: expected {net_dir / 'source'}/*.m "
        "(or pass --matpower-file / --matpower-dir)"
    )


def _git_head(path: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _input_record(path: Path, sha: str) -> dict:
    resolved = path.resolve()
    try:
        rel = Path(os.path.relpath(resolved, REPO_ROOT)).as_posix()
    except ValueError:  # different drive on Windows
        rel = resolved.as_posix()
    rec = {"path": rel, "sha256": sha}
    commit = _git_head(resolved.parent)
    if commit and not rel.startswith(("data/", "workers/")):
        rec["upstream_commit"] = commit
    return rec


def load_network(
    network_id: str,
    *,
    operating_point: str,
    networks_dir: Path,
    matpower_file: Path | None = None,
    matpower_dir: Path | None = None,
) -> tuple[AdvisorNetwork, list[dict]]:
    if network_id.startswith("pandapower-"):
        adv = load_pandapower_case(network_id.removeprefix("pandapower-"))
        inputs: list[dict] = []
    else:
        path = resolve_matpower(
            network_id,
            networks_dir=networks_dir,
            matpower_file=matpower_file,
            matpower_dir=matpower_dir,
        )
        adv = load_matpower(path, network_id)
        inputs = [_input_record(path, adv.source_files[0]["sha256"])]
    if operating_point == "opf":
        set_opf_operating_point(adv)
    elif operating_point != "case":
        raise ValueError(f"unknown operating point {operating_point!r} (case|opf)")
    return adv, inputs


def _crisis_from_file(path: Path) -> Crisis:
    data = json.loads(path.read_text(encoding="utf-8"))
    if str(data.get("schema_version", "")).startswith("stormspec/"):
        return Crisis.from_stormspec(data)
    return Crisis.from_dict(data)


def _network_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--networks-dir", type=Path, default=REPO_ROOT / "data" / "networks")
    p.add_argument("--matpower-file", type=Path, default=None)
    p.add_argument(
        "--matpower-dir",
        type=Path,
        default=None,
        help="directory with pglib_opf_*.m files (fallback when data/networks lacks the network)",
    )


def cmd_advise(args: argparse.Namespace) -> int:
    adv, inputs = load_network(
        args.network_id,
        operating_point=args.operating_point,
        networks_dir=args.networks_dir,
        matpower_file=args.matpower_file,
        matpower_dir=args.matpower_dir,
    )
    crisis = _crisis_from_file(args.crisis)
    t0 = time.perf_counter()
    payload = advise(adv, crisis, AdvisorConfig(voll_eur_per_mwh=args.voll))
    print(
        f"advisor finished in {time.perf_counter() - t0:.1f} s: {payload['outcome']}",
        file=sys.stderr,
    )
    out = json.dumps(payload, indent=1, ensure_ascii=False, allow_nan=False)
    if args.out:
        args.out.write_text(out + "\n", encoding="utf-8", newline="\n")
    else:
        print(out)
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    presets = json.loads(args.presets.read_text(encoding="utf-8"))
    runs = presets["runs"]
    if args.only:
        runs = [r for r in runs if r["artifact_id"] in set(args.only)]
    command = " ".join([args.command_prefix, *(shlex.quote(a) for a in args.argv)])
    cache: dict[tuple[str, str], tuple[AdvisorNetwork, list[dict]]] = {}
    for run in runs:
        key = (run["network_id"], run.get("operating_point", "case"))
        if key not in cache:
            cache[key] = load_network(
                key[0],
                operating_point=key[1],
                networks_dir=args.networks_dir,
                matpower_dir=args.matpower_dir,
            )
        adv, inputs = cache[key]
        crisis = Crisis.from_dict(run["crisis"])
        t0 = time.perf_counter()
        payload = advise(adv, crisis, AdvisorConfig(voll_eur_per_mwh=args.voll))
        wall = time.perf_counter() - t0
        payload["title"] = run["title"]
        art = artifact.envelope(
            run["artifact_id"],
            adv.network_id,
            payload,
            command=command,
            inputs=inputs
            + [
                {
                    "path": Path(os.path.relpath(args.presets.resolve(), REPO_ROOT)).as_posix(),
                    "sha256": artifact.sha256_file(args.presets),
                }
            ],
        )
        art["artifact"]["wall_time_s"] = round(wall, 1)
        path = artifact.write_artifact(args.out_dir, art)
        counts = payload.get("counts", {})
        print(
            f"{run['artifact_id']}: {payload['outcome']} "
            f"(evaluated {counts.get('candidates_evaluated', 0)}, "
            f"accepted {counts.get('accepted', 0)}) in {wall:.1f} s -> {path}"
        )
    artifact.write_index(args.out_dir)
    return 0


def main(argv: list[str] | None = None, *, build_command: str | None = None) -> int:
    """``build_command`` overrides the command recorded in build artifacts (used by
    ``scripts/build_artifacts.py``)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="gridstorm-advisor", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    pa = sub.add_parser("advise", help="run the advisor for one crisis")
    pa.add_argument("--network-id", required=True)
    pa.add_argument(
        "--crisis",
        type=Path,
        required=True,
        help="crisis JSON ({id, line_outages, generator_outages, demand_multiplier}) "
        "or a stormspec/1.0 scenario JSON",
    )
    pa.add_argument("--operating-point", choices=("case", "opf"), default="case")
    pa.add_argument("--voll", type=float, default=10000.0)
    pa.add_argument("--out", type=Path, default=None)
    _network_args(pa)
    pa.set_defaults(func=cmd_advise)

    pb = sub.add_parser("build", help="regenerate data/artifacts/advisor from the presets")
    pb.add_argument("--presets", type=Path, default=DEFAULT_PRESETS)
    pb.add_argument("--out-dir", type=Path, default=REPO_ROOT / "data" / "artifacts" / "advisor")
    pb.add_argument("--only", nargs="*", default=None, help="artifact ids to rebuild")
    pb.add_argument("--voll", type=float, default=10000.0)
    _network_args(pb)
    pb.set_defaults(
        func=cmd_build,
        argv=argv[1:],
        command_prefix=build_command or "uv run gridstorm-advisor build",
    )

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
