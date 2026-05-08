create table if not exists users (
  id uuid primary key,
  email text unique not null,
  password_hash text not null,
  registration_ip text unique not null,
  balance numeric(18, 6) not null default 5,
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

create table if not exists redeem_codes (
  id bigserial primary key,
  code text unique not null,
  amount numeric(18, 6) not null,
  expires_at timestamp with time zone not null,
  holder_user_id uuid references users(id),
  redeemed_at timestamp with time zone,
  expired_deducted_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists app_settings (
  setting_key text primary key,
  setting_value text not null,
  description text,
  updated_at timestamp with time zone not null default now()
);

insert into app_settings (setting_key, setting_value, description)
select 'openai.request_mode', '1', '1 = use openai_services token forwarding, 2 = use openai_codex_profiles'
where not exists (select 1 from app_settings where setting_key = 'openai.request_mode');

insert into app_settings (setting_key, setting_value, description)
select 'openai.concurrent_limit', '20', 'Global concurrent request limit for OpenAI/Codex upstream services'
where not exists (select 1 from app_settings where setting_key = 'openai.concurrent_limit');

insert into app_settings (setting_key, setting_value, description)
select 'announcements.badge_default', '0', 'Default announcement badge count before a user reads current announcements'
where not exists (select 1 from app_settings where setting_key = 'announcements.badge_default');

create table if not exists announcements (
  id bigserial primary key,
  title text not null,
  content text not null,
  active boolean not null default true,
  published_at timestamp with time zone not null default now(),
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists announcement_user_state (
  user_id uuid primary key references users(id) on delete cascade,
  last_seen_at timestamp with time zone not null default 'epoch',
  updated_at timestamp with time zone not null default now()
);

create table if not exists openai_services (
  id bigserial primary key,
  api_endpoint text not null,
  token text not null,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

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
create index if not exists idx_redeem_codes_holder_user_id
  on redeem_codes(holder_user_id);
create index if not exists idx_redeem_codes_expires_at
  on redeem_codes(expires_at);
create index if not exists idx_announcements_active_published_at
  on announcements(active, published_at desc);
create index if not exists idx_announcement_user_state_last_seen_at
  on announcement_user_state(last_seen_at);
create index if not exists idx_openai_codex_profiles_service_id
  on openai_codex_profiles(openai_service_id);
