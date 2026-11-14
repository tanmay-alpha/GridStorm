-- GridStorm core schema (Supabase / Postgres 15+).
-- Mirrors services/api/src/gridstorm_api/db/models.py; services/api/tests/test_postgres_migrations.py
-- checks that both agree. Apply with `python -m gridstorm_api.db.migrate` or the Supabase SQL editor.
-- Not created on purpose: network_assets (asset rows are served from committed canonical.json).

create extension if not exists pgcrypto;  -- gen_random_uuid() (built in since PG13; harmless)

create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

-- ---------------------------------------------------------------------------------------------
-- profiles: one row per Supabase auth user that used the API. id = auth.users.id.
create table public.profiles (
    id uuid not null,
    display_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pk_profiles primary key (id),
    constraint fk_profiles_id_users foreign key (id) references auth.users (id) on delete cascade
);

-- ---------------------------------------------------------------------------------------------
-- network datasets, versions, sources, ingestion runs
create table public.network_datasets (
    id text not null,
    name text not null,
    description text,
    coordinate_kind text not null,
    provenance_class text,
    license_spdx text,
    redistribution text,
    is_public boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pk_network_datasets primary key (id),
    constraint ck_network_datasets_coordinate_kind
        check (coordinate_kind in ('geographic', 'schematic'))
);

create table public.network_versions (
    id uuid not null default gen_random_uuid(),
    network_id text not null,
    network_sha256 text,
    canonical_sha256 text not null,
    manifest_sha256 text not null,
    manifest jsonb not null,
    retrieved_at text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pk_network_versions primary key (id),
    constraint fk_network_versions_network_id_network_datasets
        foreign key (network_id) references public.network_datasets (id) on delete cascade,
    constraint uq_network_versions_network_id_canonical_sha256_manifest_sha256
        unique (network_id, canonical_sha256, manifest_sha256)
);

create table public.dataset_sources (
    id uuid not null default gen_random_uuid(),
    network_id text not null,
    network_version_id uuid not null,
    url text,
    version text,
    publication_date text,
    upstream_commit text,
    license_spdx text,
    license_url text,
    attribution text,
    redistribution text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pk_dataset_sources primary key (id),
    constraint fk_dataset_sources_network_id_network_datasets
        foreign key (network_id) references public.network_datasets (id) on delete cascade,
    constraint fk_dataset_sources_network_version_id_network_versions
        foreign key (network_version_id) references public.network_versions (id) on delete cascade,
    constraint uq_dataset_sources_network_version_id unique (network_version_id)
);
create index ix_dataset_sources_network_id on public.dataset_sources (network_id);

create table public.ingestion_runs (
    id uuid not null default gen_random_uuid(),
    network_id text,
    network_version_id uuid,
    tool text not null,
    status text not null,
    started_at timestamptz not null,
    finished_at timestamptz,
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pk_ingestion_runs primary key (id),
    constraint fk_ingestion_runs_network_id_network_datasets
        foreign key (network_id) references public.network_datasets (id) on delete cascade,
    constraint fk_ingestion_runs_network_version_id_network_versions
        foreign key (network_version_id) references public.network_versions (id) on delete set null,
    constraint ck_ingestion_runs_status check (status in ('succeeded', 'failed'))
);
create index ix_ingestion_runs_network_id on public.ingestion_runs (network_id);

-- ---------------------------------------------------------------------------------------------
-- scenarios
create table public.scenario_definitions (
    id text not null,                       -- preset: StormSpec slug; saved: uuid string
    spec_id text not null,                  -- StormSpec `id`
    name text not null,
    network_id text not null,
    scenario_hash text not null,            -- stormspec.scenario_hash (sha256 hex)
    spec jsonb not null,
    is_preset boolean not null default false,
    visibility text not null default 'public',
    owner_id uuid,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pk_scenario_definitions primary key (id),
    constraint fk_scenario_definitions_network_id_network_datasets
        foreign key (network_id) references public.network_datasets (id) on delete restrict,
    constraint fk_scenario_definitions_owner_id_profiles
        foreign key (owner_id) references public.profiles (id) on delete cascade,
    constraint ck_scenario_definitions_visibility check (visibility in ('public', 'private')),
    constraint ck_scenario_definitions_preset_unowned check (not is_preset or owner_id is null)
);
create index ix_scenario_definitions_network_id on public.scenario_definitions (network_id);
create index ix_scenario_definitions_scenario_hash on public.scenario_definitions (scenario_hash);
create index ix_scenario_definitions_owner_id on public.scenario_definitions (owner_id);

-- ---------------------------------------------------------------------------------------------
-- simulation jobs and their outputs
create table public.simulation_jobs (
    id uuid not null default gen_random_uuid(),
    scenario_id text not null,
    scenario_definition_id text,
    scenario_hash text not null,
    spec jsonb not null,
    network_id text not null,
    network_version_id uuid,
    execution_mode text not null default 'live',
    reused boolean not null default false,
    reused_from_job_id uuid,
    status text not null default 'queued',
    stage text not null default 'queued',
    stage_history jsonb not null default '[]'::jsonb,
    outcome text,
    solver jsonb,
    error jsonb,
    attempts integer not null default 0,
    cancel_requested boolean not null default false,
    worker_id text,
    heartbeat_at timestamptz,
    owner_id uuid,
    visibility text not null default 'public',
    started_at timestamptz,
    finished_at timestamptz,
    result_sha256 text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pk_simulation_jobs primary key (id),
    constraint fk_simulation_jobs_scenario_definition_id_scenario_definitions
        foreign key (scenario_definition_id) references public.scenario_definitions (id)
        on delete set null,
    constraint fk_simulation_jobs_network_id_network_datasets
        foreign key (network_id) references public.network_datasets (id) on delete restrict,
    constraint fk_simulation_jobs_network_version_id_network_versions
        foreign key (network_version_id) references public.network_versions (id) on delete set null,
    constraint fk_simulation_jobs_reused_from_job_id_simulation_jobs
        foreign key (reused_from_job_id) references public.simulation_jobs (id) on delete set null,
    constraint fk_simulation_jobs_owner_id_profiles
        foreign key (owner_id) references public.profiles (id) on delete set null,
    constraint ck_simulation_jobs_status
        check (status in ('queued', 'running', 'completed', 'failed', 'cancelled', 'timeout')),
    constraint ck_simulation_jobs_stage
        check (stage in ('queued', 'loading_network', 'applying_scenario', 'building_model',
                         'solving', 'postprocessing', 'done')),
    constraint ck_simulation_jobs_outcome
        check (outcome is null or outcome in ('feasible', 'infeasible', 'error')),
    constraint ck_simulation_jobs_execution_mode check (execution_mode in ('live', 'precomputed')),
    constraint ck_simulation_jobs_visibility check (visibility in ('public', 'private'))
);
create index ix_simulation_jobs_status_created_at on public.simulation_jobs (status, created_at);
create index ix_simulation_jobs_scenario_hash_status
    on public.simulation_jobs (scenario_hash, status);
create index ix_simulation_jobs_network_id on public.simulation_jobs (network_id);
create index ix_simulation_jobs_owner_id on public.simulation_jobs (owner_id);

create table public.simulation_metrics (
    job_id uuid not null,
    network_id text not null,
    scenario_hash text not null,
    outcome text,
    total_load_mwh double precision,
    served_load_mwh double precision,
    unserved_energy_mwh double precision,
    peak_load_shed_mw double precision,
    total_system_cost_eur double precision,
    curtailment_mwh double precision,
    max_line_loading_pct double precision,
    congested_line_count integer,
    co2_emissions_t double precision,
    balance_residual_max_mw double precision,
    metrics jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pk_simulation_metrics primary key (job_id),
    constraint fk_simulation_metrics_job_id_simulation_jobs
        foreign key (job_id) references public.simulation_jobs (id) on delete cascade
);
create index ix_simulation_metrics_network_id on public.simulation_metrics (network_id);
create index ix_simulation_metrics_scenario_hash on public.simulation_metrics (scenario_hash);

create table public.simulation_artifacts (
    id uuid not null default gen_random_uuid(),
    job_id uuid not null,
    kind text not null,
    storage_backend text not null,
    storage_key text not null,              -- content-addressed: sha256/<hash>.<ext>
    sha256 text not null,
    bytes bigint not null,
    content_type text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pk_simulation_artifacts primary key (id),
    constraint fk_simulation_artifacts_job_id_simulation_jobs
        foreign key (job_id) references public.simulation_jobs (id) on delete cascade,
    constraint uq_simulation_artifacts_job_id_kind unique (job_id, kind),
    constraint ck_simulation_artifacts_kind check (kind in ('result', 'scenario', 'log'))
);
create index ix_simulation_artifacts_sha256 on public.simulation_artifacts (sha256);

-- ---------------------------------------------------------------------------------------------
-- comparisons
create table public.comparison_reports (
    id uuid not null default gen_random_uuid(),
    baseline_job_id uuid not null,
    scenario_job_id uuid not null,
    network_id text not null,
    report jsonb not null,
    report_sha256 text not null,
    owner_id uuid,
    visibility text not null default 'public',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint pk_comparison_reports primary key (id),
    constraint fk_comparison_reports_baseline_job_id_simulation_jobs
        foreign key (baseline_job_id) references public.simulation_jobs (id) on delete cascade,
    constraint fk_comparison_reports_scenario_job_id_simulation_jobs
        foreign key (scenario_job_id) references public.simulation_jobs (id) on delete cascade,
    constraint fk_comparison_reports_network_id_network_datasets
        foreign key (network_id) references public.network_datasets (id) on delete restrict,
    constraint fk_comparison_reports_owner_id_profiles
        foreign key (owner_id) references public.profiles (id) on delete cascade,
    constraint ck_comparison_reports_visibility check (visibility in ('public', 'private'))
);
create index ix_comparison_reports_baseline_job_id on public.comparison_reports (baseline_job_id);
create index ix_comparison_reports_scenario_job_id on public.comparison_reports (scenario_job_id);
create index ix_comparison_reports_owner_id on public.comparison_reports (owner_id);

-- ---------------------------------------------------------------------------------------------
-- audit trail (append-only; no updated_at). actor_id has no FK so history survives deletions.
create table public.audit_events (
    id bigint generated by default as identity,
    created_at timestamptz not null default now(),
    actor_id uuid,
    action text not null,
    target_type text not null,
    target_id text,
    details jsonb not null default '{}'::jsonb,
    constraint pk_audit_events primary key (id)
);
create index ix_audit_events_created_at on public.audit_events (created_at);
create index ix_audit_events_target on public.audit_events (target_type, target_id);

-- ---------------------------------------------------------------------------------------------
-- updated_at triggers
do $$
declare t text;
begin
    foreach t in array array[
        'profiles', 'network_datasets', 'network_versions', 'dataset_sources', 'ingestion_runs',
        'scenario_definitions', 'simulation_jobs', 'simulation_metrics', 'simulation_artifacts',
        'comparison_reports'
    ] loop
        execute format(
            'create trigger trg_%1$s_updated_at before update on public.%1$I '
            'for each row execute function public.set_updated_at()', t);
    end loop;
end;
$$;
