# ADR 0003 — File-backed Data Observatory (no new SQL tables)

- Status: accepted
- Date: 2026-11-17
- Scope: GridStorm 3.2, TODO G32-03 / G32-04
- Implementation: `services/api/src/gridstorm_api/observatory.py`, `routers/data.py`,
  tests `services/api/tests/test_data_catalog.py`; architecture in
  [backend.md](../architecture/backend.md#data-observatory-catalog-apiv1data)

## Context

GridStorm 3.2 adds a Data Observatory: one browsable catalog of the research data the app uses —
observed/estimated series (ENTSO-E day-ahead load forecast via OPSD, NASA POWER reanalysis), derived
analogue parameters, the five network models and the precomputed research studies — with
provenance, licence, quality checks, bounded series and licence-gated CSV export.

The production stack has Supabase Postgres (jobs, scenarios, comparisons, audit) and Supabase
Storage (generated result payloads). Network models and precomputed artifacts are not in SQL:
they are committed files baked into the API image (`data/networks/`, `data/artifacts/`) and served
read-only with sha256 checks.

The observatory data has the same shape as those files:

- **Small.** About 10–20 catalog entries; the curated bundle is < 3 MB (2.5 MB in the first
  publication, ≈ 260 k values). It loads in well under a second and costs ≈ 3.4 MiB RSS as
  `array` columns, inside the 512 MB Render instance.
- **Immutable per deployment.** It changes only when the publication pipeline republishes, which is
  a reviewed commit with a new `bundle_version`, never at request time. There are no user writes.
- **Integrity-critical.** Values must be served exactly as published, with the licence gate
  applied. A manifest of sha256 checksums verified at load gives an end-to-end guarantee from the
  pipeline output to the HTTP response; rows in a mutable database would need a second mechanism.
- **Already partly file-backed.** Two of the three catalog sources (networks, artifacts) are files.

## Decision

1. Publish non-network datasets as a committed bundle `data/observatory/` (`catalog.json`,
   `series/<id>.csv`, `manifest.json`), baked into the API image exactly like `data/networks/`
   (`.dockerignore` allow-list `!data/observatory/`, `COPY data data`, Render `buildFilter` path
   `data/observatory/**`, so a republished bundle redeploys the API). Raw downloads
   (`data/observed/**`) are not added to the image.
2. The API merges the bundle with one `network_model` entry per network and one
   `precomputed_experiment` entry per study group at runtime; nothing is duplicated.
3. Every bundle file is sha256-verified against `manifest.json` when first loaded. An unverified
   `catalog.json` drops the bundle; a mismatching series file fails only that dataset (503 for its
   series/export). Unverified bytes are never served.
4. **No SQL tables are added** for catalog entries, series or quality reports.

## Consequences

- No migration, RLS policy or backup surface; rollback is a code/data revert (below).
- The catalog is consistent with the deployed code by construction (same image); ETags derive from
  response bodies that embed the bundle version and file checksums.
- Each API process holds its own parsed copy (a few MiB). Fine for one uvicorn process; it would
  multiply with many workers.
- Series queries are in-memory scans over ≤ 3 years of hourly data per request (≤ ~26 k rows per
  series), bounded by the 3-year range limit and `max_points`.
- Adding data requires a pipeline run, review and redeploy — deliberate for licence-gated data.

## When SQL would be warranted

Move the catalog (or parts of it) into Postgres when one of these becomes true:

- the bundle no longer fits comfortably in the image or in memory (order of > 50 MB or > 10 M values),
  or queries need indexes beyond a time-sorted scan;
- datasets are added or corrected without a deployment (user uploads, scheduled ingestion);
- per-user state attaches to datasets (saved views, annotations, access control beyond the
  licence gate);
- several services or SQL clients must query the same series.

Then store bundle versions, entries and checksums in tables (or series in Supabase Storage with
row-level metadata), keep the manifest verification at publication time, and retire the baked bundle.

## Rollback

The feature is additive. To roll back: revert the commits adding `data/observatory/`, the
`/api/v1/data` router and the deploy-path lines (`.dockerignore`, Dockerfile comment,
`render.yaml` `buildFilter`), then redeploy (Render redeploy of the previous commit). No database
migration or data cleanup is involved. Deleting only `data/observatory/` also works: the catalog
then reports `bundle.status = absent` and still lists network and study entries; `/ready` is
unaffected.
