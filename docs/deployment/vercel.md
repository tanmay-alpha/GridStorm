# Deploying the web app on Vercel

The frontend (`apps/web`) is a static React + Vite single-page app. It holds no secrets and talks
to the API (see [render.md](render.md)) over HTTPS.

## Project settings

| Setting | Value | Source |
|---|---|---|
| Project name | `gridstorm` | — |
| Root Directory | `apps/web` | monorepo layout |
| Framework preset | Vite | `apps/web/vercel.json` (`"framework": "vite"`) |
| Install command | `npm ci` (default; `apps/web/package-lock.json` is committed) | — |
| Build command | `npm run build` (= `tsc -b && vite build`) | `apps/web/vercel.json`, `apps/web/package.json` |
| Output directory | `dist` | `apps/web/vercel.json` |
| Node.js | 20+ (developed on Node 24) | — |

`apps/web/vercel.json` also defines:

- **SPA rewrite** `/((?!assets/).*)` → `/index.html`, so deep links such as `/runs/<id>` or
  `/contingency` load the app instead of returning 404. Files under `/assets/` are served as-is.
- **Immutable caching** for `/assets/(.*)` (`Cache-Control: public, max-age=31536000, immutable`);
  Vite fingerprints those filenames, so this is safe.

## Environment variables

| Variable | Required | Value |
|---|---|---|
| `VITE_API_BASE_URL` | yes | Public URL of the API, e.g. `https://gridstorm-api.onrender.com` (no trailing slash; trailing slashes are stripped in `apps/web/src/api/client.ts`). |

`VITE_*` variables are inlined into the JavaScript bundle **at build time** and are public. Never
put a database URL, JWT secret or Supabase service-role key in a `VITE_*` variable. After changing
`VITE_API_BASE_URL`, redeploy (a rebuild is required). If it is empty the app calls same-origin
`/api/...`, which only works with the local Vite dev proxy.

The API must allow the Vercel origin via CORS: set `GRIDSTORM_CORS_ORIGINS` on the API to the
deployed origin(s), comma-separated (e.g.
`https://gridstorm.vercel.app,https://gridstorm-git-main-<team>.vercel.app`) —
`services/api/src/gridstorm_api/config.py`. Preview deployments get different hostnames; add the
ones you need.

## Steps (dashboard)

1. *Add New → Project*, import `tanmay-alpha/GridStorm`.
2. Set *Root Directory* to `apps/web`; Vercel picks up `vercel.json`.
3. Add `VITE_API_BASE_URL` for Production (and Preview if desired).
4. Deploy. Pushes to `main` deploy to production; other branches get preview URLs.

## Steps (CLI)

```bash
npm i -g vercel
cd apps/web
vercel link          # choose/create project "gridstorm"
vercel env add VITE_API_BASE_URL production
vercel --prod
```

## Verify

- Open the deployed URL and a deep link (e.g. `/methods`) directly — it must render, not 404.
- The browser network tab shows requests to `${VITE_API_BASE_URL}/api/v1/...` succeeding without
  CORS errors. If the API is on Render's free plan, the first request after 15 idle minutes can
  take about a minute while the service spins up (see [render.md](render.md#free-tier-limits)).
