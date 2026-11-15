# GridStorm 3.0 security and reliability audit

Date: 2026-11-15. Branch `release/gridstorm-3.0` (base `ae4ee9a`). Production at audit time: API
`https://gridstorm-api.onrender.com` (`/health` git_sha `dd185d17e9fe…`), web
`https://gridstorm.vercel.app`. Production access was read-only: GETs/OPTIONS through the public
URLs and one `BEGIN READ ONLY` database transaction that was rolled back. No jobs were created, no
load was generated, nothing was deployed. Secret values were never printed; only variable names.

Result legend: **PASS** (checked, holds), **FIXED** (defect found and fixed in source, with a
regression test; production still runs the old code until deployed), **FINDING** (risk recorded,
not changed this round), **UNVERIFIED** (could not be checked with the available access).

## Summary

| # | Check | Result |
| --- | --- | --- |
| 1 | Rate-limit client identity behind Render's proxy (X-Forwarded-For spoofing) | FIXED |
| 2 | uvicorn `--proxy-headers --forwarded-allow-ips='*'` interaction | FIXED |
| 3 | Cancellation race: cancel recorded as `failed` | FIXED |
| 4 | Anonymous simulation quotas (per-client token buckets) | PASS (after 1) |
| 5 | Global queue cap / job concurrency cap | PASS (new test for the queue cap) |
| 6 | Cross-user result isolation, owner-safe reuse, artifact authorization | PASS |
| 7 | Anonymous jobs can be cancelled by anyone | FINDING (documented demo rule; kept by decision) |
| 8 | One client can fill the global queue | FIXED (per-client active-job cap) |
| 9 | Storage confinement and bucket privacy | PASS |
| 10 | Log sensitivity (tokens, secrets, engine environment) | PASS (new tests) |
| 11 | API security headers and CORS (local + production) | PASS |
| 12 | Web security headers | FIXED in `apps/web/vercel.json` (not yet deployed) |
| 13 | Dependency vulnerability audits (npm, pip-audit) | PASS (0 known) |
| 14 | Production `/health`, `/ready`, durable storage | PASS |
| 15 | Previously completed results retrievable with matching sha256 | PARTIAL: 2/11 available and verified; 9 explicitly HTTP 410 |
| 16 | Web bundle free of server secrets | PASS (21 JS files) |
| 17 | Database RLS / grants (read-only, rolled back) | PASS for what production data allows; private-row isolation UNVERIFIED in production (no private rows exist) |

## 1. Client identity behind Render's proxy (FIXED)

### Defect

`ratelimit.client_ip` used the **first** (leftmost) `X-Forwarded-For` entry whenever
`GRIDSTORM_TRUST_PROXY=true` (set by the Dockerfile). Proxies append to that header, so the
leftmost entry is whatever the client sent. Proof against the pre-fix code (`git show
HEAD:services/api/src/gridstorm_api/ratelimit.py`, loaded in a scratch interpreter, input
`X-Forwarded-For: <spoof>, 203.0.113.7, 172.71.195.123, 10.226.90.65`):

```text
OLD client_ip -> 198.51.100.1
OLD client_ip -> 198.51.100.2
```

Each spoofed value got a fresh token bucket, so the per-IP POST and simulation quotas could be
bypassed by rotating the header. This was not exercised against production (no flooding); the
prior round's live experiment (`security-2026-11-15.md` SEC-07) was inconclusive.

### Render topology (evidence)

| Source | What it establishes |
| --- | --- |
| Render docs, [DDoS Protection](https://render.com/docs/ddos-protection) | "We're using Cloudflare's … DDoS protection infrastructure behind the scenes … When your web service is deployed to Render, it is automatically protected." |
| Cloudflare docs, [HTTP headers](https://developers.cloudflare.com/fundamentals/reference/http-headers/) | `CF-Connecting-IP` carries the IP connecting to Cloudflare, a single address; Cloudflare *appends* to an existing `X-Forwarded-For`; Cloudflare recommends `CF-Connecting-IP`/`True-Client-IP` over XFF; `True-Client-IP` is an Enterprise managed transform and "can be spoofed" if not added by Cloudflare. |
| Production response headers (this audit, `curl -D - /health`) | `Server: cloudflare`, `CF-RAY: …-BOM`, `x-render-origin-server: Render`, `rndr-id: …`. DNS: `gridstorm-api.onrender.com` → CNAME `gcp-us-west1-1.origin.onrender.com.cdn.cloudflare.net`. Cloudflare fronts this service. |
| Render feedback board, [Send the correct X_FORWARDED_FOR](https://feedback.render.com/features/p/send-the-correct-x-forwarded-for) | A user test reports Render "does not clear or reset any passed-in X-Forwarded-For header (it only appends)", so the first entry is spoofable, and observes `CF-Connecting-IP`/`True-Client-IP`. A Render staff reply on the same page says "we set the first IP in the list to the real client IP". The two statements conflict, so this audit does not trust the leftmost entry either way. |
| Header dump of a Render service, [arcjet-js#3899](https://github.com/arcjet/arcjet-js/issues/3899) (Apr 2025) | `x-forwarded-for: 81.97.145.24, 172.71.195.123, 10.226.90.65` (client, Cloudflare edge, Render-internal), `cf-connecting-ip` = `true-client-ip` = client, socket peer `::1`. |
| [Paul Kuruvilla, "Why does request.remote_ip work on Heroku but not Render?"](https://rohitpaulk.com/articles/render-rails-remote-ip) | Topology Client → Cloudflare → Render proxy → app; `X-Forwarded-For: <client>, <cloudflare edge>`, peer `10.x`. Reports Render support recommending `True-Client-Ip`/`Cf-Connecting-Ip` and saying the proxy appends to rather than strips XFF. |

Conclusion: the real client is (a) `CF-Connecting-IP`, which Cloudflare sets on every proxied
request, and (b) in `X-Forwarded-For`, the entry Cloudflare appended. Observations disagree on
whether that entry is 2nd or 3rd from the right (one or two Render hops after it).
`[INFERENCE]` A client cannot reach Render's proxies without passing Cloudflare: the public
hostname resolves only through Cloudflare. No Render documentation guarantees this.

### Fix

`ratelimit.TrustedProxyMiddleware` (outermost, installed only when `GRIDSTORM_TRUST_PROXY=true`)
rewrites `scope["client"]` and `scope["scheme"]` once:

1. `GRIDSTORM_CLIENT_IP_HEADER` (Render: `cf-connecting-ip`): used if present exactly once and a
   valid IP.
2. Otherwise the `GRIDSTORM_TRUSTED_PROXY_HOPS`-th XFF entry from the right (Render: `2`). With
   hops=2 the result is the real client under the 2-entry topology. Under the 3-entry topology it
   is the Cloudflare edge address, which collapses clients into a shared bucket but never lets a
   client choose the bucket. With fewer entries than hops, the socket peer is kept.
3. `X-Forwarded-Proto` sets the scheme (HSTS, redirect URLs).

Rate-limit buckets use `ratelimit.client_key`: the resolved IP, with IPv6 aggregated to /64,
because one subscriber normally controls a whole /64 and could otherwise rotate addresses.
Defaults outside Render are `trust_proxy=false`, header unset, hops `1`. The Dockerfile
`ENV` and `render.yaml` set `GRIDSTORM_TRUST_PROXY=true`, `GRIDSTORM_CLIENT_IP_HEADER=cf-connecting-ip`
and `GRIDSTORM_TRUSTED_PROXY_HOPS=2`. Documented in `services/api/.env.example` and
`docs/deployment/backend.md` (Operational limits).

### Tests (`services/api/tests/test_security_hardening.py`)

- `test_forwarded_client_ip_rules`: header precedence; missing, invalid or duplicated header falls
  back; Nth-from-right across repeated XFF lines; ports and IPv6 brackets; too few entries.
- `test_spoofed_leading_xff_does_not_change_bucket[cf-header|xff-hops]`: after one allowed POST,
  requests with one or two spoofed leading entries (or garbage) get **429**. A different real
  client still gets 200.
- `test_simulation_quota_cannot_be_dodged_with_spoofed_xff`: the same check for
  `POST /api/v1/simulations`.
- `test_forwarded_headers_ignored_without_proxy_trust`, `test_edge_header_ignored_unless_configured`,
  `test_ipv6_clients_share_their_slash_64`, `test_proxy_settings_from_env` (hops `0` is rejected).

## 2. uvicorn proxy headers (FIXED)

Uvicorn 0.54.0 `ProxyHeadersMiddleware` (read from the installed package):
`_TrustedHosts.get_trusted_client_address` returns `x_forwarded_for_hosts[0]` when
`always_trust` (`--forwarded-allow-ips='*'`). The leftmost, client-controlled entry therefore
became `request.client` and the access-log IP. The image now runs `--no-proxy-headers`. The app
middleware sets client and scheme, and mutates the same scope dict uvicorn logs from.

Local run (uvicorn on 127.0.0.1:8132, SQLite temp state, workers off), request headers
`X-Forwarded-For: 6.6.6.6, 203.0.113.7, 172.71.195.123, 10.226.90.65`, `CF-Connecting-IP: 203.0.113.7`,
`X-Forwarded-Proto: https`:

| Configuration | `GET /api/v1/simulations/` | Access log client |
| --- | --- | --- |
| New: `--no-proxy-headers`, trust proxy on, `cf-connecting-ip`, hops 2 | `307`, `location: https://127.0.0.1:8132/api/v1/simulations`, HSTS present | `203.0.113.7:0` |
| Old: `--proxy-headers --forwarded-allow-ips='*'` | `307`, `location: https://…`, HSTS present | `6.6.6.6:0` (spoofed) |

What depended on uvicorn's rewrite, and how each is handled now:

- `redirect_slashes` Location scheme: still https (table above; test
  `test_scheme_from_trusted_proxy_drives_redirects_and_hsts`).
- HSTS: now driven by the scheme the middleware sets; existing
  `test_networks.py::test_security_headers` passes unchanged.
- Access logs: now show the resolved client (table above).
- Rate limiter: covered in §1.

## 3. Cancellation race (FIXED, `jobs/worker.py`)

`WorkerPool.request_cancel` kills a registered engine directly. If it did so before the run loop's
first `proc.poll()`, the loop body never ran, `reason` stayed `None`, and a user cancellation was
recorded as an engine **failure**. Deterministic regression
`test_cancel_that_kills_engine_before_first_poll_is_cancelled_not_failed` (it triggers the cancel
inside the first `poll()`). Before the fix: `AssertionError … assert 'failed' == 'cancelled'`. After:
pass. Fix: when the process entry is popped after the loop, a pending cancel for the job sets
`reason = "cancel"`. The new queue-cap test also hit this race intermittently.

## 4–8. Quotas, caps, isolation, cancellation (source review + tests)

- **Anonymous quotas (PASS after §1).** Every POST costs one `post` token (60/min, burst 20). Simulation create and
  recompute also cost one `simulations` token (6/min, burst 3), per client key and per process.
  `test_scenarios_auth.py::test_rate_limit_on_posts` and `test_jobs.py::test_simulation_rate_limit` pass.
- **Concurrency cap (PASS).** `WorkerPool.start` runs exactly `max_concurrent_jobs` threads (Render: 1). Claims are
  atomic (`FOR UPDATE SKIP LOCKED` on Postgres, compare-and-set on SQLite).
  `test_jobs.py::test_cancel_running_and_queued` observes the second job `queued` while one runs.
- **Queue cap (PASS).** `create_job` refuses with 503 `queue_full`, `Retry-After: 60` once
  queued+running reaches `GRIDSTORM_MAX_QUEUED_JOBS` (50). New `test_global_queue_cap_returns_503`.
- **Isolation, reuse and artifacts (PASS).** `get_visible_job` (public-or-owner) guards detail, metrics, result,
  artifacts and recompute. `find_reusable` filters on `visible(SimulationJob, principal)` and
  verifies blob sha256. `/api/v1/artifacts` only serves committed precomputed files. Private results
  get `Cache-Control: private`. `test_authz_owner_isolation.py` (6 tests) and
  `test_jobs.py::test_private_jobs_are_isolated`/`test_cancel_requires_owner` pass.
- **FINDING (P2), anonymous cancel; kept by coordinator decision.** `access.can_modify` lets
  *anyone* cancel an ownerless (anonymous) job. This is the documented demo rule, but any visitor
  who can list `/api/v1/simulations` can cancel every anonymous job. Possible future options: a
  per-job cancel token returned only to the creator, or anonymous jobs cancellable only by the same
  client key.
- **FIXED (was P3), queue saturation.** The queue cap is global (50). Before the fix, a single
  client within its 6/min simulation quota could fill it in about 8 minutes, and then everyone got
  `queue_full`.

  Fix in `jobs/service.py::create_job`: only when a job would actually be enqueued (never for
  verified reuse or precomputed completion, and not for the operator recovery CLI), the caller's
  queued+running jobs are counted against `GRIDSTORM_MAX_ACTIVE_JOBS_PER_CLIENT` (default 2, `0`
  disables). At the limit the API answers 429 `too_many_active_jobs`, with details
  `{active_jobs, limit}` and a message telling the user to wait for or cancel a job. This check
  runs before the global 503 `queue_full`.

  How callers are identified:
  - Signed-in callers are counted by `owner_id`.
  - Anonymous callers are counted by the same client identity as the rate limiter (§1, so spoofed
    XFF does not help).
  - No schema change was needed: the anonymous identity is recorded as a pseudonymous
    `client` fingerprint (sha256 of the key, 32 hex chars) in the `simulation.create`/`.recompute`
    audit-event details. `audit_events` is server-only (RLS: 0 rows visible to anon/authenticated, §17).
  - The count joins those audit rows with the ownerless active jobs, which are bounded by the
    global queue cap.

  Limits:
  - Two simultaneous submissions can both pass the check (soft cap; the 6/min simulation bucket
    bounds this).
  - The fingerprint is a plain hash, so an IPv4 fingerprint is brute-forceable by anyone with
    database access. It is pseudonymous, not anonymous.

  Fail-before: `test_active_jobs_per_client_cap` got `assert 202 == 429` (third concurrent job
  queued). After the fix it passes. It covers the third job refused, a spoofed XFF refused, reuse
  allowed at the cap, separate allowances for another IP and for a signed-in user, and a freed
  slot after cancel.

## 9. Storage (PASS)

- `LocalArtifactStore._path` rejects keys that resolve outside the root.
  `SupabaseArtifactStore._object` rejects keys outside `^[A-Za-z0-9_][A-Za-z0-9._/-]*$` and any
  `..` segment. New `test_storage_keys_cannot_escape_the_store`.
- Missing-object errors never echo keys (`storage._missing`). httpx INFO logging, which would
  include object URLs, is raised to WARNING.
- Production DB (read-only): bucket `gridstorm-artifacts` `public = false`; **0** policies on
  `storage.objects`, so only the server's service role can read it.
- Image: the runtime user is uid 10001 `gridstorm`, and the app tree is root-owned (Dockerfile review).

## 10. Log sensitivity (PASS)

- `auth.py` logs only exception class names. Error handlers log the exception type plus traceback,
  never the request.
- New `test_tokens_are_never_logged`: a valid, an expired and a forged JWT, plus a full job run, at
  DEBUG level. Neither the token nor its signature appears in captured logs.
- The engine subprocess env drops `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL`,
  `AWS_SECRET_ACCESS_KEY` and `AWS_SESSION_TOKEN` (engine stdout/stderr is stored as the job log).
  New `test_engine_subprocess_never_receives_server_secrets` spies on `Popen` with all five set.
- Access logs now contain the real client IP (§2), which is personal data. Render log retention
  applies.

## 11–12. Headers and CORS

- **API (PASS).** `CORSMiddleware` uses an explicit origin allow-list, methods GET/POST/OPTIONS,
  headers Authorization/Content-Type, and no credentials. Production probe: preflight from
  `https://gridstorm.vercel.app` → 200 with exact ACAO and no `Access-Control-Allow-Credentials`;
  preflight from `https://evil.example` → ≥400, no ACAO. `/health` carries `nosniff`, `DENY`,
  `no-referrer` and HSTS `max-age=31536000; includeSubDomains`.
- **Web (FIXED, not deployed).** Production serves HSTS (`max-age=63072000; includeSubDomains; preload`,
  Vercel default) but not `X-Content-Type-Options`, `X-Frame-Options` or a CSP. The probe reports
  `WARN web headers missing ['x-content-type-options', 'x-frame-options', 'content-security-policy']`.
  `apps/web/vercel.json` now adds `nosniff`, `X-Frame-Options: DENY`,
  `Content-Security-Policy: frame-ancestors 'none'; object-src 'none'; base-uri 'self'`,
  `Referrer-Policy: strict-origin-when-cross-origin` and a Permissions-Policy denying camera,
  microphone, geolocation, payment and USB. `rg -i "geolocat|<iframe|<object|<base "` over
  `apps/web/src` found no use of them. A full script/connect CSP was not added: MapLibre workers,
  tile hosts and the API origin need a tested allow-list.

## 13. Dependency audits (PASS)

- `apps/web`: `npm audit --omit=dev` → `found 0 vulnerabilities` (npm 11.11.0, 418 lock entries).
- `services/api`: `uv export --frozen --no-dev` (88 pinned packages; the 4 local editable path
  packages were excluded), then `uvx pip-audit -r … --no-deps --disable-pip` (pip-audit 2.10.1) →
  `No known vulnerabilities found`. Key pins: fastapi 0.162.7, starlette 1.10.0, uvicorn 0.54.0,
  pyjwt 2.15.1, cryptography 50.0.2, httpx 0.28.1, h11 0.16.0, sqlalchemy 2.0.57, psycopg 3.3.9.
  No bumps were needed.

## 14–16. Production read-only verification

`python scripts/probe_production.py` (extended this round with durable-storage, header, CORS
preflight and bundle-scan checks) printed:

```text
PASS API /health 0.1.0
PASS API /ready {'database': 'ok', 'storage': 'ok', 'solver': 'ok', 'datasets': 'ok'}
PASS durable artifact storage supabase:gridstorm-artifacts write/read/delete round-trip ok
PASS API security headers
PASS CORS preflight: production origin allowed, foreign origin refused
PASS web HSTS; WARN web headers missing ['x-content-type-options', 'x-frame-options', 'content-security-policy']
PASS web bundle has no server secrets; JS files scanned: 21
PASS completed result retrievable and sha256 verified 458fddab
PASS completed result retrievable and sha256 verified 34424ec2
PASS lost artifact explicitly disclosed 5dafdc1a   (and f2fc0cf3 5323bc95 25e3fb2a 4104c5fc c800561d 06b4f635 0137980b 2d47898b)
PASS public read-only smoke
```

**Results (PARTIAL).** `/api/v1/simulations?limit=20` lists 11 jobs, all completed. The two
finished after the Supabase cut-over (`34424ec2` 01:19:23Z and its recompute `458fddab`
01:21:31Z) return HTTP 200, and body sha256 = `result_sha256` = `X-GridStorm-Result-SHA256`. The 9
finished between 23:41Z and 00:44Z, in the ephemeral local-store era (TODO POST-01), report
`result_available: false` and answer HTTP 410 `artifact_unavailable`: truthful, but the bytes are
gone. Four are precomputed `scigrid-de` jobs, which `/recompute` could restore byte-identically;
five are live `pglib-case14-ieee`. Recomputing would create jobs, so it was not done here.

**Bundle (PASS).** Crawled `index.html` plus 21 transitively referenced `/assets/*.js`. No match
for `service_role`, `SUPABASE_SERVICE`, `SUPABASE_JWT_SECRET`, `postgres(ql)://…@` or
`sk_(live|test)_…`. No `eyJ….eyJ….…` JWT was found at all.

## 17. Database RLS and grants

Credentials present locally (names only):

- Process env: `SUPABASE_DB_HOST/NAME/PASSWORD/PORT/USER`, all placeholders (the host is
  `YOUR_SUPABASE_DB_HOST`).
- `GridStorm/.vercel/.env.production.local`: Vercel build variables plus `VITE_API_BASE_URL`
  and `VERCEL_OIDC_TOKEN`, no DB credentials.
- External `../.secrets/supabase.env`: `POSTGRES_URL_NON_POOLING`, `SUPABASE_SERVICE_ROLE_KEY`,
  `SUPABASE_JWT_SECRET` and related names.
- CLIs: `render` and `vercel` present; `supabase` and `psql` absent.

One `BEGIN READ ONLY` transaction via `POSTGRES_URL_NON_POOLING` (role `postgres`, PostgreSQL
17.11), ended with `ROLLBACK`. Role switches used savepoints and `set_config('request.jwt.claims', …, true)`.

- Migrations recorded: `0001`, `0002`, `0003_job_indexes_and_client_grants.sql`. 0003 is now
  applied, which closes SEC-03/SEC-05 of the previous audit.
- 12/12 public tables have RLS enabled (FORCE off; the API's owner role bypasses RLS by design),
  with 15 policies. `anon`/`authenticated` hold **no** TRUNCATE/TRIGGER/REFERENCES grants.
- Visible row counts (owner role / anon / random authenticated user): jobs 11/11/11, scenarios
  14/14/14, comparisons 20/20/20, artifacts 29/29/29, metrics 11/11/11, profiles 0/0/0,
  **audit_events 33/0/0**, datasets 5/5/5. Anon-visible jobs equal public jobs.
- **UNVERIFIED in production:** isolation of *private* rows. Production has none (all 11 jobs and
  14 scenarios are public and ownerless), and creating fixtures would be a write. Isolation stays
  covered by the policy definitions, the previous round's rolled-back fixture exercise
  (`security-2026-11-15.md`, 38/38) and the API tests in §6.

## Fixes made this round

| File | Change |
| --- | --- |
| `services/api/src/gridstorm_api/ratelimit.py` | `TrustedProxyMiddleware`, `forwarded_client_ip`, `client_key` (IPv6 /64); removed leftmost-XFF `client_ip` |
| `services/api/src/gridstorm_api/config.py` | `client_ip_header` (`GRIDSTORM_CLIENT_IP_HEADER`), `trusted_proxy_hops` (`GRIDSTORM_TRUSTED_PROXY_HOPS`, ≥1) |
| `services/api/src/gridstorm_api/main.py`, `deps.py`, `security_headers.py` | middleware wiring; buckets keyed by `client_key`; HSTS from the resolved scheme |
| `services/api/src/gridstorm_api/jobs/worker.py` | cancel race fix (§3) |
| `services/api/Dockerfile` | `--no-proxy-headers`; Render proxy env |
| `render.yaml` | explicit proxy env (`true` / `cf-connecting-ip` / `2`); `GRIDSTORM_MAX_ACTIVE_JOBS_PER_CLIENT=2` |
| `apps/web/vercel.json` | web security headers |
| `scripts/probe_production.py` | durable storage, API headers, CORS preflight (allowed and foreign), web headers, bundle secret scan, all completed jobs in `limit=20` |
| `services/api/src/gridstorm_api/jobs/service.py`, `routers/simulations.py`, `deps.py` (`ClientKey`) | per-client active-job cap (§8) |
| `services/api/tests/test_security_hardening.py` | 16 regression tests (§1–3, 5, 8, 9, 10) |
| `services/api/.env.example` | proxy configuration and active-job cap documented |
| `docs/deployment/backend.md` | proxy configuration documented |
| `docker-compose.yml` | `GRIDSTORM_TRUST_PROXY=false` (direct local access, no proxy) |

## Remaining work

- Deploy, then re-run `scripts/probe_production.py`. The web-header WARN should disappear, and the
  new proxy code is only effective after the Render deploy. Production spoof resistance was not
  exercised live (no load tests).
- Optionally recompute the 4 lost precomputed `scigrid-de` results.
