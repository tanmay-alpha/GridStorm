-- Additive, idempotent hardening (no data changes; safe to re-run).
--
-- 1. Indexes for the API's hot job queries (docs/audit/security-2026-11-15.md, EXPLAIN evidence):
--    * GET /api/v1/simulations: `where visibility = 'public' [or owner_id = $uid]
--      order by created_at desc, id limit N` — previously only (status, created_at) existed, so the
--      unfiltered newest-first listing had to sort the whole table.
--    * GET /api/v1/simulations?mine=true: `where owner_id = $uid order by created_at desc`.
--    * Foreign keys with ON DELETE SET NULL that had no index on the referencing column; deleting a
--      scenario / network version / job had to scan simulation_jobs. Partial (non-null) indexes
--      keep them small because most rows leave these columns null.
-- 2. Supabase grants every table privilege to anon/authenticated by default. TRUNCATE, TRIGGER and
--    REFERENCES are not governed by RLS and are never needed by PostgREST clients; revoke them.
--    The API connects as the table owner and is unaffected.
--
-- The tables are small; plain CREATE INDEX (migrations run inside one transaction, so
-- CONCURRENTLY is not available) holds a brief SHARE lock on simulation_jobs.

create index if not exists ix_simulation_jobs_created_at_id
    on public.simulation_jobs (created_at desc, id);
create index if not exists ix_simulation_jobs_owner_id_created_at
    on public.simulation_jobs (owner_id, created_at desc)
    where owner_id is not null;
create index if not exists ix_simulation_jobs_scenario_definition_id
    on public.simulation_jobs (scenario_definition_id)
    where scenario_definition_id is not null;
create index if not exists ix_simulation_jobs_network_version_id
    on public.simulation_jobs (network_version_id)
    where network_version_id is not null;
create index if not exists ix_simulation_jobs_reused_from_job_id
    on public.simulation_jobs (reused_from_job_id)
    where reused_from_job_id is not null;
create index if not exists ix_ingestion_runs_network_version_id
    on public.ingestion_runs (network_version_id)
    where network_version_id is not null;

revoke truncate, trigger, references on all tables in schema public from anon, authenticated;
alter default privileges in schema public
    revoke truncate, trigger, references on tables from anon, authenticated;
