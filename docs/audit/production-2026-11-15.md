# Production audit — 2026-11-15 (UTC)

## Scope / evidence

Target: `main` commit `1c05c2391d32e5248c7039626ec030ce1f0277c1`.

- **Actual deployed frontend:** Vercel API reported deployment READY and SHA identical to `main`, aliased at https://gridstorm.vercel.app.
- **Live page context:** inspected an existing browser tab for https://gridstorm.vercel.app/?network=scigrid-de. Its page displayed 585 buses, 948 lines/transformers, 1,423 generators, 38 storage units, nine data assumptions and a populated map legend. This was a read-only page inspection, **not a fresh interactive click-through**.
- **Live backend telemetry:** Render service `gridstorm-api` on free Frankfurt instance; logs show `GET /health` returning 200, network assets returning 200, and `job ... finished: completed` after the previously reported IEEE 14-bus simulation. Historic build failures occurred earlier and must not be confused with current deployment failure.
- **CI:** commit `1c05c23` GitHub workflow passed, with Playwright against a local API and Vite preview. This does **not** establish live Vercel-to-Render behavior on every route.
- **Source:** frontend routes, Studio, Explorer, Run, Compare, data hooks, API routers, storage adapter, configuration, Render blueprint, and existing tests.
- **Not directly verified in this audit:** production Supabase SQL/RLS policies (connected Supabase account did not expose the GridStorm project), a fresh live POST simulation, browser console/network waterfalls, visual screenshots, mobile touch behavior, or post-restart artifact retrieval. These must not be called passed.

## P0 / P1 findings

| Severity | Finding | Evidence | Acceptance criteria |
| --- | --- | --- | --- |
| P0 | Result files are ephemeral while job records persist | `jobs/results.py::load_result_bytes` loads object from configured store; `config.py` defaults to `local`; Render free disk ephemeral; user reports no R2 creds | Complete a small run, redeploy/restart worker, and retrieve the same full result/export by SHA256. Use S3-compatible or Supabase Storage object backend with durable credentials; verify old jobs. |
| P1 | Known-ineligible scenarios remain submit-able, reliably giving HTTP 422 | `StudioPage.tsx` shows forecast `live_execution_unavailable` and previously left the Run button enabled; existing E2E intentionally asserted 422 | Disable Run when live=false and no matching precomputed scenario; offer a runnable alternative; unit and Playwright tests. **Addressed in PR #7, pending CI/review.** |
| P1 | Users have no obvious first-click demo flow | Explorer opens directly to asset filters, then lengthy metadata | Prominent working example taking users to a validated crisis, guided baseline/outage comparison. **First CTA in PR #7; guided workflow still pending.** |
| P1 | Important state can look broken during free-tier cold start | API is on Render free, health polling every 30s, errors mention 30–60s wake time | Dedicated waking/connecting state with retry/backoff and no hanging generic skeleton; measure real cold-start latency. |
| P1 | Production browser journey not part of deployment gate | `ci.yml` E2E uses Vite preview + local API; `continue-on-error` on PRs | Add protected, low-impact, post-deploy smoke tests against both public origins for GET/status/map and a bounded isolated demo; do not make the public database a test dump. |

## P2 findings and improvements

1. **Performance:** `useNetworkAssets` downloads 9 categories and pages them at 1,000 rows before `ExplorerPage` has data. Render logs show a burst of 9+ requests when changing network, including multiple generator pages for SciGRID. Use the existing `/networks/{id}/geojson` endpoint for a fast first map paint; fetch expensive asset detail tables only when selected or required by Studio. Cache by network content hash.
2. **Information hierarchy:** eight equally weighted top-level routes mix Explorer/Studio/Compare/Library with research modules. Group into `Explore → Simulate → Compare → Library`, put advanced analysis in a secondary Research group; ensure keyboard and mobile navigation tests.
3. **Explorer sidebar:** full dataset provenance, source URLs, flags, carrier list and filters compete with the map. Keep provenance badges visible but collapse technical field details; **initial change in PR #7**. Reintroduce warnings contextually where numerical claims are displayed.
4. **Map legibility:** a voltage legend plus many individual generator-carrier labels can cover much of a smaller map. Consider a collapsible legend, carrier grouping and viewport-size checks. Avoid visually suggesting OSM assets are electrically verified.
5. **Simulation affordances:** distinguish `Run live`, `Open verified precomputed result`, and `Cannot run on hosted plan`, using server-sourced availability. Prevent predictable failures, but retain backend enforcement.
6. **Compare:** add a one-click `Compare with baseline` action on Run page, choosing/creating a compatible baseline and clearly explaining comparability.
7. **Presentation:** strengthen titles and workspace hierarchy, make units obvious, prioritize map/result cards, keep accessibility/contrast and data provenance.

## Operational controls

- Verify `GET /ready` returns `database.kind=postgres` in production and `storage` identifies the active artifact backend. An HTTP 200 from `/health` alone is insufficient.
- Confirm Render is on the intended deployed Git SHA and Vercel uses the intended `VITE_API_BASE_URL`.
- Check CORS for the production and preview Vercel hostnames; do not widen to `*` for authenticated calls.
- Evaluate guest demo job quotas, idempotent result reuse, and how anonymous public/unlisted scenarios are managed.
- Keep all API keys in backend secrets, not in Vite's `VITE_` variables.

## Proposed production E2E acceptance journey

1. From a fresh desktop and mobile browser: load homepage; check correct network/route and no JS errors, inaccessible controls or overflow.
2. Switch to IEEE 14-bus; validate real map click, asset detail and legend.
3. In Studio choose built-in IEEE 14 baseline and outage. Confirm validation and execution status, plus accurate live/precomputed labeling.
4. Submit one bounded test job in an explicitly designated demo namespace, poll until terminal, check solver objective and result bytes against the recorded sha256.
5. Navigate back, open completed run and generate JSON/Markdown exports.
6. Compare the two compatible jobs, validate URL sharing and map/replay, verify that a different-network pair is refused.
7. Test SciGRID precomputed preset and ensure edited SciGRID scenarios are stopped **before** POST submission.
8. Confirm library/catalog and research pages load; check accessibility (keyboard/mobile), browser console, and browser performance timings.
9. Repeat artifact retrieval after controlled backend restart **only in a safe maintenance/test window**, without destroying production state.

## Design target

A map-first research workbench, not an overloaded admin panel: **Understand the grid → Choose a crisis → Run a scientific model → Compare with baseline → Export evidence**. Display scientific provenance without allowing metadata to crowd out the primary user task.

## Change control

PR #7 is intentionally a **draft** and frontend-only. Keep production `main` unchanged pending tests. No numerical algorithms, PostgreSQL migrations, or deployment environment variables were modified here.
