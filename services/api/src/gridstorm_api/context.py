"""Application context: long-lived services shared by routers and the job worker pool."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .auth import JWTVerifier
from .catalog import NetworkCatalog
from .config import Settings
from .db import Database
from .observatory import DataObservatory
from .precomputed import PrecomputedArtifacts
from .ratelimit import TokenBucketLimiter
from .storage import ArtifactStore, make_store

if TYPE_CHECKING:
    from .analytics import AnalyticsService
    from .jobs.worker import WorkerPool
    from .readiness import SolverProbe, StorageProbe


@dataclass
class AppContext:
    settings: Settings
    db: Database
    catalog: NetworkCatalog
    store: ArtifactStore
    precomputed: PrecomputedArtifacts
    jwt: JWTVerifier
    post_limiter: TokenBucketLimiter
    sim_limiter: TokenBucketLimiter
    observatory: DataObservatory
    network_versions: dict[str, uuid.UUID] = field(default_factory=dict)
    pool: WorkerPool | None = None
    analytics: AnalyticsService | None = None
    solver_probe: SolverProbe | None = None
    storage_probe: StorageProbe | None = None

    @classmethod
    def build(cls, settings: Settings) -> AppContext:
        catalog = NetworkCatalog(settings.networks_dir)
        precomputed = PrecomputedArtifacts(settings.artifacts_dir)
        return cls(
            settings=settings,
            db=Database(settings.resolved_database_url),
            catalog=catalog,
            store=make_store(settings),
            precomputed=precomputed,
            jwt=JWTVerifier(
                secret=settings.supabase_jwt_secret,
                supabase_url=settings.supabase_url,
                audience=settings.supabase_jwt_audience,
            ),
            post_limiter=TokenBucketLimiter(
                settings.rate_limit_post_per_min, settings.rate_limit_post_burst
            ),
            sim_limiter=TokenBucketLimiter(
                settings.rate_limit_sim_per_min, settings.rate_limit_sim_burst
            ),
            observatory=DataObservatory(settings, catalog, precomputed),
        )
