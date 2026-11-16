# Data Observatory pipeline: produce, verify, publish, roll back

Status: 2026-11-17, GridStorm 3.2 (TODO G32-03). Code: `pipelines/observed/`
(`gridstorm_observed.licence`, `.bundle`, `.power_hourly`, `.publish`;
`scripts/publish_observatory.py`). Sources and licences:
[sources-and-licensing.md](sources-and-licensing.md).

## 1. What the bundle is

`data/observatory/` is a small, committed, licence-gated bundle (target < 3 MB; bundle
`2026-11-17.1` is 2 490 754 bytes) that the API bakes into its image, like `data/networks/`.
The API merges it with one `network_model` entry per network and one `precomputed_experiment`
entry per study group; those two categories are never in the bundle.

```
data/observatory/
  .gitattributes   "* -text": git never rewrites line endings (bytes are sha256-pinned)
  catalog.json     {"schema_version": "gridstorm-observatory/1.0", "bundle_version", "entries": [DatasetEntry]}
  series/<id>.csv  wide CSV: utc,<series_id>,...; utc = YYYY-MM-DDTHH:MM:SSZ (hour start), strictly increasing
  manifest.json    pipeline + version + command, source checksums, licence-gate records,
                   files[{path, sha256, bytes}] for every file except itself, total_bytes
```

Conventions: empty CSV cell = missing (never 0); fixed decimals per series with trailing zeros
removed; LF, UTF-8; JSON with sorted keys and 2-space indent; `temporal.end_utc` and
`windows[].end_utc` are **inclusive** (last covered hour start). Nothing reads the clock: the only
times in the bundle are recorded source retrieval times. Rows that were never requested (NASA
POWER between 2015-01-23 and 2017-01-01) are absent, which means "not covered", not "missing".

| Entry | Category / provenance | Series | Rows |
|---|---|---|---|
| `opsd-de-load-forecast` | historical_demand / estimated | `de_load_forecast` (MW) | 50 400 (24 missing) |
| `nasa-power-de-weather` | weather_reanalysis / modeled | `<city>_t2m`, `<city>_ws10m` × 4 | 8 928 |
| `nasa-power-de-renewable-resource` | renewable_resource / modeled | `<city>_ws50m`, `<city>_ghi` × 4 | 8 928 |
| `opsd-de-derived-multipliers` | derived_research / modeled | one hour-of-day demand multiplier column per stress day, on the SciGRID-DE model day 2011-01-01 | 24 |
| `observed-analogue-scenarios` | synthetic_scenario_input / modeled | metadata only; `use_in_scenario` → precomputed Studio preset `observed-dunkelflaute-2015-01-20` | — |

## 2. Licence gate

`licence.gate(source_key)` returns the licence record of an allow-listed source key
(`opsd:DE_load_forecast_entsoe_transparency`, `nasa-power:{T2M,WS10M,WS50M,ALLSKY_SFC_SW_DWN}`,
`gridstorm-derived:demand_multipliers`) and raises for anything else. Restricted keys
(`*load_actual*`, `*generation_actual*`, `*capacity*`, the renewable daily multipliers and the exact
non-open OPSD column names) are refused first, even if added to the allow-list. Every entry builder
calls the gate; the build also scans every output file for restricted column names, and records
`licence_gate[dataset][series] = {source_key, licence_id, redistribution}` in the manifest so
`--verify` can re-run the gate. Only `redistribution: permitted` series are written;
`exportable` is true exactly when redistribution is permitted.

## 3. Produce

```bash
cd pipelines/observed
uv sync --locked
# First time / new NASA request set: fetch missing POWER responses (sequential, 1.5 s pause) and
# rewrite data/observed/nasa-power-de/power-hourly-requests.json
uv run --locked python scripts/publish_observatory.py --out ../../data/observatory --fetch-nasa
# Normal rebuild (all sources from the cache)
uv run --locked python scripts/publish_observatory.py --out ../../data/observatory \
    --opsd-csv "$GRIDSTORM_DATA_CACHE/opsd/time_series_60min_singleindex.csv"
```

Inputs:

- **OPSD CSV** (130 MB, outside the repo): `--opsd-csv`, default
  `<cache>/opsd/time_series_60min_singleindex.csv` (`<cache>` = `$GRIDSTORM_DATA_CACHE` or
  `<repo>/../upstream/_data_cache`). Its sha256 must equal both `sources.OPSD_CSV_SHA256` and
  `data/observed/opsd-de/manifest.json` `source.sha256`. Only `utc_timestamp`,
  `cet_cest_timestamp` and the forecast column are read.
- **NASA POWER responses**: `<cache>/nasa-power/` (raw JSON, outside the repo), pinned by the
  committed request record (URL, response sha256 and bytes, API version, header sources, fill
  counts, `values_sha256` of the canonical values, `retrieved_at`). The record is the only place
  retrieval times come from.
- **Committed inputs**: `data/observed/opsd-de/{derived-multipliers.json,manifest.json}`,
  `data/observed/analogue-results.json`, `data/scenarios/observed/*.yaml`,
  `packages/stormspec/presets/observed-*.yaml` (must be byte-identical to the scenario YAMLs;
  the build fails otherwise), `data/observed/nasa-power-de/t2m_ws10m_hourly.csv` (cross-check).

A source that is not available is **carried forward**: the previous bundle's CSV for that entry is
read back (its sha256 must match the previous manifest) and re-checked: NASA values must hash to the
request record's `values_sha256`; OPSD source-only checks (`source_*`, `dst_free_utc`,
`coverage_trim`) are copied, all table checks recomputed. The command prints which entries were
re-derived from source and which were carried forward. After writing, the script runs `--verify`.

Change the bundle version (`publish.BUNDLE_VERSION`, or `--bundle-version YYYY-MM-DD.N`) whenever
the published content changes.

## 4. Verify

```bash
cd pipelines/observed
uv run --locked pytest -q                                      # 92 tests (38 existing + 54 observatory)
uv run --locked python scripts/publish_observatory.py --out ../../data/observatory --verify
```

`--verify` fails (exit 1) unless:

1. every file in the bundle (dotfiles excepted) is listed in `manifest.json` and matches its
   sha256 and size, and `total_bytes` is consistent;
2. `catalog.json` has the schema version, unique ids, and every entry passes the DatasetEntry
   schema (`bundle.validate_entry`: all keys present, vocabularies, UTC formats, exportable ⇔
   permitted, artifact path/hash/rows);
3. each CSV parses strictly (header = entry series ids, strictly increasing `...Z` timestamps,
   finite numbers or empty);
4. every published series has a licence-gate record that still passes `licence.gate`, and no file
   names a restricted column;
5. a rebuild from the available inputs (carrying forward what is missing) is **byte-identical** to
   the bundle, including `catalog.json` and `manifest.json`.

What the offline check (no caches) does and does not prove: the derived-multiplier and analogue
entries are always re-derived from committed files; NASA values are tied to the recorded responses
through `values_sha256`; the OPSD forecast values can only be re-derived with the OPSD CSV, so
without it a consistently re-signed edit of `opsd-de-load-forecast.csv` is not detectable. CI
therefore restores or downloads the sha256-pinned CSV (below).

`tests/test_observatory.py` covers the gate (allow-list, forged allow-list, unknown keys, build
refusal), the reconstruction test (with the OPSD cache: published forecast = source forecast; an
oracle affine fit to actual load still misses by > 1 GW RMS, by > 500 MW in most hours and on each
stress day), determinism (two builds byte-identical and equal to the committed bundle; from raw
sources when cached), manifest coverage, quality maths (missing kept null, completeness, gaps),
UTC parsing (offset/local forms rejected, DST fixture), and tamper detection (unsigned byte edit,
re-signed NASA/derived/metadata edits, restricted series, unlisted file, preset drift, re-signed
forecast edit with the source).

## 5. CI and publication

- `.github/workflows/observatory.yml` runs on pull requests and pushes to `main` that touch
  `pipelines/observed/**`, `data/observed/**`, `data/observatory/**`, `data/scenarios/observed/**`
  or `packages/stormspec/presets/observed-*.yaml`: `uv sync --locked`, restore the OPSD CSV from
  the Actions cache (key `opsd-time-series-2020-10-06-6a7f2bc5`) or download it and check its
  sha256 (optional step: if OPSD is unreachable the forecast is checksum-verified only and a
  warning is emitted), `pytest -q`, then `--verify`. The general CI (`ci.yml`) also runs the
  component's ruff and tests.
- **Publication = merge.** The bundle is committed. The API image copies `data/observatory/`, and
  Render's build filter includes `data/observatory/**` (owned by the API configuration in
  `render.yaml`), so merging a bundle change to `main` triggers the API redeploy; a change elsewhere
  in this pipeline without a bundle change does not. At startup the API re-hashes every file
  against `manifest.json` and serves a dataset's series only if it verifies (503 otherwise).
- After deploy: `GET /api/v1/data/catalog` lists the five bundle entries plus the composed network
  and experiment entries; spot-check `/api/v1/data/catalog/opsd-de-load-forecast/series`.

## 6. Roll back

The bundle is plain committed files, so a rollback is a revert:

1. `git revert <commit>` of the bundle change (or restore `data/observatory/` from the previous
   release tag) — never edit files in place, because the manifest pins every byte;
2. run `--verify` locally (it must pass for the restored bundle) and merge; Render redeploys via
   the same build filter;
3. if only the API must be rolled back immediately, redeploy the previous Render deploy; the
   bundle travels inside the image, so the old image serves the old bundle.

If a source turns out to be non-redistributable, remove its key from `licence.ALLOWED`: the build
(and `--verify`) then fails with a `LicenceError` until that entry's builder is removed from
`publish.build_bundle`; republish, and document the decision in
[sources-and-licensing.md](sources-and-licensing.md).
