create table if not exists users (
  id uuid primary key,
  email text unique not null,
  password_hash text not null,
  registration_ip text unique not null,
  balance numeric(18, 6) not null default 0,
  status text not null default 'active',
  created_at timestamp with time zone not null default now()
);

create table if not exists api_keys (
  id bigserial primary key,
  user_id uuid not null references users(id),
  key_hash text not null,
  key_value text,
  name text,
  status text not null default 'active',
  created_at timestamp with time zone not null default now()
);

create table if not exists api_logs (
  id bigserial primary key,
  user_id uuid references users(id),
  model text,
  prompt_tokens int not null default 0,
  completion_tokens int not null default 0,
  cost numeric(18, 6) not null default 0,
  status text,
  created_at timestamp with time zone not null default now()
);

create table if not exists request_logs (
  id bigserial primary key,
  user_id uuid not null references users(id),
  api_key_id bigint not null references api_keys(id),
  token_name text not null,
  group_key text not null,
  request_type text not null default '消费',
  client_type text not null default 'UNKNOWN',
  model text,
  use_time_ms int not null default 0,
  first_token_ms int not null default 0,
  prompt_tokens int not null default 0,
  completion_tokens int not null default 0,
  cache_read_tokens int not null default 0,
  cache_creation_tokens int not null default 0,
  cost numeric(18, 6) not null default 0,
  ip text,
  status text,
  upstream_service_id bigint,
  detail text not null default '',
  created_at timestamp with time zone not null default now()
);

create table if not exists recharge_orders (
  id bigserial primary key,
  user_id uuid not null references users(id),
  amount numeric(18, 6) not null,
  status text not null default 'pending',
  remark text,
  created_at timestamp with time zone not null default now()
);

create table if not exists openai_services (
  id bigserial primary key,
  api_endpoint text not null,
  token text not null,
  request_mode int not null default 1,
  concurrent_limit int not null default 20,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

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

create table if not exists claude_services (
  id bigserial primary key,
  api_endpoint text not null,
  token text not null,
  concurrent_limit int not null default 20,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists model_catalog (
  id text primary key,
  name text not null,
  provider text not null default 'OpenAI',
  input_price numeric(12, 4) not null,
  output_price numeric(12, 4) not null,
  cached_input_price numeric(12, 4) not null,
  cache_creation_price numeric(12, 4) not null,
  tags text not null default '',
  sort_order int not null default 0,
  enabled boolean not null default true
);

create index if not exists idx_api_keys_user_id on api_keys(user_id);
create index if not exists idx_api_logs_user_id_created_at on api_logs(user_id, created_at desc);
create index if not exists idx_request_logs_user_id_created_at
  on request_logs(user_id, created_at desc);
create index if not exists idx_recharge_orders_user_id_created_at
  on recharge_orders(user_id, created_at desc);
create index if not exists idx_openai_codex_profiles_service_id
  on openai_codex_profiles(openai_service_id);
