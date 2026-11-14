# API container memory under a 512 MB limit (VER-007 root cause)

Measured 2026-11-15 on a local Docker build of `services/api/Dockerfile` (working tree at `7056d49`).
The container ran with the same limit as Render free: `--memory=512m --memory-swap=512m`.
Host: Docker 29.9.2, WSL2 kernel 6.18.33.2, cgroup v2. Render has not been instrumented; see
[Limits](#limits).

## Verdict

**VER-007 is a container OOM.** The kernel kills the **API process (uvicorn, PID 1)**, not the
solver child. That takes the whole service down: 502s, dropped connections, and a fresh ephemeral
state on restart. The 512 MB budget is exceeded by the **sum** of two processes, each of which
imports `pypsa`:

| Component | Resident memory | Where it comes from |
|---|---|---|
| API, idle | 91 MB RSS (cgroup 79–93 MB) | FastAPI, SQLAlchemy, uvicorn |
| API after the first `/networks/{id}/analytics/*` call | **379–409 MB RSS**, never released (cgroup ≈ 270 MB) | `AnalyticsService` imports `pypsa` in-process |
| Solver child (`python -m gridstorm_pypsa run`) | **peak 347–348 MB RSS** (≈ 216 MB anon) | `import pypsa` alone is 294 MB RSS |

Network data barely matters: the `network.nc` files are 82–172 KB for the three live networks and
1.5 MB for scigrid-de. Almost all of the memory is library import cost. `import pypsa` 1.4.0 pulls in
`pypsa.plot.statistics` (seaborn, matplotlib, plotly) and `pypsa.clustering` at import time.

The per-job watchdog (`GRIDSTORM_JOB_MEMORY_MB`) only looks at the solver tree. It cannot protect the
container. A cap of 400 MB lets the solver reach 348 MB while the API holds 400+ MB. A cap of 330 MB
kills every job, because the solver itself needs 348 MB.

## Method

* `sampler.py`, started with `docker exec` inside the container, recorded `memory.current`,
  `memory.peak` and `memory.stat` every 0.25 s. It also recorded `VmRSS`, `VmHWM`, `RssAnon` and
  `RssFile` for every process. In parallel, `docker stats --no-stream` ran in a loop on the host
  (about one sample every 2 s).
* Load came from the host through `http://127.0.0.1:8150`, with presets and `reuse: false`.
  `GRIDSTORM_EXECUTION_MODE=live`, `GRIDSTORM_MAX_CONCURRENT_JOBS=1`, `GRIDSTORM_JOB_TIMEOUT_S=180`,
  and live networks `ac-dc-meshed,pglib-case14-ieee,pglib-case118-ieee`, all as in `render.yaml`.
* The "stress" pass mimics the integration-suite load. It submits 3 jobs back to back, calls the 3
  analytics kinds on 5 networks (scigrid-de, pypsa-eur-be → 404, and the 3 live ones), and downloads
  all 53 artifacts. A second pass with 1 more job follows on the same container.
* OOM evidence came from `docker inspect -f '{{.State.OOMKilled}} {{.State.ExitCode}}'`, from the
  container's `memory.events`, and from the kernel log (`docker run --rm --privileged alpine dmesg`).

## Results

### Solver child RSS by stage (cap disabled, API warm with analytics)

From run D (`GRIDSTORM_JOB_MEMORY_MB=0`). Values are the maximum of the 0.25 s samples within each
stage. `VmHWM` is the kernel's exact high-water mark for the process. "queued" covers interpreter
start and imports, before the engine prints its first `STAGE` line.

| Stage | ac-dc-meshed-baseline RSS / anon (MB) | pglib-case118-ieee-baseline RSS / anon (MB) |
|---|---|---|
| queued (imports) | 249 / 159 | 278 / 178 |
| loading_network | **326 / 206** | **330 / 210** |
| building_model | 333 / 211 | 335 / 212 |
| solving | 339 / 212 | — (no sample) |
| postprocessing / done | 347 / 216 | 348 / 217 |
| **VmHWM (exact peak)** | **347** | **348** |

The 3 uncapped runs on a cold API (run B) reached the same peak: 346 / 347 / 346 MB for ac-dc-meshed,
case118 and case14. Each job took 3–4 s locally.

With `GRIDSTORM_JOB_MEMORY_MB=330` (run A), **3 of 3 jobs failed** with `memory_limit`
("engine resident memory 330–331 MB exceeded the 330 MB limit") in stage `loading_network`. That
matches the live data point from Render. RSS reaches 330 MB at the end of `loading_network`, and the
true peak is 348 MB.

### Container totals (cgroup `memory.current`, MB; limit 512)

| Run | Settings | Load | cgroup peak | `docker stats` max (MiB) | API RSS max | Outcome |
|---|---|---|---|---|---|---|
| idle | cap 330 | none | 79–93 | — | 91 | — |
| B | cap 0 | 3 sequential jobs, no analytics | 305 | 298.8 | 93 | 3/3 completed |
| A | cap 330 | same | 300 | 299.4 | 94 | **3/3 failed `memory_limit`** |
| first probe | cap 330 | analytics, then 1 job | **511** | — | 386 | job failed `memory_limit`; `memory.events max` 38 |
| C | cap 400 | analytics, then 2 jobs | 495 | 487.7 | 387 | 2/2 completed, 17 MB headroom |
| D | cap 0 | analytics, then 2 jobs | 495 | 495.2 | 387 | 2/2 completed |
| E | cap 400 | stress, then stress again | **512** | 512.0 | 409 | pass 1: 3/3 completed. Pass 2: **OOMKilled=true, exit 137, API killed** |
| F | cap 400 | stress ×2 | 512 | 510.6 | 321 | 4/4 completed. `memory.events max` = 1,192,250 (reclaim thrash); pass took 98 s vs 24 s |
| G | cap 400, `MALLOC_ARENA_MAX=2` | stress ×2 | 512 | 508.9 | 408 | 4/4 completed, at the ceiling (`max` 445) |
| H | G + `GRIDSTORM_NETWORK_CACHE_SIZE=1` | stress ×2 | 512 | 506.2 | 408 | 4/4 completed, at the ceiling (`max` 414) |
| **J** | cap 400, **no analytics calls** | stress ×2 minus analytics | **355** | 341.4 | 108 | **4/4 completed, 53/53 artifacts, 157 MB headroom** |

Kernel log for run E's kill:

```
oom-kill:constraint=CONSTRAINT_MEMCG ... task=uvicorn
Memory cgroup out of memory: Killed process 2654 (uvicorn) anon-rss:284440kB, file-rss:133816kB oom_score_adj:0
  task table: uvicorn rss 104564 pages (anon 71110, file 33454); engine python rss 87954 pages (anon 54759, file 33195)
```

With analytics loaded, the cgroup sits at 492–512 MB for every job, so the outcome is intermittent.
Whether the kernel can still reclaim file pages decides between thrash (F) and an OOM kill (E). This
matches VER-007: one suite run failed and the next one passed.

### OOM victim selection (480 MB limit, to force the OOM deterministically)

| Run | Settings | Outcome |
|---|---|---|
| K | cap 400 | **API killed** (`OOMKilled=true`, exit 137). dmesg: `Killed process (uvicorn) anon-rss:268580kB oom_score_adj:0`. Client saw `RemoteDisconnected`. |
| L | cap 400, engine started with `oom_score_adj=1000` | **API survived** (`/health` 200, 53/53 artifacts 200). The kernel killed the solver 4 times (dmesg: `Killed process (python) ... oom_score_adj:1000`). `memory.events oom_kill 4`. Each job ended `failed` / `engine_failed` "engine exited with code -9". |

Run L used an env-only wrapper, `GRIDSTORM_ENGINE_CMD=sh -c 'echo 1000 > /proc/self/oom_score_adj && exec "$0" -m gridstorm_pypsa run --scenario "$1" --network-dir "$2" --out "$3"' {python} {scenario} {network_dir} {out}`.
The unprivileged UID 10001 can raise its own `oom_score_adj`; this was verified in the image.

### Env-only mitigations tested

* `MALLOC_ARENA_MAX=2`: no measurable effect. API RSS after analytics was 408 MB (G) vs 406–409 MB
  (E), and solver peaks were unchanged (344–346 MB). The memory is import-time module and extension
  state, not fragmented malloc arenas.
* `GRIDSTORM_NETWORK_CACHE_SIZE=1`: no effect (408 MB). The cached `pypsa.Network` objects are small;
  what stays resident is the `pypsa` import.
* uvicorn workers: the image already runs one uvicorn process with no `--workers`, so there is
  nothing to lower.

## Recommendations

1. **Take `pypsa` out of the API process** (fixes the root cause; `services/api` change). Run J
   measured this case: cgroup peak 355 MB vs 495–512 MB, with 157 MB headroom. Two ways to do it:
   * **Preferred: precompute analytics.** The results are deterministic for the unsolved input network
     and are already memoised per (network, sha256, kind, filters). Generate them at build or import
     time, then serve the JSON, so the API never imports `pypsa`.
   * Or run `gridstorm_analytics.compute` in a short-lived subprocess, serialised through the same
     single job slot as the solver. A separate analytics subprocess also costs about 300 MB
     (`import gridstorm_analytics` = 299 MB RSS), so it must not overlap a solver run on 512 MB.
2. **Make the solver the OOM victim** (one line in `jobs/worker.py`, or the env-only wrapper above
   as a stop-gap). Write `1000` to `/proc/self/oom_score_adj` in the child, for example with
   `preexec_fn`. Run L shows this turns a whole-service restart into one failed job. Also map
   "exit −9 together with a `memory.events` `oom_kill` increase" to `error.code = memory_limit`,
   not `engine_failed`.
3. **Job cap: keep `GRIDSTORM_JOB_MEMORY_MB=400`; never go below 384.** The solver's exact peak is
   348 MB (VmHWM, case118 and ac-dc-meshed), and RSS is already 326–330 MB in `loading_network`. A
   330 cap fails 100 % of live jobs (3/3 locally, 3/3 on Render). 384 MB is the peak plus 10 %. The
   cap only becomes a real container guard once item 1 lands: API about 110 MB + solver 348 MB ≈
   355 MB cgroup (run J).
4. Optional hygiene: set `MPLCONFIGDIR=/tmp/matplotlib` in the runtime image. Every solver import of
   matplotlib (pulled in by `pypsa`) logs `mkdir -p failed for path /app/.config/matplotlib:
   Permission denied`, because `HOME=/app` is read-only for UID 10001.
5. Not recommended: `MALLOC_ARENA_MAX`, a smaller network cache, or a uvicorn worker change (no
   measured effect, see above).

## Limits

* Measured on Docker Desktop (WSL2) with all host CPUs, not on Render's free instance (512 MB, shared
  0.1 CPU). Docker Desktop charged almost no file pages to the cgroup (`file` 0–35 MB). [INFERENCE]
  On Render, the slower CPU stretches each job (about 40 s live vs 3–4 s here). Analytics, artifact
  reads and the solver then overlap for longer, which makes the 492–512 MB window more likely, not
  less. Render's own metrics for 2026-11-14 21:54–21:56 UTC were not available to this probe.
* The sampling interval is 0.25 s. The per-stage maxima are sample maxima; the overall solver peak
  is the exact `VmHWM`.

## Fix applied

Measured 2026-11-15 on a local Docker build of the working tree (on top of `5e043cd`), same host,
same method and the same `sampler.py` / `drive.py` load as above.

Changes:

* **No `pypsa` in the API process.** `services/analytics/scripts/precompute_analytics.py` (run with
  the `services/analytics` environment) computes every `gridstorm_analytics` kind (`capacity`,
  `energy_balance`, `costs`, `summary`) for every catalog network. It writes
  `data/networks/<id>/analytics/<kind>.json` and an `index.json` holding the `network.nc` sha256,
  the sha256 of each file, the generator command, and the versions of `pypsa`, pandas, numpy and
  Python. The output is deterministic: two runs produced byte-identical files. `AnalyticsService` only reads
  these files. It verifies their sha256 (500 `analytics_integrity_error`) and returns 503 when they
  are missing (`analytics_not_precomputed`) or were built from a different `network.nc`
  (`analytics_stale`). Responses keep their shape and `provenance: "calculated"`, and gain
  `execution_mode: "precomputed"` plus a `precomputed` block (file sha256, network sha256, generator
  versions). Carrier and country filters on `capacity` and `costs` are derived from the unfiltered
  rows. That is exact for unsolved networks. Any other filtered request returns 422
  `analytics_filter_not_precomputed`. Tests compare every committed file, and the filter
  combinations, against a live `gridstorm_analytics.compute`. Another test runs the app in a
  subprocess and asserts that `pypsa` is not in `sys.modules` after it has served every kind.
  `GRIDSTORM_ANALYTICS_TIMEOUT_S` and `GRIDSTORM_NETWORK_CACHE_SIZE` are removed. Precomputing also
  exposed a non-deterministic `summary`: networks whose only snapshot is PyPSA's default `"now"`
  label reported the wall-clock time as `snapshot_start`/`snapshot_end`. These fields are now null
  for such networks.
* **Solver child is the OOM victim.** On Linux the worker starts the engine with a `preexec_fn` that
  writes `1000` to `/proc/self/oom_score_adj`. If the engine exits through SIGKILL (returncode −9)
  and the watchdog, timeout or cancel did not send the signal, the job is classified as
  `memory_limit` ("killed by SIGKILL … kernel OOM killer … (OOM)"), not as `engine_failed`.
* `MPLCONFIGDIR=/tmp/matplotlib` in the runtime image, which stops the matplotlib `mkdir` warning.

| Run | Settings | Load | cgroup peak (MB) | API RSS (MB) | Engine RSS max (MB) | Outcome |
|---|---|---|---|---|---|---|
| E (before) | 512 MB, cap 400 | stress ×2 | 512 | 409 | 347 | pass 2: **OOMKilled, API killed** |
| **M (after)** | 512 MB, cap 400 | stress ×2 (4 jobs, 2 × 15 analytics calls, 2 × 54 artifact downloads) | **350.7** (`memory.peak`) | 91–107 (VmHWM 111) | 347 | **4/4 jobs completed**, analytics 24/24 200 (6 × 404 for `pypsa-eur-be`, which is not in the catalog), 108/108 artifacts 200, `OOMKilled=false`, `memory.events max 0 / oom_kill 0` |
| **N (after)** | **300 MB** (forced OOM), cap 0 | 2 sequential jobs | 300 (limit) | — | — | job 1 completed. Job 2 **failed `memory_limit`** ("…kernel OOM killer…(OOM)"). dmesg: `Killed process (python) … oom_score_adj:1000`. **API survived**: `/health` 200, PID 1 `oom_score_adj` 0, restarts 0. Docker still sets `OOMKilled=true` because any OOM kill in the container sets it. |

With the fix, the 512 MB container peaks at 351 MB under the suite-like load, which leaves 161 MB of
headroom. This matches run J (355 MB). The API stays at 91–111 MB however many analytics calls it
serves. The remaining peak is the solver child (VmHWM 347 MB). The 400 MB job cap now protects the
container: 111 + 347 < 512. If the container still runs out of memory, the kernel kills the solver
and the API keeps running. Render itself was not re-measured.
