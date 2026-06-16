-- Run this once on existing databases after moving OpenAI/Codex global settings
-- into app_settings.

create table if not exists app_settings (
  setting_key text primary key,
  setting_value text not null,
  description text,
  updated_at timestamp with time zone not null default now()
);

insert into app_settings (setting_key, setting_value, description)
values ('openai.request_mode', '1', '1 = use openai_services token forwarding, 2 = use openai_codex_profiles')
on conflict (setting_key) do nothing;

insert into app_settings (setting_key, setting_value, description)
values ('openai.concurrent_limit', '20', 'Global concurrent request limit for OpenAI/Codex upstream services')
on conflict (setting_key) do nothing;

create table if not exists openai_services (
  id bigserial primary key,
  api_endpoint text not null,
  token text not null,
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

insert into claude_services (api_endpoint, token, concurrent_limit)
select
  'https://token-plan-cn.xiaomimimo.com/anthropic',
  'tp-cfo7o6q5y38o2gwrrttalgzw8v4xuleci5id7nqbsmfdoqpk',
  20
where not exists (
  select 1
  from claude_services
  where api_endpoint = 'https://token-plan-cn.xiaomimimo.com/anthropic'
    and token = 'tp-cfo7o6q5y38o2gwrrttalgzw8v4xuleci5id7nqbsmfdoqpk'
);

insert into app_settings (setting_key, setting_value, description)
values (
  'billing.cost_multiplier',
  '1.2',
  'Multiplier applied to calculated request cost before logging and balance deduction'
)
on conflict (setting_key) do nothing;

insert into app_settings (setting_key, setting_value, description)
values (
  'announcements.badge_default',
  '0',
  'Default announcement badge count before a user reads current announcements'
)
on conflict (setting_key) do nothing;

alter table openai_services
  drop column if exists request_mode;

alter table openai_services
  drop column if exists concurrent_limit;

alter table openai_services
  drop column if exists force_replace_codex_model;

alter table openai_services
  drop column if exists codex_replacement_model;

alter table users
  alter column balance set default 5;

create table if not exists redeem_codes (
  id bigserial primary key,
  code text unique not null,
  batch text not null default 'default',
  amount numeric(18, 6) not null,
  expires_at timestamp with time zone not null,
  holder_user_id uuid references users(id),
  redeemed_ip text,
  redeemed_at timestamp with time zone,
  expired_deducted_at timestamp with time zone,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

alter table redeem_codes
  add column if not exists expired_deducted_at timestamp with time zone;

alter table redeem_codes
  add column if not exists batch text not null default 'default';

alter table redeem_codes
  add column if not exists redeemed_ip text;

create index if not exists idx_redeem_codes_holder_user_id
  on redeem_codes(holder_user_id);

create index if not exists idx_redeem_codes_expires_at
  on redeem_codes(expires_at);

create index if not exists idx_redeem_codes_batch
  on redeem_codes(batch);

create unique index if not exists idx_redeem_codes_batch_holder_user_id
  on redeem_codes(batch, holder_user_id);

create unique index if not exists idx_redeem_codes_batch_redeemed_ip
  on redeem_codes(batch, redeemed_ip);

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

create index if not exists idx_announcements_active_published_at
  on announcements(active, published_at desc);

create index if not exists idx_announcement_user_state_last_seen_at
  on announcement_user_state(last_seen_at);

create table if not exists novels (
  id bigserial primary key,
  user_id uuid not null references users(id) on delete cascade,
  title text not null,
  author text not null default '',
  excerpt text not null default '',
  content_object_key text not null,
  content_url text not null,
  content_size bigint not null default 0,
  content_sha256 text not null default '',
  rating_count int not null default 0,
  rating_total numeric(18, 6) not null default 0,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

alter table novels
  add column if not exists excerpt text not null default '';

alter table novels
  add column if not exists content_object_key text;

alter table novels
  add column if not exists content_url text;

alter table novels
  add column if not exists content_size bigint not null default 0;

alter table novels
  add column if not exists content_sha256 text not null default '';

alter table novels
  alter column content_object_key set not null;

alter table novels
  alter column content_url set not null;

alter table novels
  drop column if exists content;

create table if not exists novel_ratings (
  novel_id bigint not null references novels(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  score int not null check (score between 1 and 5),
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  primary key (novel_id, user_id)
);

create index if not exists idx_novels_created_at
  on novels(created_at desc);

create index if not exists idx_novels_rating
  on novels(rating_count desc, rating_total desc);

create index if not exists idx_novel_ratings_user_id
  on novel_ratings(user_id);

create table if not exists web_chat_history_files (
  id bigserial primary key,
  user_id uuid not null references users(id) on delete cascade,
  sequence int not null,
  object_key text not null,
  content_url text not null default '',
  size_bytes bigint not null default 0,
  turn_count int not null default 0,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now(),
  unique (user_id, sequence)
);

create index if not exists idx_web_chat_history_files_user_updated
  on web_chat_history_files(user_id, updated_at desc);
