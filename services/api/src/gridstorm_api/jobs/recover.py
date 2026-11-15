"""Recompute a lost result using its stored scenario, without changing the original job.

Run with the API's server-side environment: ``python -m gridstorm_api.jobs.recover JOB_ID``.
The privileged operator CLI accepts ``--force`` to recompute an available result as well.
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import replace
from typing import Any

from ..auth import Principal
from ..config import Settings
from ..context import AppContext
from ..db.models import SimulationJob
from ..errors import APIError, NotFound
from ..main import _startup
from .service import job_json, recompute_job
from .worker import WorkerPool


def recover(job_id: uuid.UUID, settings: Settings, *, force: bool = False) -> dict[str, Any]:
    """Run one recovery synchronously; never claim unrelated jobs from the server queue."""
    ctx = AppContext.build(replace(settings, run_workers=False))
    try:
        _startup(ctx)
        pool = WorkerPool(ctx, single_instance=False)
        with ctx.db.session() as session:
            source = session.get(SimulationJob, job_id)
            if source is None:
                raise NotFound("simulation job not found", code="job_not_found")
            principal = Principal(user_id=source.owner_id, role="recovery_operator")
            job = recompute_job(
                ctx, session, principal, source, force=force, claim_for=pool.worker_id
            )
            recovered_id, pending = job.id, job.status == "running"
        if pending:
            pool.run(recovered_id)
        with ctx.db.session() as session:
            return job_json(ctx, session, session.get(SimulationJob, recovered_id))
    finally:
        ctx.store.close()
        ctx.db.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_id", type=uuid.UUID)
    parser.add_argument("--force", action="store_true", help="also recompute an available result")
    args = parser.parse_args(argv)
    try:
        job = recover(args.job_id, Settings.from_env(), force=args.force)
    except APIError as exc:
        print(json.dumps({"error": {"code": exc.code, "message": exc.message}}))
        return 1
    print(json.dumps(job, sort_keys=True))
    return 0 if job["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
