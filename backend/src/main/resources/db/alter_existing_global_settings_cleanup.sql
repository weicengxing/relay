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

alter table users
  alter column balance set default 5;

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

alter table redeem_codes
  add column if not exists expired_deducted_at timestamp with time zone;

create index if not exists idx_redeem_codes_holder_user_id
  on redeem_codes(holder_user_id);

create index if not exists idx_redeem_codes_expires_at
  on redeem_codes(expires_at);

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
