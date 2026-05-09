create table if not exists web_chat_model_configs (
  id bigserial primary key,
  name text not null,
  base_url text not null default 'https://chatgpt.com',
  model text not null default 'gpt-5-3',
  auth_header text,
  bearer_token text,
  account_id text,
  conduit_token text,
  sentinel_token text,
  cookie text,
  oai_device_id text,
  oai_session_id text,
  oai_client_build_number text,
  oai_client_version text,
  oai_is text,
  user_agent text,
  call_prepare boolean not null default true,
  enabled boolean not null default true,
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create table if not exists web_chat_user_sessions (
  user_id uuid primary key references users(id) on delete cascade,
  config_id bigint not null references web_chat_model_configs(id),
  conversation_id text,
  parent_message_id text not null default 'client-created-root',
  updated_at timestamp with time zone not null default now()
);

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

create index if not exists idx_web_chat_model_configs_enabled
  on web_chat_model_configs(enabled, id);

create index if not exists idx_web_chat_user_sessions_config_id
  on web_chat_user_sessions(config_id);

create index if not exists idx_web_chat_history_files_user_updated
  on web_chat_history_files(user_id, updated_at desc);
