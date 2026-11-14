# GridStorm documentation

GridStorm is a power-grid resilience and crisis-simulation research platform. It is a research and
teaching tool — not a live control system and not a validated blackout predictor.

## Start here

| Document | For |
|---|---|
| [User guide](user-guide.md) | Using the web app: pages, metrics with units and formulas, execution modes, limitations |
| [Glossary](glossary.md) | Power-system terms used in the UI (LOPF, PTDF, LODF, N-1, VOLL, EENS, LOLP, rho, …) |
| [Engineering story](engineering-story.md) | Architecture and the hard problems, with file references |

## Architecture

| Document | Content |
|---|---|
| [architecture/overview.md](architecture/overview.md) | Components, principles, deployment split |
| [architecture/contracts.md](architecture/contracts.md) | Binding interfaces: environments, dataset layout, StormSpec, result and artifact schemas, HTTP API |
| [decisions/](decisions/) | Architecture decision records (ADR 0001: engine isolation and deployment split) |

## Deployment and development

| Document | Content |
|---|---|
| [deployment/local-development.md](deployment/local-development.md) | Per-component `uv` environments, running API and web locally, tests |
| [deployment/render.md](deployment/render.md) | API on Render (Docker), env vars, free-tier limits |
| [deployment/vercel.md](deployment/vercel.md) | Web app on Vercel (`apps/web`) |
| [deployment/supabase.md](deployment/supabase.md) | Postgres on Supabase: migrations, RLS, keys |
| [deployment/ci.md](deployment/ci.md) | GitHub Actions workflows |

## Research and audits

| Location | Content |
|---|---|
| [research/](research/) | Literature and upstream research notes |
| [audit/](audit/) | Audits of reused upstream projects (e.g. grid2viz) |
| [benchmarks/](benchmarks/) | Benchmark reports |
