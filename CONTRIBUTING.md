# Contributing to GridStorm

## Ground rules

1. **No fabricated numbers.** Every value shown in the UI or docs must come from a dataset with a
   manifest or from a solver run with an execution manifest. Label provenance
   (`observed | estimated | synthetic | modeled | calculated`).
2. **Reject, don't approximate.** If an engine cannot represent a scenario operation, the adapter
   must reject it with `unsupported_operation`.
3. **Respect upstream licenses.** Reused or derived files start with a header naming the upstream
   repository, commit SHA, original path and license. Add the upstream to `UPSTREAM_ATTRIBUTION.md`.
   Do not copy code from repositories without a license (e.g. `pypsa-eur-map-viewer`).
4. **Keep environments isolated.** Each Python component has its own `pyproject.toml` and `uv.lock`;
   do not add pandapower or Grid2Op to the core (PyPSA) environment.
5. **Small data only.** Networks ≤ 10 MB, artifacts ≤ 5 MB, with SHA-256 in manifests.

## Development

```bash
# Python component (example: StormSpec)
cd packages/stormspec && uv sync && uv run pytest

# API
cd services/api && uv sync && uv run uvicorn gridstorm_api.main:app --reload --port 8000

# Web
cd apps/web && npm ci && npm run dev
```

Interfaces are defined in `docs/architecture/contracts.md`; changes need an ADR in `docs/decisions/`.

## Commits

Use conventional, descriptive commit messages. Do not add co-author trailers for people or tools that
did not author the change.
