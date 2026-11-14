#!/usr/bin/env python3
"""Compare regenerated GridStorm artifacts against committed references.

Walks two JSON documents (or two directories of ``*.json`` files) in parallel and
checks that every numeric leaf agrees within ``rel_tol``/``abs_tol``
(``|a-b| <= max(abs_tol, rel_tol*max(|a|,|b|))``). Strings/bools/null must match
exactly; structural differences (missing keys, list length) are failures.

Volatile fields are ignored by key name anywhere in the tree (timestamps, platform,
host, durations, versions of the runtime, git sha). Extend with ``--ignore KEY``.

Exit codes: 0 = match, 1 = mismatch, 2 = usage / missing-file error.
Standard library only, so it runs under any Python >= 3.11.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

DEFAULT_IGNORE = frozenset(
    {
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
        "retrieved_at",
        "generated_at",
        "timestamp",
        "platform",
        "hostname",
        "host",
        "python_version",
        "git_sha",
        "duration_s",
        "duration_ms",
        "elapsed_s",
        "elapsed_ms",
        "runtime_s",
        "wall_time_s",
        "solve_time_s",
        "solver_time_s",
    }
)


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def compare(
    ref: Any,
    new: Any,
    *,
    rel_tol: float,
    abs_tol: float,
    ignore: frozenset[str],
    ignore_suffixes: tuple[str, ...] = (),
    path: str = "$",
) -> Iterator[str]:
    """Yield human-readable mismatch descriptions (empty iterator = equal)."""
    if _is_number(ref) and _is_number(new):
        a, b = float(ref), float(new)
        if math.isnan(a) and math.isnan(b):
            return
        if math.isinf(a) or math.isinf(b):
            if a != b:
                yield f"{path}: {ref!r} != {new!r}"
            return
        tol = max(abs_tol, rel_tol * max(abs(a), abs(b)))
        if abs(a - b) > tol:
            yield f"{path}: ref={ref!r} new={new!r} |diff|={abs(a - b):.6g} > tol={tol:.6g}"
        return
    if type(ref) is not type(new):
        yield f"{path}: type {type(ref).__name__} != {type(new).__name__}"
        return
    if isinstance(ref, dict):
        keys = {
            k
            for k in set(ref) | set(new)
            if k not in ignore and not (isinstance(k, str) and k.endswith(ignore_suffixes))
        }
        for k in sorted(keys, key=str):
            if k not in ref:
                yield f"{path}.{k}: missing in reference"
            elif k not in new:
                yield f"{path}.{k}: missing in regenerated"
            else:
                yield from compare(
                    ref[k],
                    new[k],
                    rel_tol=rel_tol,
                    abs_tol=abs_tol,
                    ignore=ignore,
                    ignore_suffixes=ignore_suffixes,
                    path=f"{path}.{k}",
                )
        return
    if isinstance(ref, list):
        if len(ref) != len(new):
            yield f"{path}: list length {len(ref)} != {len(new)}"
            return
        for i, (r, n) in enumerate(zip(ref, new, strict=True)):
            yield from compare(
                r,
                n,
                rel_tol=rel_tol,
                abs_tol=abs_tol,
                ignore=ignore,
                ignore_suffixes=ignore_suffixes,
                path=f"{path}[{i}]",
            )
        return
    if ref != new:
        yield f"{path}: {ref!r} != {new!r}"


def _pairs(ref: Path, new: Path) -> list[tuple[Path, Path | None]]:
    if ref.is_file():
        return [(ref, new if new.is_file() else None)]
    out: list[tuple[Path, Path | None]] = []
    for r in sorted(ref.rglob("*.json")):
        n = new / r.relative_to(ref)
        out.append((r, n if n.is_file() else None))
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("reference", type=Path, help="committed artifact file or directory")
    p.add_argument("regenerated", type=Path, help="regenerated artifact file or directory")
    p.add_argument("--rel-tol", type=float, default=1e-4)
    p.add_argument("--abs-tol", type=float, default=1e-6)
    p.add_argument("--ignore", action="append", default=[], help="extra key name to ignore")
    p.add_argument(
        "--ignore-suffix",
        action="append",
        default=[],
        help="ignore keys ending with this suffix (e.g. _s for runtimes)",
    )
    p.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="skip reference files with this name (e.g. index.json for subset runs)",
    )
    p.add_argument(
        "--allow-missing",
        action="store_true",
        help="reference files with no regenerated counterpart are reported, not failed",
    )
    p.add_argument("--max-report", type=int, default=50, help="mismatch lines per file")
    args = p.parse_args(argv)

    if not args.reference.exists():
        print(f"error: reference {args.reference} does not exist", file=sys.stderr)
        return 2
    if not args.regenerated.exists():
        print(f"error: regenerated {args.regenerated} does not exist", file=sys.stderr)
        return 2

    ignore = DEFAULT_IGNORE | frozenset(args.ignore)
    pairs = [
        (r, n) for r, n in _pairs(args.reference, args.regenerated) if r.name not in args.exclude
    ]
    if not pairs:
        print(f"error: no *.json files under {args.reference}", file=sys.stderr)
        return 2

    failed = missing = 0
    for ref, new in pairs:
        if new is None:
            missing += 1
            status = "MISSING" if not args.allow_missing else "missing (allowed)"
            print(f"[{status}] {ref}")
            failed += 0 if args.allow_missing else 1
            continue
        diffs = list(
            compare(
                json.loads(ref.read_text(encoding="utf-8")),
                json.loads(new.read_text(encoding="utf-8")),
                rel_tol=args.rel_tol,
                abs_tol=args.abs_tol,
                ignore=ignore,
                ignore_suffixes=tuple(args.ignore_suffix),
            )
        )
        if diffs:
            failed += 1
            print(f"[FAIL] {ref} ({len(diffs)} mismatches)")
            for d in diffs[: args.max_report]:
                print(f"    {d}")
        else:
            print(f"[ok]   {ref}")
    compared = len(pairs) - missing
    print(
        f"{compared - (failed - (0 if args.allow_missing else missing))}/{compared} compared "
        f"artifact files match, {missing} reference file(s) not regenerated "
        f"(rel_tol={args.rel_tol}, abs_tol={args.abs_tol})"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
