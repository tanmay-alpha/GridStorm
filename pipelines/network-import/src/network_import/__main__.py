"""CLI: ``uv run python -m network_import <id> | all | validate [ids] | from-netcdf ...``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def _all_ids() -> list[str]:
    from network_import.examples import EXAMPLES
    from network_import.pglib_import import PGLIB_CASES

    return [*EXAMPLES, *PGLIB_CASES]


def import_one(network_id: str, *, catalog: bool = True) -> None:
    from network_import.examples import EXAMPLES, import_example
    from network_import.pglib_import import PGLIB_CASES, import_pglib

    if network_id in EXAMPLES:
        import_example(network_id, catalog=catalog)
    elif network_id in PGLIB_CASES:
        import_pglib(network_id, catalog=catalog)
    else:
        raise SystemExit(f"unknown network id {network_id!r}; known: {', '.join(_all_ids())}")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "validate":
        p = argparse.ArgumentParser(prog="network_import validate")
        p.add_argument("ids", nargs="*", help="network ids (default: every catalog entry)")
        p.add_argument("--no-powerflow", action="store_true", help="skip the PGLib DC round trip")
        a = p.parse_args(argv[1:])
        from network_import.validate import validate_all

        reports = validate_all(a.ids or None, powerflow=not a.no_powerflow)
        print(json.dumps(reports, indent=2))
        return 1 if any(r["errors"] for r in reports) else 0
    if argv and argv[0] == "from-netcdf":
        p = argparse.ArgumentParser(prog="network_import from-netcdf")
        p.add_argument("network_id")
        p.add_argument("path", type=Path)
        p.add_argument("--name", required=True)
        p.add_argument("--description", default="")
        p.add_argument("--source-url", required=True)
        p.add_argument("--source-version", default="unspecified")
        p.add_argument("--upstream-commit", default=None)
        p.add_argument("--license", required=True, help="SPDX id")
        p.add_argument("--license-url", required=True)
        p.add_argument("--attribution", required=True)
        p.add_argument(
            "--redistribution", choices=["permitted", "restricted", "unknown"], default="unknown"
        )
        p.add_argument("--geographic", default="")
        p.add_argument("--temporal", default="")
        p.add_argument(
            "--provenance-class",
            default="modeled",
            choices=["observed", "estimated", "synthetic", "modeled"],
        )
        p.add_argument(
            "--schematic", action="store_true", help="bus x/y are layout coordinates (crs null)"
        )
        p.add_argument("--quality-flag", action="append", default=[])
        p.add_argument("--assumption", action="append", default=[])
        p.add_argument(
            "--field-provenance",
            action="append",
            default=[],
            metavar="COMPONENT.FIELD=CLASS",
            help="e.g. buses.x=observed (repeatable)",
        )
        p.add_argument("--retrieved-at", default=None, help="ISO-8601 retrieval timestamp")
        p.add_argument("--null-field", action="append", default=[])
        a = p.parse_args(argv[1:])
        from network_import.from_netcdf import import_netcdf

        import_netcdf(a)
        return 0
    p = argparse.ArgumentParser(
        prog="network_import", description="Import GridStorm networks into data/networks/."
    )
    p.add_argument("target", help="network id or 'all' (also: validate, from-netcdf)")
    a = p.parse_args(argv)
    ids = _all_ids() if a.target == "all" else [a.target]
    for nid in ids:
        print(f"importing {nid} ...", flush=True)
        import_one(nid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
