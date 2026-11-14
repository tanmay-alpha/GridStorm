"""In-process worker pool executing queued jobs as engine subprocesses.

* Claiming is atomic: ``UPDATE ... WHERE id = (SELECT ... FOR UPDATE SKIP LOCKED)`` on Postgres;
  on SQLite a compare-and-set ``UPDATE ... WHERE id = ? AND status = 'queued'`` (SQLite serialises
  writers, so exactly one claimer wins).
* Each job runs ``GRIDSTORM_ENGINE_CMD`` (default ``python -m gridstorm_pypsa run ...``) in a
  temporary directory. ``STAGE <name>`` stdout lines update ``stage``/``stage_history``.
* Limits: wall-clock ``GRIDSTORM_JOB_TIMEOUT_S`` (kill → status ``timeout``) and a resident-set
  watchdog: the RSS of the child process tree is polled every ~0.25 s (psutil) and the tree is
  killed when it exceeds ``GRIDSTORM_JOB_MEMORY_MB`` (→ status ``failed``, error code
  ``memory_limit``). RLIMIT_AS is deliberately NOT used: numpy/OpenBLAS/HiGHS reserve large
  virtual address ranges, so an address-space cap causes spurious MemoryErrors at import.
  BLAS/OpenMP thread pools are pinned to one thread in the child.
* Cancellation kills the subprocess (process group on POSIX) within ~0.25 s when the job runs in
  this process, or at the next heartbeat (``GRIDSTORM_JOB_HEARTBEAT_S``) otherwise.
* Recovery: a ``running`` job whose heartbeat is older than ``GRIDSTORM_JOB_STALE_AFTER_S`` (or any
  ``running`` job found at startup, when ``single_instance``) is requeued while
  ``attempts < GRIDSTORM_JOB_MAX_ATTEMPTS``, otherwise failed with code ``worker_restart``.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import shlex
import shutil
import signal
import socket
import subprocess
import tempfile
import threading
import time
import uuid
from collections import deque
from datetime import timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import and_, or_, select, update

from ..access import audit
from ..context import AppContext
from ..db.models import JOB_STAGES, SimulationJob, utcnow
from .results import parse_result, record_artifact, record_metrics, solver_summary
from .service import stage_event

log = logging.getLogger("gridstorm_api.worker")

LOG_LIMIT_BYTES = 256 * 1024
_RUN_STAGES = frozenset(JOB_STAGES) - {"queued"}


def build_command(
    template: str, *, python: str, scenario: Path, network_dir: Path, out: Path
) -> list[str]:
    """Split the template first, then substitute, so paths with spaces stay single arguments."""
    subs = {
        "{python}": python,
        "{scenario}": str(scenario),
        "{network_dir}": str(network_dir),
        "{out}": str(out),
    }
    argv = []
    for token in shlex.split(template):
        for k, v in subs.items():
            token = token.replace(k, v)
        argv.append(token)
    return argv


def tree_rss_bytes(pid: int) -> int:
    """Resident set size of a process and all its descendants (0 if it already exited)."""
    import psutil

    try:
        root = psutil.Process(pid)
        procs = [root, *root.children(recursive=True)]
    except psutil.Error:
        return 0
    total = 0
    for p in procs:
        try:
            total += p.memory_info().rss
        except psutil.Error:
            continue
    return total


def kill_tree(pid: int) -> None:
    import psutil

    try:
        root = psutil.Process(pid)
        procs = [*root.children(recursive=True), root]
    except psutil.Error:
        return
    for p in procs:
        try:
            p.kill()
        except psutil.Error:
            continue


class _Tail:
    """Bounded combined stdout/stderr log (keeps the head and the most recent tail)."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.head: list[str] = []
        self.head_bytes = 0
        self.tail: deque[str] = deque()
        self.tail_bytes = 0
        self.dropped = 0
        self.lock = threading.Lock()

    def add(self, line: str) -> None:
        n = len(line.encode("utf-8", "replace"))
        with self.lock:
            if self.head_bytes + n <= self.limit // 2:
                self.head.append(line)
                self.head_bytes += n
                return
            self.tail.append(line)
            self.tail_bytes += n
            while self.tail_bytes > self.limit // 2 and self.tail:
                self.tail_bytes -= len(self.tail.popleft().encode("utf-8", "replace"))
                self.dropped += 1

    def text(self) -> str:
        with self.lock:
            mid = [f"... [{self.dropped} line(s) omitted] ...\n"] if self.dropped else []
            return "".join(self.head + mid + list(self.tail))

    def last(self, chars: int) -> str:
        return self.text()[-chars:]


class WorkerPool:
    def __init__(self, ctx: AppContext, *, single_instance: bool = True) -> None:
        self.ctx = ctx
        self.settings = ctx.settings
        self.single_instance = single_instance
        self.worker_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._wake = threading.Event()
        self._stopping = threading.Event()
        self._threads: list[threading.Thread] = []
        self._procs: dict[uuid.UUID, subprocess.Popen[str]] = {}
        self._cancel: set[uuid.UUID] = set()
        self._lock = threading.Lock()
        self._last_sweep = 0.0

    # -- lifecycle ---------------------------------------------------------------------------
    @property
    def active(self) -> bool:
        return bool(self._threads) and not self._stopping.is_set()

    def start(self) -> None:
        self.recover(startup=True)
        for i in range(self.settings.max_concurrent_jobs):
            t = threading.Thread(target=self._loop, name=f"gridstorm-worker-{i}", daemon=True)
            t.start()
            self._threads.append(t)
        log.info("worker pool %s started with %d thread(s)", self.worker_id, len(self._threads))

    def stop(self, timeout: float = 10.0) -> None:
        self._stopping.set()
        self._wake.set()
        with self._lock:
            procs = list(self._procs.values())
        for p in procs:
            self._kill(p)
        for t in self._threads:
            t.join(timeout)
        self._threads.clear()

    def notify(self) -> None:
        self._wake.set()

    def request_cancel(self, job_id: uuid.UUID) -> None:
        with self._lock:
            self._cancel.add(job_id)
            proc = self._procs.get(job_id)
        if proc is not None:
            self._kill(proc)

    # -- recovery ----------------------------------------------------------------------------
    def recover(self, *, startup: bool = False) -> int:
        """Requeue or fail ``running`` jobs whose worker is gone. Returns rows recovered."""
        now = utcnow()
        stale_before = now - timedelta(seconds=self.settings.job_stale_after_s)
        cond = SimulationJob.status == "running"
        if not (startup and self.single_instance):
            cond = and_(
                cond,
                SimulationJob.worker_id != self.worker_id,
                or_(
                    SimulationJob.heartbeat_at < stale_before,
                    and_(
                        SimulationJob.heartbeat_at.is_(None),
                        SimulationJob.updated_at < stale_before,
                    ),
                ),
            )
        recovered = 0
        with self.ctx.db.session() as s:
            for job in s.scalars(select(SimulationJob).where(cond)).all():
                values: dict[str, Any] = {
                    "worker_id": None,
                    "heartbeat_at": None,
                    "updated_at": now,
                }
                if job.cancel_requested:
                    values.update(
                        status="cancelled",
                        finished_at=now,
                        error={"code": "cancelled", "message": "cancelled; worker was lost"},
                    )
                elif job.attempts < self.settings.job_max_attempts:
                    values.update(
                        status="queued",
                        stage="queued",
                        started_at=None,
                        stage_history=[
                            *job.stage_history,
                            stage_event("queued", now, reason="worker_restart"),
                        ],
                    )
                else:
                    values.update(
                        status="failed",
                        finished_at=now,
                        error={
                            "code": "worker_restart",
                            "message": (
                                f"the worker running this job stopped (attempt {job.attempts} of "
                                f"{self.settings.job_max_attempts}); not retried again"
                            ),
                        },
                    )
                res = s.execute(
                    update(SimulationJob)
                    .where(
                        SimulationJob.id == job.id,
                        SimulationJob.status == "running",
                        SimulationJob.worker_id.is_(job.worker_id)
                        if job.worker_id is None
                        else SimulationJob.worker_id == job.worker_id,
                    )
                    .values(**values)
                )
                if res.rowcount:
                    recovered += 1
                    audit(
                        s,
                        None,
                        "simulation.recover",
                        "simulation_job",
                        job.id,
                        {"new_status": values["status"], "attempts": job.attempts},
                    )
            s.commit()
        if recovered:
            log.warning("recovered %d stale running job(s)", recovered)
            self._wake.set()
        return recovered

    # -- main loop ---------------------------------------------------------------------------
    def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                if time.monotonic() - self._last_sweep > self.settings.job_stale_after_s / 2:
                    self._last_sweep = time.monotonic()
                    self.recover()
                job_id = self.claim()
                if job_id is None:
                    self._wake.wait(self.settings.job_poll_s)
                    self._wake.clear()
                    continue
                self.run(job_id)
            except Exception:  # keep the worker alive; the job row records failures
                log.exception("worker loop error")
                time.sleep(1.0)

    def claim(self) -> uuid.UUID | None:
        now = utcnow()
        with self.ctx.db.session() as s:
            if self.ctx.db.is_postgres:
                sub = (
                    select(SimulationJob.id)
                    .where(SimulationJob.status == "queued")
                    .order_by(SimulationJob.created_at)
                    .limit(1)
                    .with_for_update(skip_locked=True)
                    .scalar_subquery()
                )
                stmt = update(SimulationJob).where(SimulationJob.id == sub)
            else:
                candidate = s.scalar(
                    select(SimulationJob.id)
                    .where(SimulationJob.status == "queued")
                    .order_by(SimulationJob.created_at)
                    .limit(1)
                )
                if candidate is None:
                    return None
                stmt = update(SimulationJob).where(
                    SimulationJob.id == candidate, SimulationJob.status == "queued"
                )
            stmt = stmt.values(
                status="running",
                worker_id=self.worker_id,
                heartbeat_at=now,
                started_at=now,
                updated_at=now,
                attempts=SimulationJob.attempts + 1,
            ).returning(SimulationJob.id)
            job_id = s.execute(stmt).scalar()
            s.commit()
            return job_id

    def _kill(self, proc: subprocess.Popen[str]) -> None:
        if proc.poll() is not None:
            return
        kill_tree(proc.pid)
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            pass

    def _owned_update(self, s: Any, job_id: uuid.UUID, **values: Any) -> bool:
        res = s.execute(
            update(SimulationJob)
            .where(
                SimulationJob.id == job_id,
                SimulationJob.status == "running",
                SimulationJob.worker_id == self.worker_id,
            )
            .values(updated_at=utcnow(), **values)
        )
        return bool(res.rowcount)

    def run(self, job_id: uuid.UUID) -> None:
        settings = self.settings
        with self.ctx.db.session() as s:
            job = s.get(SimulationJob, job_id)
            assert job is not None
            spec, network_id = job.spec, job.network_id
            history = list(job.stage_history or [])
            expected_hash = job.scenario_hash
        try:
            entry = self.ctx.catalog.get(network_id)
        except Exception as exc:
            self._finish(
                job_id, status="failed", error={"code": "network_unavailable", "message": str(exc)}
            )
            return

        workdir = Path(tempfile.mkdtemp(prefix="gridstorm-job-"))
        logbuf = _Tail(LOG_LIMIT_BYTES)
        stages: queue.Queue[str] = queue.Queue()
        try:
            scenario_path = workdir / "scenario.json"
            scenario_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
            out_path = workdir / "result.json"
            argv = build_command(
                settings.engine_cmd,
                python=settings.python_executable,
                scenario=scenario_path,
                network_dir=entry.directory,
                out=out_path,
            )
            env = {
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                "PYTHONIOENCODING": "utf-8",
                "OPENBLAS_NUM_THREADS": "1",
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            }
            for secret in ("SUPABASE_JWT_SECRET", "DATABASE_URL", "AWS_SECRET_ACCESS_KEY"):
                env.pop(secret, None)
            popen_kw: dict[str, Any] = {}
            if os.name == "posix":
                popen_kw["start_new_session"] = True
            proc = subprocess.Popen(
                argv,
                cwd=workdir,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **popen_kw,
            )
        except OSError as exc:
            shutil.rmtree(workdir, ignore_errors=True)
            self._finish(
                job_id, status="failed", error={"code": "engine_start_failed", "message": str(exc)}
            )
            return

        with self._lock:
            self._procs[job_id] = proc
            cancelled_early = job_id in self._cancel

        def read_stdout() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                logbuf.add(line)
                parts = line.strip().split()
                if len(parts) == 2 and parts[0] == "STAGE" and parts[1] in _RUN_STAGES:
                    stages.put(parts[1])

        def read_stderr() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                logbuf.add("[stderr] " + line)

        readers = [
            threading.Thread(target=read_stdout, daemon=True),
            threading.Thread(target=read_stderr, daemon=True),
        ]
        for r in readers:
            r.start()

        deadline = time.monotonic() + settings.job_timeout_s
        next_beat = time.monotonic() + settings.job_heartbeat_s
        reason: str | None = "cancel" if cancelled_early else None
        if reason:
            self._kill(proc)
        lost = False
        memory_limit = settings.job_memory_mb * 1024 * 1024
        peak_rss = 0
        while proc.poll() is None:
            try:
                stage = stages.get(timeout=0.25)
                history.append(stage_event(stage))
                with self.ctx.db.session() as s:
                    lost = not self._owned_update(
                        s, job_id, stage=stage, stage_history=history, heartbeat_at=utcnow()
                    )
                    s.commit()
            except queue.Empty:
                pass
            now = time.monotonic()
            with self._lock:
                if job_id in self._cancel and reason is None:
                    reason = "cancel"
            if reason is None and now >= deadline:
                reason = "timeout"
            if reason is None and memory_limit > 0:
                rss = tree_rss_bytes(proc.pid)
                peak_rss = max(peak_rss, rss)
                if rss > memory_limit:
                    reason = "memory"
            if reason is None and now >= next_beat:
                next_beat = now + settings.job_heartbeat_s
                with self.ctx.db.session() as s:
                    lost = not self._owned_update(s, job_id, heartbeat_at=utcnow())
                    s.commit()
                    if s.scalar(
                        select(SimulationJob.cancel_requested).where(SimulationJob.id == job_id)
                    ):
                        reason = "cancel"
            if lost and reason is None:
                reason = "lost"
            if reason is not None:
                self._kill(proc)
        for r in readers:
            r.join(5)
        while not stages.empty():
            history.append(stage_event(stages.get_nowait()))
        with self._lock:
            self._procs.pop(job_id, None)
            self._cancel.discard(job_id)

        try:
            log_blob = self.ctx.store.put(
                logbuf.text().encode("utf-8"), ext="txt", content_type="text/plain; charset=utf-8"
            )
            if reason == "lost":
                log.warning("job %s was taken over by recovery; result discarded", job_id)
                return
            if self._stopping.is_set() and reason != "cancel" and proc.returncode != 0:
                # shutdown killed the engine: leave the row for recovery to requeue
                return
            if reason == "cancel":
                self._finish(
                    job_id,
                    status="cancelled",
                    history=history,
                    log_blob=log_blob,
                    error={"code": "cancelled", "message": "cancelled while running"},
                )
                return
            if reason == "memory":
                self._finish(
                    job_id,
                    status="failed",
                    history=history,
                    log_blob=log_blob,
                    error={
                        "code": "memory_limit",
                        "message": (
                            f"engine resident memory {peak_rss / 2**20:.0f} MB exceeded the "
                            f"{settings.job_memory_mb} MB limit; process tree killed"
                        ),
                    },
                )
                return
            if reason == "timeout":
                self._finish(
                    job_id,
                    status="timeout",
                    history=history,
                    log_blob=log_blob,
                    error={
                        "code": "timeout",
                        "message": f"engine exceeded the {settings.job_timeout_s:g} s limit",
                    },
                )
                return
            if proc.returncode != 0 or not out_path.is_file():
                tail = logbuf.last(2000)
                code = "engine_out_of_memory" if "MemoryError" in tail else "engine_failed"
                self._finish(
                    job_id,
                    status="failed",
                    history=history,
                    log_blob=log_blob,
                    error={
                        "code": code,
                        "message": f"engine exited with code {proc.returncode}: {tail.strip()}",
                    },
                )
                return
            data = out_path.read_bytes()
            try:
                result = parse_result(data)
            except ValueError as exc:
                self._finish(
                    job_id,
                    status="failed",
                    history=history,
                    log_blob=log_blob,
                    error={"code": "invalid_result", "message": str(exc)},
                )
                return
            if result.get("scenario_hash") != expected_hash:
                self._finish(
                    job_id,
                    status="failed",
                    history=history,
                    log_blob=log_blob,
                    error={
                        "code": "result_mismatch",
                        "message": "engine result scenario_hash does not match the job",
                    },
                )
                return
            blob = self.ctx.store.put(data, ext="json")
            error = None
            if result["outcome"] == "error":
                warnings = "; ".join(str(w) for w in result.get("warnings") or [])
                error = {
                    "code": "engine_reported_error",
                    "message": warnings or "engine reported outcome=error",
                }
            self._finish(
                job_id,
                status="completed",
                history=history,
                log_blob=log_blob,
                result=result,
                result_blob=blob,
                error=error,
            )
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    def _finish(
        self,
        job_id: uuid.UUID,
        *,
        status: str,
        error: dict[str, Any] | None,
        history: list[dict[str, Any]] | None = None,
        log_blob: Any = None,
        result: dict[str, Any] | None = None,
        result_blob: Any = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": status,
            "error": error,
            "finished_at": utcnow(),
            "heartbeat_at": None,
        }
        if history is not None:
            values["stage_history"] = history
        if result is not None:
            values.update(
                outcome=result["outcome"],
                solver=solver_summary(result),
                result_sha256=result_blob.sha256,
            )
            if history is not None and (not history or history[-1]["stage"] != "done"):
                values["stage_history"] = [*history, stage_event("done")]
            values["stage"] = "done"
        elif history:
            values["stage"] = history[-1]["stage"]
        with self.ctx.db.session() as s:
            if not self._owned_update(s, job_id, **values):
                s.rollback()
                log.warning(
                    "job %s no longer owned by %s; final state dropped", job_id, self.worker_id
                )
                return
            job = s.get(SimulationJob, job_id)
            assert job is not None
            if log_blob is not None:
                record_artifact(s, job, "log", log_blob)
            if result is not None:
                record_artifact(s, job, "result", result_blob)
                record_metrics(s, job, result)
            s.commit()
        log.info("job %s finished: %s", job_id, status)
