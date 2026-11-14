"""Engine OOM handling: the solver child is the OOM killer's victim; SIGKILL -> memory_limit."""

from __future__ import annotations

import sys

import pytest

from conftest import run_job, scenario
from gridstorm_api.jobs import worker

# Kills itself with signal 9: SIGKILL on POSIX (returncode -9), TerminateProcess(9) on Windows.
SELF_KILL = '{python} -c "import os; os.kill(os.getpid(), 9)" {scenario} {network_dir} {out}'
PRINT_OOM_ADJ = (
    "{python} -c \"import sys; sys.exit(open('/proc/self/oom_score_adj').read())\" "
    "{scenario} {network_dir} {out}"
)


def test_sigkill_without_timeout_is_memory_limit(client_factory, monkeypatch):
    if sys.platform == "win32":  # no signals on Windows: os.kill(pid, 9) exits with code 9
        monkeypatch.setattr(worker, "_SIGKILL_RETURNCODE", 9)
    client = client_factory(engine_cmd=SELF_KILL)
    job = run_job(client, scenario("oom-killed"))
    assert job["status"] == "failed", job
    assert job["error"]["code"] == "memory_limit"
    assert "OOM" in job["error"]["message"] and "SIGKILL" in job["error"]["message"]


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="oom_score_adj is Linux-only")
def test_engine_child_prefers_itself_as_oom_victim(client_factory):
    client = client_factory(engine_cmd=PRINT_OOM_ADJ)
    job = run_job(client, scenario("oom-adj"))
    assert job["error"]["code"] == "engine_failed"
    assert job["error"]["message"].rstrip().endswith("1000"), job["error"]["message"]
