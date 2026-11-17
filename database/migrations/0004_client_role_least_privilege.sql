-- Least privilege for the Supabase client roles (GridStorm 3.3, TODO G33-01). No data changes;
-- idempotent; safe to re-run. The API connects as the table owner (`postgres`) and is unaffected.
--
-- Evidence (read-only production inventory, 2026-11-17, docs/data/production-inventory.md):
-- 1. `anon` holds INSERT / UPDATE / DELETE on every public table, but no RLS policy grants `anon`
--    any write command (all `anon` policies are SELECT). Writes were rejected only by RLS; the
--    grants serve no client and widen the blast radius of a future policy mistake. `authenticated`
--    keeps its write grants because its owner-scoped write policies (scenarios, comparisons,
--    profiles) are part of the documented client design.
-- 2. Through the `anon` / `authenticated` SELECT grant on simulation_jobs, PostgREST exposes
--    `worker_id` (Render service id + host name + pid) and `heartbeat_at`, worker internals that
--    the GridStorm API never returns. Column-level REVOKE has no effect while a table-level SELECT
--    exists, so the table grant is replaced by a column grant without those two columns. A new
--    column added later is therefore not client-readable until it is granted explicitly.
--
-- Rollback (restores the 0003 state):
--   grant insert, update, delete on all tables in schema public to anon;
--   alter default privileges in schema public grant insert, update, delete on tables to anon;
--   grant select on public.simulation_jobs to anon, authenticated;

revoke insert, update, delete on all tables in schema public from anon;
alter default privileges in schema public
    revoke insert, update, delete on tables from anon;

revoke select on public.simulation_jobs from anon, authenticated;
grant select (
    id, scenario_id, scenario_definition_id, scenario_hash, spec, network_id, network_version_id,
    execution_mode, reused, reused_from_job_id, status, stage, stage_history, outcome, solver,
    error, attempts, cancel_requested, owner_id, visibility, started_at, finished_at,
    result_sha256, created_at, updated_at
) on public.simulation_jobs to anon, authenticated;
