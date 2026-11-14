# Network data catalog

The four shipped networks are indexed by [`data/networks/catalog.json`](../../data/networks/catalog.json) (`network-catalog/1.0`). Each directory contains a PyPSA 1.4.0 `network.nc`, validated `canonical-grid/1.0` JSON, and a `dataset-manifest/1.0` manifest. Manifests record SHA256 and byte length of **every file except the manifest itself** (self-hashing is not possible), attribution, units, missing-value policy, quality flags and transformation history. Retrieval records preserve the original download timestamp and source checksum; reruns reuse verified local sources.

## Inventory

| Dataset | Buses | Lines | Transformers | Links | Generators | Loads | Snapshots | NetCDF bytes |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ac-dc-meshed | 9 | 7 | 0 | 4 | 6 | 6 | 10 | 111180 |
| scigrid-de | 585 | 852 | 96 | 0 | 1423 | 489 | 24 | 1527668 |
| pglib-case14-ieee | 14 | 17 | 3 | 0 | 5 | 11 | 1 | 81921 |
| pglib-case118-ieee | 118 | 175 | 11 | 0 | 54 | 99 | 1 | 171750 |

SciGRID also has 38 storage units. All files are below the 10 MiB importer limit. These are research/example systems, not validated present-day operational grids.

## ac-dc-meshed

- Source: [versioned upstream NetCDF](https://data.pypsa.org/networks/examples/v1.4.0/ac_dc_meshed.nc), the URL used by `pypsa.examples.ac_dc_meshed()` in PyPSA 1.4.0. PyPSA code/tag commit: `6c45594596cbc5612511ee9202a9e269e5001d88`; this identifies the downloader/license revision, not a Git commit of the remotely hosted NetCDF.
- Version/date: PyPSA v1.4.0 example; HTTP Last-Modified `Wed, 11 Nov 2026 16:06:54 GMT` (server metadata, not an independently established publication date).
- Retrieved: `2026-11-14T16:08:10+00:00`.
- Source and shipped NetCDF SHA256: `62e4e53555e2219a2ae48b7f91e576e2ea383cadd2f61db9919f3592503c932f` (byte-identical upstream).
- License/attribution: CC-BY-4.0, PyPSA Contributors. [Pinned REUSE.toml](https://github.com/PyPSA/PyPSA/blob/6c45594596cbc5612511ee9202a9e269e5001d88/REUSE.toml) explicitly licenses `examples/**.nc` as CC-BY-4.0, separately from PyPSA's MIT code license.
- Coverage: synthetic UK/Germany/Norway nodes, EPSG:4326; 10 hourly snapshots, 2015-01-01 00:00–09:00.
- Units: kV, MVA, MW, MWh, ohm, EUR/MWh; coordinate degrees. Full per-field units: [manifest](../../data/networks/ac-dc-meshed/manifest.json).
- Missing values: line lengths and bus names null; other absent/NaN/infinite canonical values null. NetCDF retains source defaults.
- Quality: illustrative topology and extendable generators with placeholder capacity; zero resistance AC lines and zero reactance DC lines retained. Four PyPSA sub-networks (3/3/2/1 buses) are coupled through converter links; no isolated bus. GlobalConstraint `co2_limit` is retained in NetCDF but outside canonical-grid/1.0.
- Transformations: checksum-verified download → dependent electrical values → canonical JSON and manifest. Source NetCDF unchanged.
- Redistribution: freely downloadable **and open for redistribution with CC-BY attribution**, license link and modification notice. Canonical JSON is a derived representation by GridStorm.

## scigrid-de

- Source: [versioned upstream NetCDF](https://data.pypsa.org/networks/examples/v1.4.0/scigrid_de.nc), as used by `pypsa.examples.scigrid_de()` in PyPSA 1.4.0; downloader/license commit `6c45594596cbc5612511ee9202a9e269e5001d88`.
- Version/date: PyPSA v1.4.0 packaging of SciGRID v0.2; HTTP Last-Modified `Wed, 11 Nov 2026 16:06:48 GMT` (not an independently verified publication date).
- Retrieved: `2026-11-14T16:08:26+00:00`.
- Source and shipped NetCDF SHA256: `284850c8e922414f9da69ffda0623431148e0c28a3380ba370e4135ac5236500`.
- License/attribution: PyPSA Contributors, CC-BY-4.0 per the [pinned REUSE annotations](https://github.com/PyPSA/PyPSA/blob/6c45594596cbc5612511ee9202a9e269e5001d88/REUSE.toml). Attribute SciGRID (DLR Institute of Networked Energy Systems, formerly NEXT ENERGY) and © OpenStreetMap contributors, [ODbL-1.0](https://www.openstreetmap.org/copyright). The [upstream data-sources notebook](https://github.com/PyPSA/PyPSA/blob/6c45594596cbc5612511ee9202a9e269e5001d88/docs/examples/scigrid-lopf-then-pf.ipynb) explicitly identifies the SciGRID/OSM origin. SciGRID's original release license text was not recovered from its unavailable original download site; do not mistake the verified PyPSA packaging grant for proof that underlying OSM obligations disappear.
- Coverage: Germany, 220/380 kV transmission; EPSG:4326; 24 hourly snapshots on 2011-01-01. Generator capacities include end-2014 renewable inputs, so this is not a temporally uniform historical reconstruction.
- Units: kV, MVA, MW, MWh, km, ohm; transformer impedance p.u. on transformer MVA rating; efficiencies dimensionless; coordinate degrees. Full list: [manifest](../../data/networks/scigrid-de/manifest.json).
- Missing values: bus names/country, line carrier, carrier colors/emission factors null where source values are absent or placeholders. Four loads retain source static zero demand without time series.
- Quality: line impedances calculated from standard line types and length/parallel count; thermal ratings estimated; uniform transformer parameters placeholders (2000 MVA, x=0.1 p.u.). Load is ENTSO-E demand scaled by 1.12 and allocated using NUTS3 GDP/population, not bus-level metering. Plant locations/capacities derive from BNetzA and EEG/EnergyMap; renewable availability from REatlas; marginal costs illustrative. One connected sub-network, no isolated bus. Exactly 96 line/transformer IDs overlap: IDs are unique only within a component type. `line_outage` must specify `component: "transformer"` for transformers; default is `"line"`.
- Transformations: checksum-verified download → standard-type dependent impedances → canonical conversion with provenance and null masking; NetCDF byte-identical upstream.
- Redistribution decision: freely downloadable; redistribute the PyPSA example with its CC-BY attribution **and retain OSM attribution/ODbL notice**. Conservatively treat public derived OSM databases as subject to ODbL share-alike/source-access obligations, not as CC-BY-only. This is not a legal clearance of the unrecovered original SciGRID release. See also [license audit](license-audit.md#scigrid-example-network-pypsa).

## PGLib-OPF cases

Both cases use PGLib-OPF **v23.07**, publication date recorded as `2023-07-23`, pinned commit `dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3`.

| Dataset | Source URL | Retrieved UTC | Raw MATPOWER SHA256 | Shipped NetCDF SHA256 |
|---|---|---|---|---|
| pglib-case14-ieee | [pglib_opf_case14_ieee.m](https://raw.githubusercontent.com/power-grid-lib/pglib-opf/dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3/pglib_opf_case14_ieee.m) | 2026-11-14T16:09:22+00:00 | `bd5c568621de65e4b0922317010868bc7fa94173807faa10ea8fdbbe77c28106` | `52424e30e5375a7d8b57d66704b2c0b258c21cad65d47c223e02bad0cb056a42` |
| pglib-case118-ieee | [pglib_opf_case118_ieee.m](https://raw.githubusercontent.com/power-grid-lib/pglib-opf/dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3/pglib_opf_case118_ieee.m) | 2026-11-14T16:09:32+00:00 | `b1af0833849040c04babc3700631cff0d9afa66b79c5d3e13ae79bdf516cec78` | `f355e7888f8864231e3f113d339d08efd647ead9bcb9f2b77fc4e3171d2dcdad` |

- License evidence: [pinned upstream LICENSE](https://github.com/power-grid-lib/pglib-opf/blob/dc6be4b2f85ca0e776952ec22cbd4c22396ea5a3/LICENSE), copied into each `source/LICENSE-pglib-opf`, explicitly separates **CC-BY-4.0 data** from MIT software. Each committed `.m` header repeats the data grant and credits © 1999 Richard D. Christie, University of Washington. Attribute the IEEE PES Task Force on Benchmarks for Validation of Emerging Power System Algorithms and the per-case holder. License file SHA256: `95b1cd9fee1676221d74f7c0cbba622d98ac098e9b317b3848113ef4356ab4fd`.
- Coverage: IEEE benchmark systems derived from historic AEP cases, not georeferenced grids; one undated operating point. Deterministic Kamada-Kawai coordinates are **schematic**, dimensionless, with `crs: null`.
- Transformation history: pinned `.m` and license download → strict MATPOWER v2 parser → PyPSA network construction/unit conversion → schematic layout → canonical JSON. Raw sources are preserved in each dataset's `source/` directory.
- IDs: `bus-<BUS_I>`, `branch-<1-based row>`, `gen-<1-based row>`, `load-<BUS_I>`. A nontrivial tap, phase shift, or voltage-level change creates a transformer with the same branch ID. Counts are preserved: case14 20 branches/5 generators; case118 186 branches/54 generators.
- Electrical units: line `r/x` in ohm = source p.u. × baseKV²/baseMVA; shunt susceptance S = source p.u. × baseMVA/baseKV². Transformer `r/x` p.u. on its own rating = source p.u. × s_nom/baseMVA. Taps on from-bus, phase shift degrees, pi model. Powers MW/MVAr; ratings MVA; voltage kV.
- Costs: c2·P²+c1·P+c0 linearized to secant slope `c1+c2*Pmax`, with c0 dropped, provenance `modeled`. Values remain source nominal currency/MWh, **not EUR**, despite the fixed canonical field name `marginal_cost_eur_per_mwh`; manifests explicitly override its units. Do not use them for euro-denominated comparisons.
- Missing-value policy: unknown line length/country/emission factors/color and unsupported defaults become null. MATPOWER RATE_A=0 means unlimited: canonical rating null, flagged NetCDF sentinel 1e9 MVA, never presented as an observed limit. The parser/build tests exercise this rule even though neither shipped case needs the sentinel.
- Quality flags (both): `schematic_coordinates`, `single_snapshot`, `cost_currency_not_eur`, `marginal_cost_linearized_secant`. Some zero-resistance branches produce consistency warnings; these source values are preserved. Voltage limits/setpoints and shunts remain in NetCDF; branch angle limits and RATE_B/C are not represented; shunts lie outside canonical-grid/1.0.
- Temporal interpretation: one snapshot `now`, weighting 1 hour; load energy is power × 1 hour, not an observed annual energy total. Source Pg is an initial point, not balanced dispatch: case14 Pg=199.5 vs Pd=259 MW; case118 Pg=3257.5 vs Pd=4242 MW. DC power flow adjusts slack by +59.5/+984.5 MW respectively and balances generation/load at 259/4242 MW, with zero reported mismatch. This is a conversion check, not OPF or AC feasibility evidence.
- Redistribution: freely downloadable **and open for redistribution with CC-BY attribution**, license link and indication of GridStorm's conversion/linearization/layout changes. Full fields/checksums: [case14 manifest](../../data/networks/pglib-case14-ieee/manifest.json), [case118 manifest](../../data/networks/pglib-case118-ieee/manifest.json).

## Reproduction and validation

From `pipelines/network-import`:

```sh
uv run python -m network_import all
uv run python -m network_import validate
uv run pytest -q
```

Imports are deterministic/idempotent: pinned example checksums, commit-addressed PGLib sources, persisted retrieval metadata, stable JSON, and semantic NetCDF comparison retain existing bytes when unchanged. `from-netcdf <id> <path> --name ... --source-url ... --license ...` supports externally built networks; `network_import.canonical.from_pypsa` is the shared conversion API. No external build is claimed as part of these four shipped datasets.

Validation checks Pydantic schemas, per-component IDs, bus references, manifest file coverage/checksums/sizes, NetCDF/canonical asset IDs, physical ranges, required electrical parameters, PyPSA consistency and connectivity (including islands), plus PGLib source counts and DC power balance. Warnings are reported, not hidden. Canonical models and exported JSON Schemas live under `packages/canonical-grid/`. Any energy-not-served derived from a single deterministic dataset/scenario is unserved energy; reserve “EENS” for probability-weighted results.
