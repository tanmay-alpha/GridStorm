# syntax=docker/dockerfile:1.7
# GridStorm API image. Build context = repository root:
#   docker build -f services/api/Dockerfile -t gridstorm-api .
# Render (srv-dbs8a30ae00c73cs4cog) builds it with dockerContext "." and injects PORT.

ARG PYTHON_IMAGE=python:3.11-slim-bookworm

# ---------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS builder
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/services/api/.venv
WORKDIR /app

# Dependency layer: lockfile + the path-dependency project metadata only.
COPY services/api/pyproject.toml services/api/uv.lock services/api/
COPY packages/stormspec/pyproject.toml packages/stormspec/
COPY packages/canonical-grid/pyproject.toml packages/canonical-grid/
COPY workers/pypsa/pyproject.toml workers/pypsa/
COPY services/analytics/pyproject.toml services/analytics/
RUN --mount=type=cache,target=/root/.cache/uv \
    cd services/api && uv sync --frozen --no-dev --no-install-project --no-install-workspace \
        --no-install-package stormspec --no-install-package canonical-grid \
        --no-install-package gridstorm-pypsa --no-install-package gridstorm-analytics

# Source layer (editable installs keep the repo layout: config resolves /app as the root).
COPY packages/stormspec packages/stormspec
COPY packages/canonical-grid packages/canonical-grid
COPY workers/pypsa workers/pypsa
COPY services/analytics services/analytics
COPY services/api services/api
RUN --mount=type=cache,target=/root/.cache/uv \
    cd services/api && uv sync --frozen --no-dev

# ---------------------------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime
ARG GIT_SHA=""
ENV PATH=/app/services/api/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OPENBLAS_NUM_THREADS=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    PORT=8000 \
    GRIDSTORM_DATA_DIR=/app/data \
    GRIDSTORM_STATE_DIR=/tmp/gridstorm \
    GRIDSTORM_MIGRATIONS_DIR=/app/database/migrations \
    GRIDSTORM_TRUST_PROXY=true \
    GRIDSTORM_GIT_SHA=${GIT_SHA}

RUN groupadd --system --gid 10001 gridstorm \
    && useradd --system --uid 10001 --gid gridstorm --home-dir /app --no-create-home gridstorm \
    && mkdir /state \
    && chown gridstorm:gridstorm /state

WORKDIR /app
COPY --from=builder --chown=root:root /app /app
COPY database database
# Datasets (data/networks) and precomputed artifacts (data/artifacts) are baked in because
# Render's disk is ephemeral; .dockerignore admits only those two subtrees of data/.
COPY data data

USER gridstorm
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health', timeout=4).read()" || exit 1

# One uvicorn process: the job worker pool lives in-process (bounded by
# GRIDSTORM_MAX_CONCURRENT_JOBS); engine runs are subprocesses with RSS/time limits.
CMD ["sh", "-c", "exec uvicorn gridstorm_api.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers --forwarded-allow-ips='*' --no-server-header"]
