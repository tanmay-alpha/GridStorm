-- Row Level Security for direct Supabase client access (anon / authenticated roles).
--
-- The GridStorm API connects with DATABASE_URL as the table owner (Supabase `postgres` role) or
-- `service_role`; both bypass RLS (owner without FORCE ROW LEVEL SECURITY; service_role has
-- BYPASSRLS). The API enforces the same rules in its own queries; these policies make the rules
-- hold for anyone using the anon/authenticated keys directly against PostgREST.
--
-- Rules:
--   * datasets / versions / sources: public read when the dataset is public.
--   * scenario_definitions, simulation_jobs, comparison_reports: readable when
--     visibility = 'public' or owner_id = auth.uid(); owners may update/delete their own
--     scenarios and comparisons; clients cannot create jobs (only the API does).
--   * simulation_metrics / simulation_artifacts: readable when the parent job is readable.
--   * profiles: a user reads/updates only their own row.
--   * ingestion_runs, audit_events, schema_migrations: no client access (no policies).

alter table public.profiles enable row level security;
alter table public.network_datasets enable row level security;
alter table public.network_versions enable row level security;
alter table public.dataset_sources enable row level security;
alter table public.ingestion_runs enable row level security;
alter table public.scenario_definitions enable row level security;
alter table public.simulation_jobs enable row level security;
alter table public.simulation_metrics enable row level security;
alter table public.simulation_artifacts enable row level security;
alter table public.comparison_reports enable row level security;
alter table public.audit_events enable row level security;

-- profiles ------------------------------------------------------------------------------------
create policy profiles_select_own on public.profiles
    for select to authenticated using (id = (select auth.uid()));
create policy profiles_insert_own on public.profiles
    for insert to authenticated with check (id = (select auth.uid()));
create policy profiles_update_own on public.profiles
    for update to authenticated
    using (id = (select auth.uid())) with check (id = (select auth.uid()));

-- datasets ------------------------------------------------------------------------------------
create policy network_datasets_public_read on public.network_datasets
    for select to anon, authenticated using (is_public);
create policy network_versions_public_read on public.network_versions
    for select to anon, authenticated using (
        exists (select 1 from public.network_datasets d where d.id = network_id and d.is_public)
    );
create policy dataset_sources_public_read on public.dataset_sources
    for select to anon, authenticated using (
        exists (select 1 from public.network_datasets d where d.id = network_id and d.is_public)
    );

-- scenarios -----------------------------------------------------------------------------------
create policy scenario_definitions_read on public.scenario_definitions
    for select to anon, authenticated
    using (visibility = 'public' or owner_id = (select auth.uid()));
create policy scenario_definitions_insert_own on public.scenario_definitions
    for insert to authenticated
    with check (owner_id = (select auth.uid()) and not is_preset);
create policy scenario_definitions_update_own on public.scenario_definitions
    for update to authenticated
    using (owner_id = (select auth.uid()))
    with check (owner_id = (select auth.uid()) and not is_preset);
create policy scenario_definitions_delete_own on public.scenario_definitions
    for delete to authenticated using (owner_id = (select auth.uid()));

-- jobs and outputs ----------------------------------------------------------------------------
create policy simulation_jobs_read on public.simulation_jobs
    for select to anon, authenticated
    using (visibility = 'public' or owner_id = (select auth.uid()));
create policy simulation_metrics_read on public.simulation_metrics
    for select to anon, authenticated using (
        exists (
            select 1 from public.simulation_jobs j
            where j.id = job_id
              and (j.visibility = 'public' or j.owner_id = (select auth.uid()))
        )
    );
create policy simulation_artifacts_read on public.simulation_artifacts
    for select to anon, authenticated using (
        exists (
            select 1 from public.simulation_jobs j
            where j.id = job_id
              and (j.visibility = 'public' or j.owner_id = (select auth.uid()))
        )
    );

-- comparisons ---------------------------------------------------------------------------------
create policy comparison_reports_read on public.comparison_reports
    for select to anon, authenticated
    using (visibility = 'public' or owner_id = (select auth.uid()));
create policy comparison_reports_delete_own on public.comparison_reports
    for delete to authenticated using (owner_id = (select auth.uid()));
