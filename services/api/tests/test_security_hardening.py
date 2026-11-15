"""Security regressions: client identity behind the trusted proxy (rate-limit keys), queue cap,
engine secret isolation, storage key confinement and token-free logs.

Render topology (docs/audit/security-3.0.md): client -> Cloudflare -> Render proxies -> app.
Cloudflare overwrites ``CF-Connecting-IP`` and *appends* the connecting address to any
client-supplied ``X-Forwarded-For``; Render's proxies append one or two more entries. A client can
therefore only control ``X-Forwarded-For`` entries to the LEFT of the real one.
"""

from __future__ import annotations

import logging
import uuid

import httpx
import pytest

from conftest import auth, make_token, run_job, scenario, wait_job
from gridstorm_api.config import Settings
from gridstorm_api.jobs import worker as worker_module
from gridstorm_api.ratelimit import client_key, forwarded_client_ip
from gridstorm_api.storage import LocalArtifactStore, SupabaseArtifactStore

ALICE = uuid.UUID("11111111-1111-4111-8111-111111111111")
CF_EDGE = "172.71.195.123"
RENDER_HOP = "10.226.90.65"
VALIDATE = "/api/v1/scenarios/validate"


def _hdrs(**values: str) -> list[tuple[bytes, bytes]]:
    return [(k.replace("_", "-").encode(), v.encode()) for k, v in values.items()]


def _render(client_ip: str, *spoofed: str) -> dict[str, str]:
    """Headers reaching the app on Render when the client sent ``X-Forwarded-For: spoofed``."""
    xff = ", ".join([*spoofed, client_ip, CF_EDGE, RENDER_HOP])
    return {"X-Forwarded-For": xff, "CF-Connecting-IP": client_ip}


# -- resolution rules ---------------------------------------------------------------------------


def test_forwarded_client_ip_rules():
    resolve = forwarded_client_ip
    # the configured edge header wins and leading XFF entries never matter
    h = _hdrs(x_forwarded_for="6.6.6.6, 203.0.113.7, 172.71.0.1", cf_connecting_ip="203.0.113.7")
    assert resolve(h, client_ip_header="cf-connecting-ip", proxy_hops=1) == "203.0.113.7"
    # fallback: N-th entry from the right, across repeated header lines, ports stripped
    h = _hdrs(x_forwarded_for="6.6.6.6, 203.0.113.7:5555") + _hdrs(x_forwarded_for=CF_EDGE)
    assert resolve(h, client_ip_header=None, proxy_hops=2) == "203.0.113.7"
    assert resolve(h, client_ip_header=None, proxy_hops=1) == CF_EDGE
    v6 = _hdrs(x_forwarded_for="[2001:db8::1]:443, 10.0.0.1")
    assert resolve(v6, client_ip_header=None, proxy_hops=2) == "2001:db8::1"
    # missing/invalid/duplicated edge header -> XFF fallback; too few entries -> socket peer
    for bad in ("", "not-an-ip", "1.2.3.4, 5.6.7.8"):
        h = _hdrs(x_forwarded_for="6.6.6.6, 203.0.113.7", cf_connecting_ip=bad)
        assert resolve(h, client_ip_header="cf-connecting-ip", proxy_hops=1) == "203.0.113.7"
    dup = _hdrs(cf_connecting_ip="6.6.6.6") + _hdrs(cf_connecting_ip="7.7.7.7")
    assert resolve(dup, client_ip_header="cf-connecting-ip", proxy_hops=1) is None
    assert (
        resolve(_hdrs(x_forwarded_for="203.0.113.7"), client_ip_header=None, proxy_hops=2) is None
    )
    assert resolve(_hdrs(x_forwarded_for="garbage"), client_ip_header=None, proxy_hops=1) is None


def test_bucket_keys_aggregate_ipv6_to_slash_64():
    assert client_key({"client": ("2001:db8:1:2::1", 0)}) == "2001:db8:1:2::/64"
    assert client_key({"client": ("2001:db8:1:2:ffff::9", 0)}) == "2001:db8:1:2::/64"
    assert client_key({"client": ("::ffff:203.0.113.7", 0)}) == "203.0.113.7"
    assert client_key({"client": ("203.0.113.7", 0)}) == "203.0.113.7"
    assert client_key({}) == "unknown"


def test_proxy_settings_from_env(monkeypatch):
    monkeypatch.setenv("GRIDSTORM_CLIENT_IP_HEADER", "CF-Connecting-IP")
    monkeypatch.setenv("GRIDSTORM_TRUSTED_PROXY_HOPS", "2")
    s = Settings.from_env()
    assert (s.client_ip_header, s.trusted_proxy_hops) == ("cf-connecting-ip", 2)
    monkeypatch.setenv("GRIDSTORM_TRUSTED_PROXY_HOPS", "0")
    with pytest.raises(ValueError, match="TRUSTED_PROXY_HOPS"):
        Settings.from_env()


# -- spoofing through the HTTP stack ------------------------------------------------------------


def _limited(client_factory, **overrides):
    return client_factory(rate_limit_post_per_min=0.001, rate_limit_post_burst=1, **overrides)


def _validate(client, headers):
    return client.post(VALIDATE, json={"scenario": scenario()}, headers=headers).status_code


@pytest.mark.parametrize(
    "proxy",
    [
        {"client_ip_header": "cf-connecting-ip", "trusted_proxy_hops": 2},  # Render config
        {"client_ip_header": None, "trusted_proxy_hops": 2},  # XFF-only fallback
    ],
    ids=["cf-header", "xff-hops"],
)
def test_spoofed_leading_xff_does_not_change_bucket(client_factory, proxy):
    client = _limited(client_factory, trust_proxy=True, **proxy)
    real = "203.0.113.7"
    if proxy["client_ip_header"] is None:  # Render topology with one internal hop fewer

        def headers(*spoofed):
            return {"X-Forwarded-For": ", ".join([*spoofed, real, CF_EDGE])}
    else:

        def headers(*spoofed):
            return _render(real, *spoofed)

    assert _validate(client, headers()) == 200
    for spoofed in (("198.51.100.1",), ("198.51.100.2", "198.51.100.3"), ("garbage",)):
        assert _validate(client, headers(*spoofed)) == 429, spoofed
    # a genuinely different client still has its own bucket
    other = "203.0.113.8"
    other_headers = (
        _render(other) if proxy["client_ip_header"] else {"X-Forwarded-For": f"{other}, {CF_EDGE}"}
    )
    assert _validate(client, other_headers) == 200


def test_simulation_quota_cannot_be_dodged_with_spoofed_xff(client_factory):
    client = client_factory(
        trust_proxy=True,
        client_ip_header="cf-connecting-ip",
        trusted_proxy_hops=2,
        rate_limit_sim_per_min=0.001,
        rate_limit_sim_burst=1,
    )
    real = "203.0.113.9"
    r = client.post(
        "/api/v1/simulations", json={"scenario": scenario("quota-1")}, headers=_render(real)
    )
    assert r.status_code == 202
    for i in range(3):
        r = client.post(
            "/api/v1/simulations",
            json={"scenario": scenario(f"quota-spoof-{i}")},
            headers=_render(real, f"198.51.100.{i}"),
        )
        assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    wait_job(client, client.get("/api/v1/simulations").json()["items"][0]["id"])


def test_forwarded_headers_ignored_without_proxy_trust(client_factory):
    client = _limited(client_factory)  # trust_proxy=False (default)
    assert _validate(client, {}) == 200
    for i in range(3):
        spoof = {"X-Forwarded-For": f"198.51.100.{i}", "CF-Connecting-IP": f"198.51.100.{i}"}
        assert _validate(client, spoof) == 429


def test_edge_header_ignored_unless_configured(client_factory):
    client = _limited(client_factory, trust_proxy=True)  # header None, hops 1
    # hops=1 -> rightmost entry (appended by the proxy itself); CF-Connecting-IP is not trusted
    assert _validate(client, {"X-Forwarded-For": "6.6.6.6, 10.0.0.1"}) == 200
    blocked = {"X-Forwarded-For": "7.7.7.7, 10.0.0.1", "CF-Connecting-IP": "8.8.8.8"}
    assert _validate(client, blocked) == 429


def test_ipv6_clients_share_their_slash_64(client_factory):
    client = _limited(client_factory, trust_proxy=True, client_ip_header="cf-connecting-ip")
    assert _validate(client, {"CF-Connecting-IP": "2001:db8:1:2::1"}) == 200
    assert _validate(client, {"CF-Connecting-IP": "2001:db8:1:2::dead:beef"}) == 429
    assert _validate(client, {"CF-Connecting-IP": "2001:db8:1:3::1"}) == 200


def test_scheme_from_trusted_proxy_drives_redirects_and_hsts(client_factory):
    # uvicorn runs with --no-proxy-headers: the app alone derives the scheme, so redirect_slashes
    # Location URLs and HSTS must still say https behind Render's TLS-terminating proxy.
    proxied = client_factory(trust_proxy=True, client_ip_header="cf-connecting-ip")
    https = {"X-Forwarded-Proto": "https", "CF-Connecting-IP": "203.0.113.7"}
    r = proxied.get("http://testserver/api/v1/simulations/", headers=https, follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].startswith("https://testserver/")
    assert "strict-transport-security" in r.headers
    r = proxied.get("/docs", headers=https)
    assert r.status_code == 200 and "strict-transport-security" in r.headers

    plain = client_factory()
    r = plain.get(
        "http://testserver/api/v1/simulations/",
        headers={"X-Forwarded-Proto": "https"},
        follow_redirects=False,
    )
    assert r.headers["location"].startswith("http://testserver/")
    assert "strict-transport-security" not in r.headers


# -- queue cap, engine isolation, storage keys, logs -------------------------------------------


def test_global_queue_cap_returns_503(client_factory):
    client = client_factory(max_queued_jobs=1)
    running = client.post(
        "/api/v1/simulations", json={"scenario": scenario("cap", assumptions=["fake:sleep=30"])}
    ).json()
    r = client.post("/api/v1/simulations", json={"scenario": scenario("cap-2")})
    assert r.status_code == 503 and r.json()["error"]["code"] == "queue_full"
    assert r.headers["retry-after"] == "60"
    assert client.post(f"/api/v1/simulations/{running['id']}/cancel").status_code == 200
    job = wait_job(client, running["id"], timeout=15)
    assert job["status"] == "cancelled", job


def test_cancel_that_kills_engine_before_first_poll_is_cancelled_not_failed(client, monkeypatch):
    # Race: request_cancel() kills the registered engine before the run loop's first poll(); the
    # loop body never runs, so the cancel must still be honoured after the loop.
    pool = client.app.state.ctx.pool
    real_popen = worker_module.subprocess.Popen

    def spy(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        original_poll = proc.poll
        fired = False

        def poll():
            nonlocal fired
            if fired:
                return original_poll()
            fired = True
            (job_id,) = list(pool._procs)  # registered by run() just before the loop
            pool.request_cancel(job_id)  # what POST /cancel does for a running job
            proc.wait(10)
            return proc.returncode

        proc.poll = poll
        return proc

    monkeypatch.setattr(worker_module.subprocess, "Popen", spy)
    r = client.post(
        "/api/v1/simulations", json={"scenario": scenario("race", assumptions=["fake:sleep=30"])}
    )
    job = wait_job(client, r.json()["id"], timeout=20)
    assert job["status"] == "cancelled", job
    assert job["error"]["code"] == "cancelled"


def test_active_jobs_per_client_cap(client_factory):
    client = client_factory(
        trust_proxy=True, client_ip_header="cf-connecting-ip", max_active_jobs_per_client=2
    )
    me, other = _render("203.0.113.20"), _render("203.0.113.21")

    def submit(name, headers, *, sleep=True):
        flags = ["fake:sleep=30"] if sleep else []
        body = {"scenario": scenario(name, assumptions=flags)}
        return client.post("/api/v1/simulations", json=body, headers=headers)

    done = submit("cap-src", me, sleep=False).json()
    assert wait_job(client, done["id"])["status"] == "completed"  # finished jobs never count
    active = [submit(f"cap-{i}", me).json()["id"] for i in range(2)]
    r = submit("cap-3", me)
    assert r.status_code == 429, r.text
    err = r.json()["error"]
    assert err["code"] == "too_many_active_jobs"
    assert err["details"] == {"active_jobs": 2, "limit": 2}
    assert "queued or running" in err["message"]
    # spoofed leading X-Forwarded-For entries do not open a new allowance
    assert submit("cap-spoof", _render("203.0.113.20", "198.51.100.77")).status_code == 429
    # a completed identical result is reused without enqueueing, so it is not capped
    reused = submit("cap-src", me, sleep=False)
    assert reused.status_code == 202 and reused.json()["reused"] is True
    # other clients and signed-in users have their own allowance
    active.append(submit("cap-other", other).json()["id"])
    alice = auth(ALICE)
    active += [submit(f"cap-alice-{i}", alice).json()["id"] for i in range(2)]
    r = submit("cap-alice-3", alice)
    assert r.status_code == 429 and r.json()["error"]["code"] == "too_many_active_jobs"
    # finishing (here: cancelling) a job frees the slot
    assert client.post(f"/api/v1/simulations/{active[0]}/cancel", headers=me).status_code == 200
    wait_job(client, active[0], timeout=15)
    active.append(submit("cap-after-cancel", me).json()["id"])
    for job_id in active[1:]:
        client.post(f"/api/v1/simulations/{job_id}/cancel", headers=alice)
        client.post(f"/api/v1/simulations/{job_id}/cancel")


def test_engine_subprocess_never_receives_server_secrets(client, monkeypatch):
    secrets = {
        "SUPABASE_JWT_SECRET": "jwt-secret-value",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-value",
        "DATABASE_URL": "postgresql://u:p@h/db",
        "AWS_SECRET_ACCESS_KEY": "aws-secret",
        "AWS_SESSION_TOKEN": "aws-token",
    }
    for k, v in secrets.items():
        monkeypatch.setenv(k, v)
    seen: list[dict[str, str]] = []
    real_popen = worker_module.subprocess.Popen

    def spy(*args, **kwargs):
        seen.append(dict(kwargs["env"]))
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(worker_module.subprocess, "Popen", spy)
    assert run_job(client, scenario("env-isolation"))["status"] == "completed"
    assert seen, "engine subprocess was not started"
    leaked = {k for env in seen for k in secrets if k in env}
    assert not leaked and all("PATH" in env for env in seen)


def test_storage_keys_cannot_escape_the_store(tmp_path):
    store = LocalArtifactStore(tmp_path / "artifacts")
    (tmp_path / "secret.json").write_text("{}")
    for key in ("../secret.json", "a/../../secret.json"):
        with pytest.raises(ValueError):
            store.get(key, expected_sha256="0" * 64)
    remote = SupabaseArtifactStore(
        "https://example.invalid",
        "service-role",
        "bucket",
        transport=httpx.MockTransport(lambda request: httpx.Response(500)),
    )
    try:
        for key in ("../x", "a/../../x", "/abs", ".hidden/x"):
            with pytest.raises(ValueError):
                remote.exists(key, fresh=True)
    finally:
        remote.close()


def test_tokens_are_never_logged(client, caplog):
    caplog.set_level(logging.DEBUG)
    good = auth(ALICE)["Authorization"].split(" ", 1)[1]
    expired = make_token(ALICE, expires_in=-60)
    forged = good[:-4] + ("AAAA" if not good.endswith("AAAA") else "BBBB")
    for token in (good, expired, forged, "not.a.jwt"):
        client.get("/api/v1/scenarios", headers={"Authorization": f"Bearer {token}"})
    run_job(client, scenario("log-scan"), headers={"Authorization": f"Bearer {good}"})
    for token in (good, expired, forged):
        assert token not in caplog.text
        assert token.split(".")[2] not in caplog.text  # not even the signature
