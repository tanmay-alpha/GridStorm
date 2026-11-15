"""Restore lost artifact blobs byte-for-byte from operator-supplied sources, never from guesses.

A completed job keeps the sha256 of every artifact it produced. When a blob is lost from the
store (e.g. results written to Render's ephemeral disk before durable storage existed), the
original bytes can sometimes be recovered: a precomputed job's result is the canonical payload
of a committed artifact file (retrievable from git history), and a scenario blob is the canonical
form of the job's stored spec. This module accepts candidate files, derives those canonical forms,
and re-uploads a candidate **only if its sha256 equals the recorded one**. Nothing else changes:
the job keeps its id, checksum and metrics; a mismatch leaves the blob missing (recompute instead).

Run with the API's server-side environment, from ``services/api``::

    git show 96f3f3a:data/artifacts/pypsa/scigrid-de-baseline.json > old-artifact.json
    python -m gridstorm_api.jobs.restore JOB_ID [JOB_ID ...] --source old-artifact.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..access import audit
from ..config import Settings
from ..context import AppContext
from ..db.models import SimulationArtifact, SimulationJob
from .service import canonical_bytes


def candidates(sources: list[bytes], job: SimulationJob) -> dict[str, bytes]:
    """``{sha256: bytes}`` for every byte string a source could have been stored as."""
    out: list[bytes] = []
    for raw in sources:
        out.append(raw)
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        # A committed precomputed artifact wraps the stored result as its "payload".
        if isinstance(doc, dict) and isinstance(doc.get("payload"), dict):
            out.append(canonical_bytes(doc["payload"]))
    if job.spec:
        out.append(canonical_bytes(job.spec))
    return {hashlib.sha256(data).hexdigest(): data for data in out}


def _record_location(session: Session, job: SimulationJob, row: SimulationArtifact, backend: str):
    """Point the artifact row at the backend now holding its verified bytes, with an audit trail."""
    previous, row.storage_backend = row.storage_backend, backend
    audit(
        session,
        None,
        "simulation.artifact_restore",
        "simulation_job",
        job.id,
        {
            "kind": row.kind,
            "sha256": row.sha256,
            "bytes": row.bytes,
            "previous_backend": previous,
            "backend": backend,
        },
    )


def restore_job(
    ctx: AppContext, session: Session, job: SimulationJob, sources: list[bytes]
) -> dict[str, str]:
    """``{artifact kind: present | restored | missing}`` for one job; commits restored rows.

    A blob already present under its content address (e.g. restored for another job sharing the
    same bytes) is verified and, if the row names another backend, relabelled to the real one.
    """
    rows = session.scalars(
        select(SimulationArtifact).where(SimulationArtifact.job_id == job.id)
    ).all()
    found = candidates(sources, job)
    status: dict[str, str] = {}
    backend = ctx.store.backend
    for row in rows:
        if row.kind == "result" and row.sha256 != job.result_sha256:
            status[row.kind] = "missing"  # inconsistent metadata: never pick a side
            continue
        if ctx.store.exists(row.storage_key, fresh=True):
            if row.storage_backend != backend:
                ctx.store.get(row.storage_key, expected_sha256=row.sha256)
                _record_location(session, job, row, backend)
            status[row.kind] = "present"
            continue
        data = found.get(row.sha256)
        if data is None:
            status[row.kind] = "missing"
            continue
        ext = row.storage_key.rsplit(".", 1)[-1]
        blob = ctx.store.put(data, ext=ext, content_type=row.content_type)
        if blob.key != row.storage_key or blob.sha256 != row.sha256:
            raise RuntimeError(f"restored {row.kind} landed at an unexpected content address")
        _record_location(session, job, row, blob.backend)
        status[row.kind] = "restored"
    if "result" not in status and job.result_sha256:
        status["result"] = "missing"  # no artifact record: nothing to restore against
    session.commit()
    return status


def restore(
    job_ids: list[uuid.UUID], paths: list[Path], settings: Settings
) -> list[dict[str, Any]]:
    ctx = AppContext.build(replace(settings, run_workers=False))
    sources = [path.read_bytes() for path in paths]
    try:
        report = []
        with ctx.db.session() as session:
            for job_id in job_ids:
                job = session.get(SimulationJob, job_id)
                if job is None or job.status != "completed":
                    report.append({"job_id": str(job_id), "error": "no completed job"})
                    continue
                artifacts = restore_job(ctx, session, job, sources)
                report.append({"job_id": str(job_id), "artifacts": artifacts})
        return report
    finally:
        ctx.store.close()
        ctx.db.dispose()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_ids", type=uuid.UUID, nargs="+")
    parser.add_argument(
        "--source", type=Path, action="append", default=[], help="candidate file (repeatable)"
    )
    args = parser.parse_args(argv)
    report = restore(args.job_ids, args.source, Settings.from_env())
    print(json.dumps(report, sort_keys=True))
    ok = all(
        entry.get("artifacts", {}).get("result") in ("present", "restored") for entry in report
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
