# Python dependency compatibility matrix

Date 2026-11-14. Question: which of PyPSA 1.4.x, pandapower 3.5.x and Grid2Op 1.12.x (plus linopy,
highspy, pandas) can share one Python environment? Answer is derived from the packages' published
requirements and confirmed by actually running the uv resolver.

## 1. Published requirements (PyPI JSON API, `https://pypi.org/pypi/<pkg>/json`)

| Package | Latest | `requires_python` | Relevant `requires_dist` (non-extra) |
|---|---|---|---|
| pypsa | 1.4.0 | >=3.11 | `pandas>=3.0`, `linopy>=0.9.0`, `highspy`, `xarray`, `numpy`, `scipy`, `networkx>=2` |
| linopy | 0.10.1 | >=3.11 | `numpy`, `scipy`, `xarray>=2024.2.0` |
| highspy | 1.16.0 | >=3.9 | `numpy` (licence MIT) |
| pandas | 3.1.1 | >=3.11 | `numpy>=2.0.2` (py<3.14) |
| pandapower | 3.5.6 | >=3.10 | **`pandas~=2.3`**, `numpy<2.5,>=1.26`, `scipy>=1.15`, `networkx~=3.6` (py>=3.11) |
| pandapower | 3.5.2 | — | `pandas~=2.3`, `numpy<2.4,>=1.26` (first 3.5.x with the `pandas<3` cap, per resolver message below) |
| pandapower | 3.1.2 | — | `pandas>=1.0`, `numpy` (no cap) |
| grid2op | 1.12.6 | >=3.8 | **`pandas<3,>=1.0.3`**, `pandapower>=3.1.1`, `scipy>=1.4.1`, `networkx>=2.4` |
| grid2op | 1.12.1 – 1.12.5 | — | `pandas<3,>=1.0.3`, `pandapower>=3.1.1` |
| grid2op | 1.12.0 | — | `pandas>=1.0.3` (no cap), `pandapower>=3.1.1` |
| lightsim2grid | 1.3.1 | >=3.8 | `numpy` |

PyPSA-Eur v2026.09.0 (`upstream/pypsa-eur/envs/environment.yaml`): L24 `highspy >=1.12.0`, L28
`linopy >=0.8,<0.9`, L34 `numpy >=1.26.4`, L36 `pandas >=3`, L43 `pypsa >=0.35.2`, L46
`python >=3.12`, L62 `xarray >=2026.1`. Its lock `envs/default_linux-64.pin.txt` pins python 3.13.15
(L27), pandas 3.0.1 (L48), highspy 1.13.1 (L50), xarray 2026.7.0 (L171), linopy 0.8.0 (L319),
**pypsa 1.2.4** (L328).

The structural conflict: **PyPSA ≥ 1.3 requires pandas ≥ 3; pandapower ≥ 3.5.2 and Grid2Op ≥ 1.12.1
require pandas < 3.**

## 2. Resolver runs

Tool: `uv 0.11.32 (3010295ae 2026-07-23 x86_64-pc-windows-msvc)`. Inputs in
`D:/New folder (4)/_compat-tmp/<name>.in` (outside the repo), isolated cache
`UV_CACHE_DIR=_compat-tmp/.uvcache`. Command per case:

```
uv pip compile --python-version <3.11|3.12> --no-header <name>.in
```

All cases were run for Python 3.11 (logs `<name>.log`, outputs `<name>.txt`) and re-run on
2026-11-14 for Python 3.12 with identical verdicts. Key resolved pins / resolver message:

| Case | Requirements | Result | Resolved key pins / uv message |
|---|---|---|---|
| `pypsa` | `pypsa>=1.4,<1.5` | ✅ 52 pkgs | pypsa 1.4.0, linopy 0.10.1, highspy 1.16.0, pandas 3.1.1, numpy 2.4.6 (py3.11) / 2.5.4 (py3.12) |
| `pandapower` | `pandapower>=3.5,<3.6` | ✅ 24 pkgs | pandapower 3.5.6, pandas 2.3.3, numpy 2.4.6 |
| `grid2op` | `grid2op>=1.12,<1.13` | ✅ 30 pkgs | grid2op 1.12.6, pandapower 3.5.6, pandas 2.3.3 |
| `pp_g2o` | `pandapower>=3.5,<3.6` + `grid2op>=1.12,<1.13` | ✅ 30 pkgs | grid2op 1.12.6, pandapower 3.5.6, pandas 2.3.3 |
| `pypsa_pp` | `pypsa>=1.4,<1.5` + `pandapower>=3.5,<3.6` | ❌ | "Because pandapower>=3.5.2 depends on pandas>=2.3,<3.dev0 and pypsa>=1.4.0 depends on pandas>=3.0, we can conclude that pandapower>=3.5.2 and pypsa>=1.4.0 are incompatible." |
| `pypsa13_pp` | `pypsa>=1.3,<1.4` + `pandapower>=3.5,<3.6` | ❌ | "... pandapower>=3.5.2 depends on pandas>=2.3,<3.dev0 and pypsa==1.3.0 depends on pandas>=3.0 ..." |
| `pypsa_pp_unbounded` | `pypsa>=1.4,<1.5` + `pandapower` | ✅ but degraded | resolver backtracks to **pandapower 3.1.2** (last release without the pandas cap) with pandas 3.1.1 — an untested combination, and not pandapower 3.5.x |
| `pypsa_g2o` | `pypsa>=1.4,<1.5` + `grid2op>=1.12,<1.13` | ✅ but degraded | backtracks to **grid2op 1.12.0** + **pandapower 3.1.2** + pandas 3.1.1 (grid2op 1.12.0 lacks the `pandas<3` cap) |
| `pypsa_g2o_latest` | `pypsa>=1.4,<1.5` + `grid2op>=1.12.6,<1.13` | ❌ | "Because grid2op>=1.12.6 depends on pandas>=1.0.3,<3 and pypsa>=1.4.0 depends on pandas>=3.0, we can conclude that grid2op>=1.12.6 and pypsa>=1.4.0 are incompatible." |
| `all3` | pypsa 1.4.x + pandapower 3.5.x + grid2op 1.12.x | ❌ | same pandas conflict as `pypsa_pp` |
| `pp_pandas3` | `pandapower>=3.5,<3.6` + `pandas>=3` | ❌ | "Because pandapower>=3.5.2 depends on pandas>=2.3,<3.dev0 and you require pandapower>=3.5, we can conclude that you require pandas>=2.3,<3.dev0." |
| `pp_pandas2` | `pandapower>=3.5,<3.6` + `pandas<3` | ✅ | pandapower 3.5.6, pandas 2.3.3 |
| `g2o_pandas3` | `grid2op>=1.12,<1.13` + `pandas>=3` | ✅ but degraded | grid2op 1.12.0, pandapower 3.1.2, pandas 3.1.1 |
| `g2o_pp_pandas2` | grid2op 1.12.x + pandapower 3.5.x + numpy + scipy | ✅ | grid2op 1.12.6, pandapower 3.5.6, pandas 2.3.3, scipy 1.17.1 |
| `core` | `pypsa>=1.4,<1.5` + linopy + highspy + `pandas>=3` + fastapi + `pydantic>=2` | ✅ 63 pkgs | pypsa 1.4.0, linopy 0.10.1, highspy 1.16.0, pandas 3.1.1, fastapi 0.162.7 |
| `core_stormspec_only` | `pydantic>=2` | ✅ 5 pkgs | pydantic 2.14.3 — confirms `stormspec`/`canonical_grid` can be imported in every env |
| `eur_core` | PyPSA-Eur env spec (pypsa>=0.35.2, linopy>=0.8,<0.9, pandas>=3, highspy>=1.12, xarray>=2026.1, numpy>=1.26.4) | ✅ 49 pkgs | **pypsa 1.2.4**, linopy 0.8.0 (matches upstream lock) |
| `eur_with_pypsa14` | `pypsa>=1.4,<1.5` + `linopy>=0.8,<0.9` + `pandas>=3` | ❌ | "Because pypsa>=1.4.0 depends on linopy>=0.9.0 and you require pypsa>=1.4, we can conclude that you require linopy>=0.9.0. And because you require linopy>=0.8,<0.9 ... unsatisfiable." |

"Degraded" = resolvable only by silently downgrading to releases older than the target minor series;
these are rejected because GridStorm pins pandapower 3.5.x and grid2op 1.12.x (contract §1) and
the downgraded combos (pandas 3 + pandapower 3.1.2) are not the upstreams' tested matrix.

## 3. Conclusions

1. **PyPSA 1.4 ⟂ pandapower 3.5** — proven incompatible (pandas ≥ 3 vs pandas < 3). Separate envs.
2. **PyPSA 1.4 ⟂ Grid2Op 1.12.x (≥ 1.12.1)** — proven incompatible for the same reason; only
   grid2op 1.12.0 + pandapower 3.1.2 would co-install, which is rejected. Separate envs.
3. **pandapower 3.5 + Grid2Op 1.12.6 — compatible**: resolve to pandas 2.3.3, grid2op 1.12.6 already
   depends on pandapower. They *can* share an env. GridStorm nevertheless keeps `workers/grid2op`
   separate from `workers/pandapower` because grid2op additionally pulls `lightsim2grid` and dataset
   download state, and the contract (§1) isolates engines; the pandapower-family envs
   (`workers/pandapower`, `workers/advisor`, `workers/distribution`, `packages/stormbench`,
   `packages/stormml`) are all mutually compatible (observed installs: pandapower 3.5.6, pandas 2.3.3,
   numpy 2.4.6). `workers/pandapower` and `packages/stormml` later pinned `scipy<1.14` (pandapower's
   AC-OPF uses the sparse `.H` attribute removed in SciPy 1.14), which resolves to pandapower 3.5.4,
   SciPy 1.13.1 and numpy 2.2.6 in those two envs.
4. **PyPSA-Eur workflow ⟂ PyPSA 1.4** — its own spec caps `linopy<0.9`, which forces pypsa ≤ 1.2.x
   (resolver picks 1.2.4, same as upstream lock). It must run in its own pixi/conda env (GridStorm runs it
   in a container via `pipelines/pypsa-eur/build.sh`); its NetCDF output is consumed by the PyPSA 1.4
   core env.
5. **core env (PyPSA 1.4 + linopy 0.10 + highspy + pandas 3 + FastAPI) — compatible** (`core` case).
6. `stormspec` / `canonical_grid` depend only on pydantic and resolve anywhere.

Required isolation (matches `docs/architecture/contracts.md` §1):

| Env | pandas | Must be isolated from |
|---|---|---|
| core (PyPSA 1.4, linopy 0.10, highspy 1.16, FastAPI) — also pipelines, stormrisk, observed, analytics | 3.x | every pandapower/grid2op env; PyPSA-Eur env |
| pandapower family (pandapower 3.5.6) | 2.3.x | core |
| grid2op (grid2op 1.12.6 + lightsim2grid 1.3.1 + pandapower 3.5.6) | 2.3.x | core (could technically share with pandapower family) |
| PyPSA-Eur workflow (pypsa 1.2.4, linopy 0.8.0, Python ≥ 3.12) | 3.0.x | core (linopy conflict) |

Installed state observed on 2026-11-14 in `<component>/.venv/Lib/site-packages` agrees: core-family
venvs have pypsa 1.4.0 / linopy 0.10.1 / highspy 1.16.0 / pandas 3.1.1; pandapower-family venvs have
pandapower 3.5.6 / pandas 2.3.3; `workers/grid2op` has grid2op 1.12.6 / lightsim2grid 1.3.1 /
pandapower 3.5.6 / pandas 2.3.3.

## 4. Reproduce

```bash
mkdir -p /tmp/compat && cd /tmp/compat
printf 'pypsa>=1.4,<1.5\npandapower>=3.5,<3.6\n' > pypsa_pp.in
uv pip compile --python-version 3.11 --no-header pypsa_pp.in   # expect: No solution found (pandas)
printf 'pandapower>=3.5,<3.6\ngrid2op>=1.12,<1.13\n' > pp_g2o.in
uv pip compile --python-version 3.11 --no-header pp_g2o.in     # expect: grid2op==1.12.6, pandas==2.3.3
```
