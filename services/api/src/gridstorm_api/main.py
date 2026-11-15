"""ASGI entrypoint: ``uvicorn gridstorm_api.main:app``.

Startup (lifespan): build the application context, create/verify the schema, sync the network
catalog and StormSpec presets into the database, then start the in-process worker pool
(live mode only). Heavy scientific imports (pypsa, linopy, highspy) never happen in this process:
analytics are served from precomputed JSON and simulations run in engine subprocesses.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import RedirectResponse

from . import __version__
from .analytics import AnalyticsService
from .config import Settings
from .context import AppContext
from .errors import install_error_handlers
from .ratelimit import BodySizeLimitMiddleware
from .readiness import SolverProbe, StorageProbe
from .routers import artifacts, comparisons, health, networks, scenarios, simulations
from .security_headers import SecurityHeadersMiddleware
from .sync import sync_catalog, sync_presets

log = logging.getLogger("gridstorm_api")

EXPOSED_HEADERS = [
    "X-GridStorm-Result-SHA256",
    "X-GridStorm-Report-SHA256",
    "X-GridStorm-Payload-Verified",
    "Retry-After",
]


def _startup(ctx: AppContext) -> None:
    s = ctx.settings
    ctx.solver_probe = SolverProbe(s.python_executable, s.solver_check_ttl_s)
    ctx.storage_probe = StorageProbe(ctx.store, s.storage_check_ttl_s)
    ctx.analytics = AnalyticsService()
    try:
        ctx.db.init_schema(
            migrations_dir=s.migrations_dir,
            auto_migrate=s.db_auto_migrate,
            supabase_stub=s.db_supabase_stub,
        )
        with ctx.db.session() as session:
            ctx.network_versions = sync_catalog(session, ctx.catalog)
            rejected = sync_presets(session, ctx.catalog, s.resolved_presets_dir)
        if rejected:
            log.error("rejected preset scenario file(s): %s", rejected)
    except Exception:
        # Keep serving /health and report the failure through /ready instead of crash-looping.
        log.exception("database initialisation failed")
        return
    if s.execution_mode == "live" and s.run_workers and s.max_concurrent_jobs > 0:
        from .jobs.worker import WorkerPool

        ctx.pool = WorkerPool(ctx)
        ctx.pool.start()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        ctx = AppContext.build(settings)
        app.state.ctx = ctx
        _startup(ctx)
        log.info(
            "gridstorm-api %s ready: mode=%s db=%s workers=%d",
            __version__,
            settings.execution_mode,
            ctx.db.engine.dialect.name,
            settings.max_concurrent_jobs if ctx.pool else 0,
        )
        try:
            yield
        finally:
            if ctx.pool is not None:
                ctx.pool.stop()
            ctx.db.dispose()
            ctx.store.close()

    app = FastAPI(
        title="GridStorm API",
        version=__version__,
        summary="Power-grid crisis scenarios: network catalog, StormSpec validation, simulation "
        "jobs, comparisons and reproducible reports.",
        description="Contract: docs/architecture/contracts.md §6. Errors are "
        '`{"error": {"code", "message", "details"}}`; pages are `{items, total, limit, offset}`.',
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.add_middleware(GZipMiddleware, minimum_size=2048)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=EXPOSED_HEADERS,
        max_age=600,
    )
    # outermost: reject oversized bodies before anything else reads them
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
    # wraps everything, so 413s and error responses carry the headers too (VER-011)
    app.add_middleware(SecurityHeadersMiddleware, trust_proxy=settings.trust_proxy)

    for module in (health, networks, scenarios, simulations, comparisons, artifacts):
        app.include_router(module.router)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    return app


app = create_app()
