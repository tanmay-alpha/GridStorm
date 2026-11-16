# GridStorm documentation

GridStorm is a power-grid resilience and crisis-simulation research platform. It is a research and
teaching tool — not a live control system and not a validated blackout predictor.

## Start here

| Document | For |
|---|---|
| [User guide](user-guide.md) | Using the web app: pages (incl. the Data Observatory), metrics with units and formulas, execution modes, limitations |
| [Glossary](glossary.md) | Power-system and data terms used in the UI (LOPF, PTDF, LODF, N-1, VOLL, EENS, LOLP, rho, tie group, reanalysis, licence gate, …) |
| [Engineering story](engineering-story.md) | Architecture and the hard problems, with file references |

## Architecture

| Document | Content |
|---|---|
| [architecture/overview.md](architecture/overview.md) | Components, principles, deployment split, file-backed data |
| [architecture/backend.md](architecture/backend.md) | API internals: reference data, Data Observatory catalog routes, persistence, execution lifecycle, artifacts |
| [architecture/contracts.md](architecture/contracts.md) | Binding interfaces: environments, dataset layout, StormSpec, result and artifact schemas, HTTP API |
| [architecture/scientific-spec.md](architecture/scientific-spec.md) | PyPSA equations, metric definitions, assumptions and scientific limitations |
| [architecture/design-system.md](architecture/design-system.md) | Web design tokens and shared UI primitives |
| [decisions/](decisions/) | Architecture decision records: [0001](decisions/0001-architecture-and-environment-isolation.md) engine isolation and deployment split · [0002](decisions/0002-pypsa-explorer-baseline.md) PyPSA-Explorer baseline · [0003](decisions/0003-file-backed-data-observatory.md) file-backed Data Observatory |

## Data

| Document | Content |
|---|---|
| [data/sources-and-licensing.md](data/sources-and-licensing.md) | Every shipped network and Observatory dataset: source, licence, attribution, what is not published and why, candidate-source scoring (NASA POWER, EIA, …) |
| [data/observatory-pipeline.md](data/observatory-pipeline.md) | Producing, verifying, publishing and rolling back the licence-gated `data/observatory/` bundle |
| [data/production-inventory.md](data/production-inventory.md) | Measured production data inventory (API-observable part; database/storage sections blocked) |
| [research/data-catalog.md](research/data-catalog.md) | Network dataset catalog with provenance |

## Deployment and development

| Document | Content |
|---|---|
| [deployment/local-development.md](deployment/local-development.md) | Per-component `uv` setup, SQLite, Docker Compose/Postgres, API/web commands, observatory pipeline, diagnostics |
| [deployment/backend.md](deployment/backend.md) | API deployment: local Python, Docker, Render, lost-artifact recovery, Postgres/Supabase schema and runbook |
| [deployment/render.md](deployment/render.md) | API on Render (Docker), env vars, free-tier limits |
| [deployment/vercel.md](deployment/vercel.md) | Web app on Vercel (`apps/web`) |
| [deployment/supabase.md](deployment/supabase.md) | Postgres on Supabase: migrations, RLS, keys |
| [deployment/ci.md](deployment/ci.md) | GitHub Actions workflows |

## Research, benchmarks and audits

| Location | Content |
|---|---|
| [research/](research/) | Literature and upstream research notes, study reports (AC validation, advisor, Grid2Op, SimBench, observed analogues, …) |
| [research/compatibility-matrix.md](research/compatibility-matrix.md) | Published engine requirements and measured uv resolver evidence for environment isolation |
| [benchmarks/stormbench.md](benchmarks/stormbench.md) | StormBench screening benchmark, incl. [reproducibility and ties](benchmarks/stormbench.md#reproducibility-and-ties) |
| [benchmarks/](benchmarks/) | Other benchmark reports: cross-engine, PyPSA presets, API memory, web performance ([3.0](benchmarks/web-performance-3.0.md), [3.2](benchmarks/web-performance-3.2.md)) |
| [audit/](audit/) | Audits of reused upstream projects and historical production/security/functional audits (bannered when superseded) |
