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
  created_at timestamp with time zone not null default now(),
  updated_at timestamp with time zone not null default now()
);

create index if not exists idx_api_keys_user_id on api_keys(user_id);
create index if not exists idx_api_logs_user_id_created_at on api_logs(user_id, created_at desc);
create index if not exists idx_recharge_orders_user_id_created_at
  on recharge_orders(user_id, created_at desc);
