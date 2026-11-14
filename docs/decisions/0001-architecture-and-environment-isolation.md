# ADR 0001 — Architecture, engine isolation and deployment split

- Status: accepted
- Date: 2026-11-14

## Context

GridStorm must combine PyPSA (optimisation), pandapower (AC power flow / N-1) and Grid2Op
(sequential operation), expose them through a web UI on Vercel and an API on Render's free tier,
and keep results reproducible and honest.

Verified on PyPI (2026-11-14): `pypsa 1.4.0` (Python ≥ 3.11), `linopy 0.10.1`, `pandas 3.1.1`,
`pandapower 3.5.6`, `grid2op 1.12.6`, `highspy 1.16.0`. The brief records that PyPSA 1.4 requires
pandas 3 while pandapower 3.5.6 and Grid2Op 1.12.6 pin pandas < 3; the Forensics audit
(`docs/research/compatibility-matrix.md`) re-verifies this with resolver output.

## Decision

1. **Monorepo, multiple isolated Python environments** (one `uv` project + lock per component).
   Shared packages (`stormspec`, `canonical_grid`) depend only on pydantic so every env can use them.
2. **Artifact contracts between engines** (`docs/architecture/contracts.md`): NetCDF networks,
   canonical JSON, result JSON, artifact envelopes with SHA-256.
3. **API process runs only the PyPSA engine live** (subprocess per job, timeout + memory limit,
   bounded concurrency). pandapower, advisor, Grid2Op and StormBench studies run offline and are
   published as labelled precomputed artifacts. Rationale: Render free instances have 512 MB RAM,
   shared CPU and ephemeral disk; loading three scientific stacks in one process is neither
   compatible nor affordable.
4. **React + Vite SPA** for the public UI (no SSR requirement; static hosting on Vercel). PyPSA
   Explorer's Dash UI is not ported wholesale; its analytics are ported into `gridstorm_analytics`
   with attribution and served via the API.
5. **Persistence:** Postgres (Supabase) for metadata, jobs, metrics, scenarios and audit events,
   with RLS for user-owned rows; large payloads go to a content-addressed ArtifactStore
   (local FS, or S3-compatible such as Cloudflare R2). SQLite is supported for local development
   and tests only.

## Consequences

- Cross-engine claims (e.g. PyPSA DC flows ≈ pandapower DC flows on the same case) need explicit
  numerical tests that run two environments and compare artifacts.
- The public demo remains useful without heavy compute (precomputed, labelled artifacts).
- More lockfiles to maintain; CI runs one job per environment.
