# GridStorm

Open-source power-grid resilience and crisis-simulation research platform.

> Status: under active construction. See [`TODO.md`](TODO.md) for verified progress.

GridStorm lets researchers, students and educators select a documented electricity-network model,
define a crisis scenario (transmission outages, demand surges, renewable shortfalls), run a real
scientific simulation (PyPSA linear optimal power flow, pandapower AC power flow / N-1, Grid2Op
sequential operation), and compare baseline, crisis and mitigation results with full provenance.

**GridStorm is not a live utility control system and not a validated real-world blackout predictor.**

- Architecture: [`docs/architecture/overview.md`](docs/architecture/overview.md)
- Interface contracts: [`docs/architecture/contracts.md`](docs/architecture/contracts.md)
- Decisions: [`docs/decisions/`](docs/decisions/)

License: MIT (see [`LICENSE`](LICENSE)); third-party components keep their own licenses
([`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md), [`UPSTREAM_ATTRIBUTION.md`](UPSTREAM_ATTRIBUTION.md)).
