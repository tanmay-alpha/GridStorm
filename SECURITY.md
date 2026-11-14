# Security policy

## Scope

GridStorm is a research and education platform. It does not connect to, control, or receive data from
real grid operational technology. Do not deploy it as part of any operational control loop.

## Reporting a vulnerability

Please open a private security advisory on GitHub
(`Security → Advisories → Report a vulnerability`) for this repository. Do not file public issues
for vulnerabilities. Expect an initial response within 7 days.

## Practices

- Secrets are provided only through environment variables (see `.env.example`); none are committed.
  The Supabase service-role key is never sent to the browser.
- User-owned rows are protected by Postgres row-level security and by owner checks in the API.
- Simulation jobs run in subprocesses with a wall-clock timeout, an address-space limit (Linux) and
  bounded concurrency; request bodies and POST rates are limited.
- Scenario inputs are validated against a strict schema and against the selected network before any
  computation; unsupported operations are rejected.
- Dependencies are locked per component and audited in CI (`pip-audit`, `npm audit`).
