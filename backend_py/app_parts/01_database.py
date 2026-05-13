@contextmanager
def db() -> Iterable[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=5)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA busy_timeout = 5000")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with db() as con:
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA synchronous = NORMAL")
        con.executescript(
            """
            create table if not exists users (
              id text primary key,
              email text unique not null,
              password_hash text not null,
              registration_ip text unique,
              balance text not null default '5.000000',
              status text not null default 'active',
              created_at text not null
            );
            create table if not exists verification_codes (
              email text primary key,
              code text not null,
              expires_at text not null
            );
            create table if not exists api_keys (
              id integer primary key autoincrement,
              user_id text not null references users(id) on delete cascade,
              key_hash text not null,
              key_value text,
              name text,
              status text not null default 'active',
              created_at text not null
            );
            create table if not exists api_logs (
              id integer primary key autoincrement,
              user_id text references users(id) on delete cascade,
              model text,
              prompt_tokens integer not null default 0,
              completion_tokens integer not null default 0,
              cost text not null default '0.000000',
              status text,
              created_at text not null
            );
            create table if not exists request_logs (
              id integer primary key autoincrement,
              user_id text not null references users(id) on delete cascade,
              api_key_id integer not null references api_keys(id) on delete cascade,
              token_name text not null,
              group_key text not null,
              request_type text not null default 'usage',
              client_type text not null default 'UNKNOWN',
              model text,
              use_time_ms integer not null default 0,
              first_token_ms integer not null default 0,
              prompt_tokens integer not null default 0,
              completion_tokens integer not null default 0,
              cache_read_tokens integer not null default 0,
              cache_creation_tokens integer not null default 0,
              cost text not null default '0.000000',
              ip text,
              status text,
              upstream_service_id integer,
              detail text not null default '',
              created_at text not null
            );
            create table if not exists recharge_orders (
              id integer primary key autoincrement,
              user_id text not null references users(id) on delete cascade,
              amount text not null,
              status text not null default 'pending',
              remark text,
              created_at text not null
            );
            create table if not exists app_settings (
              setting_key text primary key,
              setting_value text not null,
              description text,
              updated_at text not null
            );
            create table if not exists announcements (
              id integer primary key autoincrement,
              title text not null,
              content text not null,
              active integer not null default 1,
              published_at text not null,
              created_at text not null,
              updated_at text not null
            );
            create table if not exists announcement_reads (
              user_id text not null references users(id) on delete cascade,
              announcement_id integer not null references announcements(id) on delete cascade,
              read_at text not null,
              primary key (user_id, announcement_id)
            );
            create table if not exists announcement_user_state (
              user_id text primary key references users(id) on delete cascade,
              last_seen_at text not null,
              updated_at text not null
            );
            create table if not exists redeem_codes (
              id integer primary key autoincrement,
              code text unique not null,
              amount text not null,
              expires_at text not null,
              holder_user_id text references users(id),
              redeemed_at text,
              expired_deducted_at text,
              created_at text not null,
              updated_at text not null
            );
            create table if not exists model_catalog (
              id text primary key,
              name text not null,
              provider text not null default 'OpenAI',
              input_price text not null,
              output_price text not null,
              cached_input_price text not null,
              cache_creation_price text not null,
              tags text not null default '',
              sort_order integer not null default 0,
              enabled integer not null default 1
            );
            create table if not exists openai_services (
              id integer primary key autoincrement,
              api_endpoint text not null,
              token text not null,
              concurrent_limit integer not null default 20,
              created_at text not null,
              updated_at text not null
            );
            create table if not exists openai_codex_profiles (
              id integer primary key autoincrement,
              openai_service_id integer not null unique references openai_services(id) on delete cascade,
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
              last_refresh text,
              created_at text not null,
              updated_at text not null
            );
            create table if not exists claude_services (
              id integer primary key autoincrement,
              api_endpoint text not null,
              token text not null,
              concurrent_limit integer not null default 20,
              created_at text not null,
              updated_at text not null
            );
            create table if not exists web_chat_model_configs (
              id integer primary key autoincrement,
              name text not null unique,
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
              call_prepare integer not null default 1,
              enabled integer not null default 1,
              created_at text not null,
              updated_at text not null
            );
            create table if not exists web_chat_user_sessions (
              user_id text primary key references users(id) on delete cascade,
              config_id integer not null references web_chat_model_configs(id),
              conversation_id text,
              parent_message_id text not null default 'client-created-root',
              updated_at text not null
            );
            create table if not exists web_chat_history_files (
              id integer primary key autoincrement,
              user_id text not null references users(id) on delete cascade,
              sequence integer not null,
              object_key text not null,
              content_url text not null default '',
              size_bytes integer not null default 0,
              turn_count integer not null default 0,
              created_at text not null,
              updated_at text not null,
              unique (user_id, sequence)
            );
            create table if not exists novels (
              id integer primary key autoincrement,
              user_id text not null references users(id) on delete cascade,
              title text not null,
              author text not null default '',
              excerpt text not null default '',
              content_object_key text not null,
              content_url text not null,
              content_size integer not null default 0,
              content_sha256 text not null default '',
              rating_count integer not null default 0,
              rating_total text not null default '0',
              created_at text not null,
              updated_at text not null
            );
            create table if not exists novel_ratings (
              novel_id integer not null references novels(id) on delete cascade,
              user_id text not null references users(id) on delete cascade,
              score integer not null,
              created_at text not null,
              updated_at text not null,
              primary key (novel_id, user_id)
            );
            create index if not exists idx_novels_created_at on novels(created_at desc);
            create index if not exists idx_novels_created_id on novels(created_at desc, id desc);
            create index if not exists idx_novels_rating on novels(rating_count desc, rating_total desc);
            create index if not exists idx_novel_ratings_user_id on novel_ratings(user_id);
            create index if not exists idx_web_chat_history_files_user_updated
              on web_chat_history_files(user_id, updated_at desc);
            create index if not exists idx_request_logs_user_created
              on request_logs(user_id, created_at desc, id desc);
            create index if not exists idx_model_catalog_enabled_sort
              on model_catalog(enabled, sort_order, id);
            create index if not exists idx_announcements_active_published
              on announcements(active, published_at desc, id desc);
            """
        )
        normalize_sqlite_schema(con)
        seed_defaults(con)


def normalize_sqlite_schema(con: sqlite3.Connection) -> None:
    expected_novel_columns = [
        "id",
        "user_id",
        "title",
        "author",
        "excerpt",
        "content_object_key",
        "content_url",
        "content_size",
        "content_sha256",
        "rating_count",
        "rating_total",
        "created_at",
        "updated_at",
    ]
    ensure_columns(
        con,
        "novels",
        {
            "content_object_key": "text not null default ''",
            "content_url": "text not null default ''",
            "content_size": "integer not null default 0",
            "content_sha256": "text not null default ''",
        },
    )
    novel_columns = [row["name"] for row in con.execute("pragma table_info(novels)").fetchall()]
    if "content" in novel_columns or novel_columns != expected_novel_columns:
        rebuild_novels_table(con)
    con.execute("drop table if exists web_chat_history")


def ensure_columns(con: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in con.execute(f"pragma table_info({quote_ident(table)})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            con.execute(f"alter table {quote_ident(table)} add column {quote_ident(name)} {definition}")


def rebuild_novels_table(con: sqlite3.Connection) -> None:
    con.commit()
    con.execute("PRAGMA foreign_keys = OFF")
    try:
        con.executescript(
            """
            drop table if exists novels_new;
            create table novels_new (
              id integer primary key autoincrement,
              user_id text not null references users(id) on delete cascade,
              title text not null,
              author text not null default '',
              excerpt text not null default '',
              content_object_key text not null,
              content_url text not null,
              content_size integer not null default 0,
              content_sha256 text not null default '',
              rating_count integer not null default 0,
              rating_total text not null default '0',
              created_at text not null,
              updated_at text not null
            );
            insert into novels_new (
              id, user_id, title, author, excerpt, content_object_key, content_url,
              content_size, content_sha256, rating_count, rating_total, created_at, updated_at
            )
            select
              id, user_id, title, coalesce(author, ''), coalesce(excerpt, ''),
              coalesce(content_object_key, ''), coalesce(content_url, ''),
              coalesce(content_size, 0), coalesce(content_sha256, ''),
              coalesce(rating_count, 0), coalesce(rating_total, '0'), created_at, updated_at
            from novels;
            drop table novels;
            alter table novels_new rename to novels;
            create index if not exists idx_novels_created_at on novels(created_at desc);
            create index if not exists idx_novels_created_id on novels(created_at desc, id desc);
            create index if not exists idx_novels_rating on novels(rating_count desc, rating_total desc);
            """
        )
        con.commit()
    finally:
        con.execute("PRAGMA foreign_keys = ON")


def seed_defaults(con: sqlite3.Connection) -> None:
    ts = now_iso()
    settings = [
        ("openai.request_mode", "2", "1 = token forwarding, 2 = codex profile request mode"),
        ("openai.concurrent_limit", "20", "Global concurrent request limit"),
        ("billing.cost_multiplier", "1.2", "Cost multiplier"),
        ("announcements.badge_default", "0", "Default announcement badge count"),
        ("maintenance.write_disabled", "false", "Disable database write APIs during migration"),
        ("auth.turnstile_enabled", "true", "Require Cloudflare Turnstile verification during registration"),
        ("recharge.alipay_qr_image", "", "Alipay payment QR image URL or data URL"),
        ("recharge.wechat_qr_image", "", "WeChat payment QR image URL or data URL"),
    ]
    con.executemany(
        """
        insert into app_settings(setting_key, setting_value, description, updated_at)
        values (?, ?, ?, ?)
        on conflict(setting_key) do nothing
        """,
        [(k, v, d, ts) for k, v, d in settings],
    )
    models = [
        ("gpt-5.5", "GPT-5.5", "OpenAI", "1.2500", "10.0000", "0.1250", "1.2500", "coding,reasoning", 1),
        ("gpt-5.4", "GPT-5.4", "OpenAI", "1.0000", "8.0000", "0.1000", "1.0000", "balanced", 2),
        ("gpt-5.3-codex", "GPT-5.3 Codex", "OpenAI", "1.0000", "8.0000", "0.1000", "1.0000", "codex", 3),
        ("gpt-5.4-mini", "GPT-5.4 Mini", "OpenAI", "0.2500", "2.0000", "0.0250", "0.2500", "fast,cheap", 4),
        ("gpt-5-5-thinking", "GPT-5.5 Thinking", "OpenAI", "1.2500", "10.0000", "0.1250", "1.2500", "chat", 5),
        ("gpt-5-3", "GPT-5.3", "OpenAI", "1.0000", "8.0000", "0.1000", "1.0000", "chat", 6),
        ("mimo-v2-omni", "MiMo V2 Omni", "Xiaomi", "0.0000", "0.0000", "0.0000", "0.0000", "xiaomi,mimo,claude", 20),
        ("mimo-v2-pro", "MiMo V2 Pro", "Xiaomi", "0.0000", "0.0000", "0.0000", "0.0000", "xiaomi,mimo,claude", 21),
        ("mimo-v2-tts", "MiMo V2 TTS", "Xiaomi", "0.0000", "0.0000", "0.0000", "0.0000", "xiaomi,mimo,tts", 22),
        ("mimo-v2.5", "MiMo V2.5", "Xiaomi", "0.0000", "0.0000", "0.0000", "0.0000", "xiaomi,mimo,claude", 23),
        ("mimo-v2.5-pro", "MiMo V2.5 Pro", "Xiaomi", "0.0000", "0.0000", "0.0000", "0.0000", "xiaomi,mimo,claude", 24),
        ("mimo-v2.5-tts", "MiMo V2.5 TTS", "Xiaomi", "0.0000", "0.0000", "0.0000", "0.0000", "xiaomi,mimo,tts", 25),
        ("mimo-v2.5-tts-voiceclone", "MiMo V2.5 TTS Voice Clone", "Xiaomi", "0.0000", "0.0000", "0.0000", "0.0000", "xiaomi,mimo,tts,voice", 26),
        ("mimo-v2.5-tts-voicedesign", "MiMo V2.5 TTS Voice Design", "Xiaomi", "0.0000", "0.0000", "0.0000", "0.0000", "xiaomi,mimo,tts,voice", 27),
    ]
    con.executemany(
        """
        insert into model_catalog
          (id, name, provider, input_price, output_price, cached_input_price, cache_creation_price, tags, sort_order)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?)
        on conflict(id) do nothing
        """,
        models,
    )
    import_chat_profiles(con)
    import_codex_profiles(con)
    dedupe_codex_profiles(con)


def import_chat_profiles(con: sqlite3.Connection) -> None:
    if not CHAT_PROFILES_PATH.exists():
        return
    try:
        data = json.loads(CHAT_PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    profiles = data.get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, list):
        return
    ts = now_iso()
    default_model = data.get("model") or DEFAULT_WEB_MODEL
    for idx, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            continue
        name = profile.get("name") or f"account_{idx + 1}"
        if is_placeholder(profile.get("bearer_token")) and is_placeholder(profile.get("cookie")):
            continue
        con.execute(
            """
            insert into web_chat_model_configs
              (name, base_url, model, auth_header, bearer_token, account_id, conduit_token,
               sentinel_token, cookie, oai_device_id, oai_session_id, user_agent, call_prepare,
               enabled, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(name) do update set
              base_url=excluded.base_url, model=excluded.model, auth_header=excluded.auth_header,
              bearer_token=excluded.bearer_token, account_id=excluded.account_id,
              conduit_token=excluded.conduit_token, sentinel_token=excluded.sentinel_token,
              cookie=excluded.cookie, oai_device_id=excluded.oai_device_id,
              oai_session_id=excluded.oai_session_id, user_agent=excluded.user_agent,
              call_prepare=excluded.call_prepare, enabled=excluded.enabled, updated_at=excluded.updated_at
            """,
            (
                str(name),
                profile.get("base_url") or data.get("base_url") or "https://chat.sharedchat.cc",
                profile.get("model") or default_model,
                profile.get("auth_header"),
                profile.get("bearer_token"),
                profile.get("account_id"),
                profile.get("conduit_token"),
                profile.get("sentinel_token"),
                profile.get("cookie"),
                profile.get("oai_device_id"),
                profile.get("oai_session_id"),
                profile.get("user_agent"),
                1 if profile.get("call_prepare", data.get("call_prepare", False)) else 0,
                1,
                ts,
                ts,
            ),
        )


def import_codex_profiles(con: sqlite3.Connection) -> None:
    if not CODEX_PROFILES_PATH.exists():
        return
    try:
        data = json.loads(CODEX_PROFILES_PATH.read_text(encoding="utf-8-sig"))
    except Exception:
        return
    profiles = data.get("profiles") if isinstance(data, dict) else None
    defaults = data.get("request_defaults") if isinstance(data.get("request_defaults"), dict) else {}
    if not isinstance(profiles, list):
        return
    ts = now_iso()
    for idx, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            continue
        profile_name = profile.get("name") or f"codex_{idx + 1}"
        tokens = profile.get("tokens") if isinstance(profile.get("tokens"), dict) else {}
        access_token = first_non_blank(tokens.get("access_token"), profile.get("access_token"), profile.get("OPENAI_API_KEY"))
        openai_key = first_non_blank(profile.get("OPENAI_API_KEY"), profile.get("openai_api_key"))
        if is_placeholder(access_token) and is_placeholder(openai_key):
            continue
        base_url = first_non_blank(profile.get("base_url"), defaults.get("base_url"), "https://chatgpt.com/backend-api/codex")
        existing = con.execute(
            """
            select s.id
            from openai_services s
            join openai_codex_profiles p on p.openai_service_id = s.id
            where p.profile_name = ?
            """,
            (profile_name,),
        ).fetchone()
        if existing:
            service_id = existing["id"]
            con.execute(
                "update openai_services set api_endpoint = ?, token = ?, updated_at = ? where id = ?",
                (base_url, access_token or openai_key or "", ts, service_id),
            )
        else:
            con.execute(
                "insert into openai_services(api_endpoint, token, concurrent_limit, created_at, updated_at) values (?, ?, ?, ?, ?)",
                (base_url, access_token or openai_key or "", 20, ts, ts),
            )
            service_id = con.execute("select last_insert_rowid()").fetchone()[0]
        con.execute(
            """
            insert into openai_codex_profiles
              (openai_service_id, profile_name, auth_mode, openai_api_key, access_token, account_id,
               id_token, refresh_token, client_id, base_url, model, reasoning_effort, last_refresh, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(openai_service_id) do update set
              profile_name=excluded.profile_name, auth_mode=excluded.auth_mode,
              openai_api_key=excluded.openai_api_key, access_token=excluded.access_token,
              account_id=excluded.account_id, id_token=excluded.id_token,
              refresh_token=excluded.refresh_token, client_id=excluded.client_id, base_url=excluded.base_url,
              model=excluded.model, reasoning_effort=excluded.reasoning_effort,
              last_refresh=excluded.last_refresh, updated_at=excluded.updated_at
            """,
            (
                service_id,
                profile_name,
                profile.get("auth_mode") or "chatgpt",
                openai_key,
                access_token,
                tokens.get("account_id") or profile.get("account_id"),
                tokens.get("id_token") or profile.get("id_token"),
                tokens.get("refresh_token") or profile.get("refresh_token"),
                profile.get("client_id") or data.get("client_id"),
                base_url,
                first_non_blank(profile.get("model"), defaults.get("model"), "gpt-5.5"),
                first_non_blank(profile.get("reasoning_effort"), defaults.get("reasoning_effort"), "high"),
                profile.get("last_refresh"),
                ts,
                ts,
            ),
        )


def dedupe_codex_profiles(con: sqlite3.Connection) -> None:
    rows = con.execute(
        """
        select profile_name, max(openai_service_id) as keep_service_id, count(*) as total
        from openai_codex_profiles
        group by profile_name
        having count(*) > 1
        """
    ).fetchall()
    for row in rows:
        delete_rows = con.execute(
            """
            select openai_service_id
            from openai_codex_profiles
            where profile_name = ? and openai_service_id <> ?
            """,
            (row["profile_name"], row["keep_service_id"]),
        ).fetchall()
        for delete_row in delete_rows:
            con.execute("delete from openai_services where id = ?", (delete_row["openai_service_id"],))
