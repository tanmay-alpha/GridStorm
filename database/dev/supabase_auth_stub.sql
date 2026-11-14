-- LOCAL DEV / TESTS ONLY. Never apply to a real Supabase project (it already has all of this).
-- Minimal stand-in for the parts of Supabase that GridStorm migrations reference:
-- roles anon / authenticated / service_role, schema auth, auth.users, auth.uid().
-- auth.uid() reads the JWT subject from the `request.jwt.claim.sub` setting, like Supabase's
-- legacy implementation, so RLS policies can be exercised with
--   set local role authenticated; set local request.jwt.claim.sub = '<uuid>';

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin noinherit;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin noinherit;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'service_role') then
        create role service_role nologin noinherit bypassrls;
    end if;
end;
$$;

create schema if not exists auth;

create table if not exists auth.users (
    id uuid primary key,
    email text,
    created_at timestamptz not null default now()
);

create or replace function auth.uid() returns uuid
language sql stable as $$
    select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;

grant usage on schema public to anon, authenticated, service_role;
grant usage on schema auth to anon, authenticated, service_role;
grant execute on function auth.uid() to anon, authenticated, service_role;
alter default privileges in schema public
    grant select, insert, update, delete on tables to anon, authenticated, service_role;
alter default privileges in schema public
    grant usage, select on sequences to anon, authenticated, service_role;
