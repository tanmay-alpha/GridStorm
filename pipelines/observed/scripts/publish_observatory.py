"""Publish or verify the Data Observatory bundle (``data/observatory/``).

Run from ``pipelines/observed``::

    uv run --locked python scripts/publish_observatory.py --out ../../data/observatory \
        [--opsd-csv PATH] [--power-cache DIR] [--fetch-nasa]
    uv run --locked python scripts/publish_observatory.py --out ../../data/observatory --verify

``--opsd-csv`` defaults to ``<cache>/opsd/time_series_60min_singleindex.csv`` and
``--power-cache`` to ``<cache>/nasa-power`` (``<cache>`` = ``$GRIDSTORM_DATA_CACHE`` or
``<repo>/../upstream/_data_cache``). A missing source is not an error: that entry's series is
carried forward from the existing bundle and re-checked. ``--fetch-nasa`` downloads the POWER
responses that are not cached yet (hourly windows and the yearly requests behind the daily means;
sequentially, with a pause) and rewrites both committed request records. ``--verify`` re-hashes
the bundle, validates every entry, re-runs the licence gate and
re-derives the bundle from the available inputs, requiring byte equality; exit status 1 on any
error.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from gridstorm_observed import bundle, power_daily, power_hourly, publish, sources


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--out", type=Path, required=True, help="bundle directory")
    ap.add_argument("--opsd-csv", type=Path, default=None)
    ap.add_argument("--power-cache", type=Path, default=None)
    ap.add_argument("--fetch-nasa", action="store_true", help="fetch missing POWER responses")
    ap.add_argument("--verify", action="store_true", help="verify the bundle in --out")
    ap.add_argument("--bundle-version", default=publish.BUNDLE_VERSION)
    args = ap.parse_args(argv)

    opsd_csv = args.opsd_csv or sources.cache_dir() / "opsd" / sources.OPSD_CSV_NAME
    power_cache = args.power_cache or power_hourly.default_cache()
    out = args.out.resolve()
    inputs = publish.Inputs(
        opsd_csv=opsd_csv if opsd_csv.exists() else None,
        power_cache=power_cache,
        previous=out if (out / "catalog.json").exists() else None,
        bundle_version=args.bundle_version,
    )

    if args.verify:
        errors, notes = publish.verify(out, inputs)
        for n in notes:
            print(f"note: {n}")
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        if errors:
            print(f"verify FAILED: {len(errors)} error(s)", file=sys.stderr)
            return 1
        manifest = (out / "manifest.json").read_bytes()
        total = sum(p.stat().st_size for p in out.rglob("*") if p.is_file())
        print(
            f"verify OK: {out} ({total} bytes on disk, manifest sha256 {bundle.sha256(manifest)})"
        )
        return 0

    if args.fetch_nasa:
        record = power_hourly.fetch(power_cache)
        power_hourly.RECORD_PATH.write_bytes(bundle.dump_json(record))
        print(f"POWER request record written: {power_hourly.RECORD_PATH}")
        daily = power_daily.fetch(power_cache)
        power_daily.RECORD_PATH.write_bytes(bundle.dump_json(daily))
        print(f"POWER daily-means request record written: {power_daily.RECORD_PATH}")

    result = publish.build_bundle(inputs)
    publish.write_bundle(out, result.files)
    for n in result.notes:
        print(f"note: {n}")
    total = sum(len(d) for d in result.files.values())
    print(f"bundle written: {out} ({len(result.files)} files, {total} bytes)")
    errors, _ = publish.verify(out, inputs)
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
