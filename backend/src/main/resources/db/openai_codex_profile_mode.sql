-- Run this on an existing database before inserting mode=2 Codex profile services.
alter table openai_services
  add column if not exists request_mode int not null default 1;

create table if not exists openai_codex_profiles (
  id bigserial primary key,
  openai_service_id bigint not null unique references openai_services(id) on delete cascade,
  profile_name text not null,
  auth_mode text not null default 'chatgpt',
  openai_api_key text,
  access_token text,
  account_id text,
  id_token text,
  refresh_token text,
  client_id text,
  base_url text,
  model text,
  reasoning_effort text,
  last_refresh timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create index if not exists idx_openai_codex_profiles_service_id
  on openai_codex_profiles(openai_service_id);

-- Insert one service row per codex_profiles.json profile.
-- The service row still owns round-robin selection and concurrent_limit.
with service as (
  insert into openai_services (api_endpoint, token, request_mode, concurrent_limit)
  values ('https://chatgpt.com/backend-api/codex', 'codex-profile', 2, 20)
  returning id
)
insert into openai_codex_profiles (
  openai_service_id,
  profile_name,
  auth_mode,
  openai_api_key,
  access_token,
  account_id,
  id_token,
  refresh_token,
  client_id,
  base_url,
  model,
  reasoning_effort,
  last_refresh
)
select
  id,
  'local_codex',
  'chatgpt',
  null,
  'PASTE_ACCESS_TOKEN_HERE',
  'PASTE_ACCOUNT_ID_HERE',
  'PASTE_ID_TOKEN_HERE',
  'PASTE_REFRESH_TOKEN_HERE',
  null,
  '',
  '',
  '',
  null
from service;
