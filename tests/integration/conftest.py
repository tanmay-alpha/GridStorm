"""Fixtures for the GridStorm integration tests.

Two families:
* API black-box tests (use the ``client`` fixture) — skipped unless GRIDSTORM_API_URL is set.
* Offline checks of committed datasets/artifacts (``test_offline_*``) — always run, stdlib only.

Environment:
  GRIDSTORM_API_URL            base URL of a running API (e.g. http://127.0.0.1:8120 or the Render
                               URL).
  GRIDSTORM_LIVE_JOBS=1        enable tests that submit real simulation jobs (marker ``live``).
  GRIDSTORM_TEST_JOB_TIMEOUT_S seconds to wait for a job to finish (default 900).
  GRIDSTORM_TEST_JWT_SECRET    the server's SUPABASE_JWT_SECRET, ONLY for local test servers;
                               enables cross-user isolation tests with self-minted tokens.
  GRIDSTORM_TEST_ALLOWED_ORIGIN an origin the server allows via CORS (default http://localhost:5173).
  GRIDSTORM_TEST_RATE_LIMIT=1  enable the test that exhausts the POST rate limit.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

import httpx
import pytest

API_URL = os.environ.get("GRIDSTORM_API_URL", "").rstrip("/")
JOB_TIMEOUT_S = float(os.environ.get("GRIDSTORM_TEST_JOB_TIMEOUT_S", "900"))
JWT_SECRET = os.environ.get("GRIDSTORM_TEST_JWT_SECRET") or None
ALLOWED_ORIGIN = os.environ.get("GRIDSTORM_TEST_ALLOWED_ORIGIN", "http://localhost:5173")
REPO_ROOT = Path(__file__).resolve().parents[2]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_all = pytest.mark.skip(reason="GRIDSTORM_API_URL not set")
    skip_live = pytest.mark.skip(reason="set GRIDSTORM_LIVE_JOBS=1 to submit real jobs")
    skip_rl = pytest.mark.skip(reason="set GRIDSTORM_TEST_RATE_LIMIT=1 to exhaust rate limits")
    for item in items:
        if not API_URL and "client" in getattr(item, "fixturenames", ()):
            item.add_marker(skip_all)
        if "live" in item.keywords and os.environ.get("GRIDSTORM_LIVE_JOBS") != "1":
            item.add_marker(skip_live)
        if "ratelimit" in item.keywords and os.environ.get("GRIDSTORM_TEST_RATE_LIMIT") != "1":
            item.add_marker(skip_rl)


def make_token(sub: str, secret: str, *, aud: str = "authenticated", **extra) -> str:
    import jwt

    now = int(time.time())
    claims = {"sub": sub, "aud": aud, "role": "authenticated", "iat": now, "exp": now + 3600}
    claims.update(extra)
    return jwt.encode(claims, secret, algorithm="HS256")


@pytest.fixture(scope="session")
def api_url() -> str:
    return API_URL


@pytest.fixture(scope="session")
def client() -> httpx.Client:
    with httpx.Client(base_url=API_URL, timeout=120.0, follow_redirects=False) as c:
        yield c


@pytest.fixture(scope="session")
def scenarios(client: httpx.Client) -> list[dict]:
    from gs_helpers import iter_pages

    return iter_pages(client, "/api/v1/scenarios", limit=100)


@pytest.fixture(scope="session")
def acdc_preset(scenarios: list[dict]) -> dict:
    """A preset scenario record targeting ac-dc-meshed with the PyPSA engine."""
    for rec in scenarios:
        spec = rec.get("spec") or {}
        if (
            rec.get("preset")
            and spec.get("dataset", {}).get("network_id") == "ac-dc-meshed"
            and spec.get("execution", {}).get("engine") == "pypsa"
        ):
            return rec
    pytest.fail("no PyPSA preset for ac-dc-meshed is exposed by GET /api/v1/scenarios")


@pytest.fixture
def unique_id() -> str:
    return f"it-{uuid.uuid4().hex[:12]}"
