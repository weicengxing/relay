from __future__ import annotations

import base64
import hashlib
import hmac
import html as html_lib
import json
import os
import random
import re
import secrets
import smtplib
import sqlite3
import ssl
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote, urljoin, urlparse

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("RELAY_PY_DB", str(ROOT / "relay_py.db")))
JWT_SECRET = os.getenv("RELAY_PY_JWT_SECRET", "relay-python-dev-secret-change-me")
CHAT_PROFILES_PATH = Path(os.getenv("RELAY_PY_CHAT_PROFILES", r"D:\freeclaude\chat_profiles.json"))
CODEX_PROFILES_PATH = Path(os.getenv("RELAY_PY_CODEX_PROFILES", r"D:\freeclaude\codex_profiles.json"))
ALLOW_DEV_VERIFY_CODE = os.getenv("RELAY_PY_ALLOW_DEV_VERIFY_CODE", "1") == "1"
DEFAULT_BALANCE = Decimal("5.000000")
OWNER_EMAIL = "2997657261@qq.com"
ROOT_PARENT_MESSAGE_ID = "client-created-root"
SMTP_HOST = os.getenv("QQ_SMTP_HOST", "smtp.qq.com")
SMTP_PORT = int(os.getenv("QQ_SMTP_PORT", "465"))
SMTP_USERNAME = os.getenv("QQ_SMTP_USERNAME", "2997657261@qq.com")
SMTP_PASSWORD = os.getenv("QQ_SMTP_PASSWORD", "mlajppzvoexhdddf")
SMTP_FROM = os.getenv("QQ_SMTP_FROM", SMTP_USERNAME)
VERIFICATION_CODE_TTL_MINUTES = int(os.getenv("VERIFICATION_CODE_TTL_MINUTES", "10"))
TURNSTILE_SECRET = os.getenv("TURNSTILE_SECRET", "")
TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "0x4AAAAAADMr7AGgokgaUM6z")
TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
DEFAULT_WEB_MODEL = "gpt-5-3"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36"
)
DEFAULT_OAI_CLIENT_BUILD_NUMBER = "5561002"
DEFAULT_OAI_CLIENT_VERSION = "prod-8bd5c4ba133b610a0563c545f5e81318b3890627"
DROP_REQUEST_HEADERS = {
    "accept-encoding",
    "content-length",
    "host",
    "authorization",
    "x-api-key",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
DROP_RESPONSE_HEADERS = {
    "connection",
    "content-encoding",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
TEXT_DELTA_TYPES = {"response.output_text.delta", "response.refusal.delta"}
TEXT_DONE_TYPES = {"response.output_text.done", "response.refusal.done"}
DONE_TYPES = {
    "message_stream_complete",
    "response.completed",
    "response.failed",
    "response.incomplete",
    "response.cancelled",
    "done",
}
OUTPUT_TEXT_TYPES = {"output_text", "text", "refusal"}
SUPPORTED_IMAGE_MEDIA_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MODEL_RE = re.compile(r'"model"\s*:\s*"([^"]+)"')
NAME_RE = re.compile(r'"name"\s*:\s*"([^"]+)"')
GITHUB_API_BASE = "https://api.github.com/repos"
GITHUB_NOVEL_REPOSITORY = os.getenv("GITHUB_NOVEL_REPOSITORY", "weicengxing/relay-novel-storage")
GITHUB_NOVEL_BRANCH = os.getenv("GITHUB_NOVEL_BRANCH", "main")
GITHUB_NOVEL_BASE_PATH = os.getenv("GITHUB_NOVEL_BASE_PATH", "novels")
GITHUB_NOVEL_TOKEN = os.getenv("GITHUB_NOVEL_TOKEN", "")
CHAT_HISTORY_ENABLED = os.getenv("CHAT_HISTORY_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
CHAT_HISTORY_MAX_FILE_BYTES = int(os.getenv("CHAT_HISTORY_MAX_FILE_BYTES", str(5 * 1024 * 1024)))
GITHUB_CHAT_HISTORY_REPOSITORY = os.getenv("GITHUB_CHAT_HISTORY_REPOSITORY", "")
GITHUB_CHAT_HISTORY_BRANCH = os.getenv("GITHUB_CHAT_HISTORY_BRANCH", "main")
GITHUB_CHAT_HISTORY_BASE_PATH = os.getenv("GITHUB_CHAT_HISTORY_BASE_PATH", "chat-history")
GITHUB_CHAT_HISTORY_TOKEN = os.getenv("GITHUB_CHAT_HISTORY_TOKEN", "")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def api_ok(data: Any = None) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None, "timestamp": now_iso()}


def api_fail(status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "success": False,
            "data": None,
            "error": {"code": code, "message": message, "details": details},
            "timestamp": now_iso(),
        },
    )


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


def db_write_api(func: Any) -> Any:
    setattr(func, "__db_write_api__", True)
    return func


def maintenance_control_api(func: Any) -> Any:
    setattr(func, "__maintenance_control_api__", True)
    return func


def maintenance_write_disabled() -> bool:
    try:
        with db() as con:
            row = con.execute(
                "select setting_value from app_settings where setting_key = ?",
                ("maintenance.write_disabled",),
            ).fetchone()
        return str(row["setting_value"]).strip().lower() in {"1", "true", "yes", "on"} if row else False
    except sqlite3.Error:
        return False


async def maintenance_request_is_owner(request: Request) -> bool:
    authorization = request.headers.get("authorization")
    if authorization and authorization.startswith("Bearer "):
        try:
            user_id = verify_jwt(authorization[len("Bearer ") :].strip())
            with db() as con:
                row = con.execute("select email from users where id = ?", (user_id,)).fetchone()
            if row and str(row["email"]).lower() == OWNER_EMAIL:
                return True
        except Exception:
            pass

    if request.url.path in {"/api/auth/register-code", "/api/auth/register", "/api/auth/login"}:
        try:
            payload = await request.json()
            email = str(payload.get("email") or "").strip().lower() if isinstance(payload, dict) else ""
            return email == OWNER_EMAIL
        except Exception:
            return False
    return False


class WriteGuardRoute(APIRoute):
    def get_route_handler(self) -> Any:
        original_route_handler = super().get_route_handler()

        async def guarded_route_handler(request: Request) -> Response:
            endpoint = self.endpoint
            if (
                getattr(endpoint, "__db_write_api__", False)
                and not getattr(endpoint, "__maintenance_control_api__", False)
                and maintenance_write_disabled()
                and not await maintenance_request_is_owner(request)
            ):
                raise AppError(503, "WRITE_DISABLED", "Database writes are disabled for maintenance")
            return await original_route_handler(request)

        return guarded_route_handler


@contextmanager
def db() -> Iterable[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with db() as con:
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
               id_token, refresh_token, base_url, model, reasoning_effort, last_refresh, created_at, updated_at)
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            on conflict(openai_service_id) do update set
              profile_name=excluded.profile_name, auth_mode=excluded.auth_mode,
              openai_api_key=excluded.openai_api_key, access_token=excluded.access_token,
              account_id=excluded.account_id, id_token=excluded.id_token,
              refresh_token=excluded.refresh_token, base_url=excluded.base_url,
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


def is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or text.startswith("PASTE_")


def first_non_blank(*values: Any) -> str | None:
    for value in values:
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def decimal_text(value: Decimal | str | float | int) -> str:
    return str(Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP))


def parse_decimal(value: Any) -> Decimal:
    return Decimal(str(value or "0"))


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64url_decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def encode_novel_cursor(row: sqlite3.Row) -> str:
    payload = {"createdAt": row["created_at"], "id": row["id"]}
    return b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))


def decode_novel_cursor(cursor: str) -> tuple[str, int]:
    try:
        payload = json.loads(b64url_decode(cursor).decode("utf-8"))
        created_at = str(payload["createdAt"])
        novel_id = int(payload["id"])
        if not created_at or novel_id < 1:
            raise ValueError
        return created_at, novel_id
    except Exception as exc:
        raise AppError(400, "VALIDATION_FAILED", "Invalid novel cursor") from exc


def trim_slashes(value: Any) -> str:
    return str(value or "").strip().strip("/")


def github_repo_ref(repository: str) -> tuple[str, str]:
    value = (repository or "").strip()
    if value.startswith("https://github.com/"):
        value = value[len("https://github.com/") :]
    elif value.startswith("git@github.com:"):
        value = value[len("git@github.com:") :]
    if value.endswith(".git"):
        value = value[:-4]
    parts = trim_slashes(value).split("/")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return "", ""
    return parts[0], parts[1]


def github_encode_path(path: str) -> str:
    return "/".join(quote(part, safe="") for part in str(path or "").split("/"))


def github_branch(branch: str) -> str:
    return (branch or "").strip() or "main"


def github_headers(token: str, accept: str) -> dict[str, str]:
    return {
        "Accept": accept,
        "Authorization": f"Bearer {token.strip()}",
        "User-Agent": "relay-backend-local",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def github_require_config(repository: str, token: str, label: str) -> tuple[str, str]:
    owner, repo = github_repo_ref(repository)
    if not owner or not repo or not (token or "").strip():
        raise AppError(500, "INTERNAL_ERROR", f"GitHub {label} storage is not configured")
    return owner, repo


def github_is_configured(repository: str, token: str) -> bool:
    owner, repo = github_repo_ref(repository)
    return bool(owner and repo and (token or "").strip())


def github_contents_url(repository: str, object_key: str, branch: str, include_ref: bool) -> str:
    owner, repo = github_repo_ref(repository)
    url = f"{GITHUB_API_BASE}/{owner}/{repo}/contents/{github_encode_path(object_key)}"
    if include_ref:
        url += f"?ref={quote(github_branch(branch), safe='')}"
    return url


def github_raw_url(repository: str, object_key: str, branch: str) -> str:
    owner, repo = github_repo_ref(repository)
    return (
        f"https://raw.githubusercontent.com/{owner}/{repo}/"
        f"{quote(github_branch(branch), safe='')}/{github_encode_path(object_key)}"
    )


def github_read_json_file(repository: str, branch: str, token: str, object_key: str, label: str) -> dict[str, Any] | None:
    github_require_config(repository, token, label)
    url = github_contents_url(repository, object_key, branch, True)
    try:
        with httpx.Client(timeout=60) as client:
            response = client.get(url, headers=github_headers(token, "application/vnd.github+json"))
    except Exception as exc:
        raise AppError(500, "INTERNAL_ERROR", f"Unable to read {label} from GitHub: {exc}") from exc
    if response.status_code == 404:
        return None
    if response.status_code < 200 or response.status_code >= 300:
        raise AppError(500, "INTERNAL_ERROR", f"Unable to read {label} from GitHub: {truncate(response.text, 1000)}")
    payload = response.json()
    encoded = str(payload.get("content") or "")
    content = ""
    if encoded.strip():
        content = base64.b64decode(encoded).decode("utf-8")
    return {"content": content, "sha": payload.get("sha") or "", "size": len(content.encode("utf-8"))}


def github_read_raw_file(content_url: str, token: str, label: str) -> str | None:
    url = str(content_url or "").strip()
    if not url:
        return None
    if not url.startswith("https://raw.githubusercontent.com/"):
        raise AppError(500, "INTERNAL_ERROR", f"Invalid GitHub {label} raw URL")
    headers = {"User-Agent": "relay-backend-local"}
    if (token or "").strip():
        headers["Authorization"] = f"Bearer {token.strip()}"
    try:
        with httpx.Client(timeout=60) as client:
            response = client.get(url, headers=headers)
    except Exception as exc:
        raise AppError(500, "INTERNAL_ERROR", f"Unable to read {label} from GitHub raw URL: {exc}") from exc
    if response.status_code == 404:
        return None
    if response.status_code < 200 or response.status_code >= 300:
        raise AppError(
            500,
            "INTERNAL_ERROR",
            f"Unable to read {label} from GitHub raw URL: {truncate(response.text, 1000)}",
        )
    return response.text


def github_read_file_content(
    repository: str,
    branch: str,
    token: str,
    object_key: str,
    label: str,
    content_url: str = "",
) -> str:
    if github_is_configured(repository, token):
        stored = github_read_json_file(repository, branch, token, object_key, label)
        if stored is not None:
            return str(stored.get("content") or "")
    raw_content = github_read_raw_file(content_url, token, label)
    if raw_content is not None:
        return raw_content
    github_require_config(repository, token, label)
    raise AppError(404, "NOT_FOUND", f"GitHub {label} file not found")


def github_write_file(
    repository: str,
    branch: str,
    token: str,
    object_key: str,
    content: str,
    message: str,
    label: str,
    sha: str | None = None,
) -> dict[str, Any]:
    github_require_config(repository, token, label)
    body: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": github_branch(branch),
    }
    if sha:
        body["sha"] = sha
    try:
        with httpx.Client(timeout=120) as client:
            response = client.put(
                github_contents_url(repository, object_key, branch, False),
                json=body,
                headers={**github_headers(token, "application/vnd.github+json"), "Content-Type": "application/json"},
            )
    except Exception as exc:
        raise AppError(500, "INTERNAL_ERROR", f"Unable to write {label} to GitHub: {exc}") from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise AppError(500, "INTERNAL_ERROR", f"Unable to write {label} to GitHub: {truncate(response.text, 1000)}")
    size_bytes = len(content.encode("utf-8"))
    return {"url": github_raw_url(repository, object_key, branch), "size": size_bytes}


def issue_jwt(user: sqlite3.Row) -> str:
    now = int(time.time())
    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = b64url(
        json.dumps(
            {"sub": user["id"], "email": user["email"], "iat": now, "exp": now + 86400},
            separators=(",", ":"),
        ).encode()
    )
    unsigned = f"{header}.{payload}"
    sig = hmac.new(JWT_SECRET.encode(), unsigned.encode(), hashlib.sha256).digest()
    return f"{unsigned}.{b64url(sig)}"


def verify_jwt(token: str | None) -> str:
    if not token:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")
    parts = token.split(".")
    if len(parts) != 3:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")
    unsigned = f"{parts[0]}.{parts[1]}"
    expected = b64url(hmac.new(JWT_SECRET.encode(), unsigned.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, parts[2]):
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")
    try:
        payload = json.loads(b64url_decode(parts[1]))
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired")
        return str(uuid.UUID(payload["sub"]))
    except Exception as exc:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized") from exc


def bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.startswith("Bearer "):
        return authorization[len("Bearer ") :].strip()
    return None


def current_user_id(authorization: str | None) -> str:
    return verify_jwt(bearer_token(authorization))


def current_owner_user_id(authorization: str | None) -> str:
    user_id = current_user_id(authorization)
    with db() as con:
        row = con.execute("select email from users where id = ?", (user_id,)).fetchone()
    if not row or str(row["email"]).lower() != OWNER_EMAIL:
        raise AppError(403, "FORBIDDEN", "Owner access required")
    return user_id


def sha256_key(value: str) -> str:
    return b64url(hashlib.sha256(value.encode()).digest())


def issue_api_key() -> str:
    return "relay_" + b64url(secrets.token_bytes(32))


def display_key(key_hash: str) -> str:
    return "relay_" + key_hash[:8] + "..."


def verification_email_html(code: str, ttl_minutes: int) -> str:
    digits = "".join(
        "<td style=\"padding:0 6px\">"
        "<div style=\"width:48px;height:56px;line-height:56px;text-align:center;"
        "font-size:28px;font-weight:700;color:#1a1a2e;background:#f4f5f7;"
        "border-radius:10px;font-family:'SF Mono',Consolas,monospace\">"
        f"{digit}</div></td>"
        for digit in code
    )
    return (
        "<!DOCTYPE html><html><head><meta charset=\"UTF-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\"></head>"
        "<body style=\"margin:0;padding:0;background:#f4f5f7;"
        "font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif\">"
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#f4f5f7;padding:32px 16px\">"
        "<tr><td align=\"center\">"
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"max-width:480px;background:#fff;"
        "border-radius:16px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.04)\">"
        "<tr><td style=\"padding:36px 36px 0\">"
        "<table cellpadding=\"0\" cellspacing=\"0\"><tr>"
        "<td style=\"width:40px;height:40px;border-radius:10px;background:#6366f1;text-align:center;"
        "vertical-align:middle\"><span style=\"color:#fff;font-size:20px;line-height:40px\">&#9889;</span></td>"
        "<td style=\"padding-left:10px;font-size:20px;font-weight:800;color:#1a1a2e\">Relay</td>"
        "</tr></table></td></tr>"
        "<tr><td style=\"padding:32px 36px 0\">"
        "<h1 style=\"margin:0;font-size:22px;font-weight:700;color:#1a1a2e\">验证你的邮箱</h1>"
        "<p style=\"margin:8px 0 0;font-size:14px;color:#6e7191;line-height:1.6\">"
        "你正在注册 Relay 账户，请使用以下验证码完成验证：</p>"
        "</td></tr>"
        f"<tr><td style=\"padding:28px 36px\"><table cellpadding=\"0\" cellspacing=\"0\" style=\"margin:0 auto\"><tr>{digits}</tr></table></td></tr>"
        "<tr><td style=\"padding:0 36px 28px\">"
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"background:#f9fafb;border-radius:10px;padding:14px 18px\">"
        "<tr><td style=\"font-size:13px;color:#6e7191;line-height:1.5\">"
        f"验证码有效期为 <strong style=\"color:#1a1a2e\">{ttl_minutes} 分钟</strong>。"
        "如果这不是你本人的操作，请忽略此邮件。"
        "</td></tr></table></td></tr>"
        "<tr><td style=\"padding:0 36px 32px\">"
        "<table width=\"100%\" cellpadding=\"0\" cellspacing=\"0\" style=\"border-top:1px solid #f0f0f3;padding-top:20px\">"
        "<tr><td style=\"font-size:12px;color:#a0a3bd;text-align:center;line-height:1.5\">"
        "此邮件由系统自动发送，请勿回复<br>Relay AI 代理平台"
        "</td></tr></table></td></tr>"
        "</table></td></tr></table></body></html>"
    )


def send_verification_email(email: str, code: str, ttl_minutes: int) -> bool:
    if not SMTP_USERNAME.strip() or not SMTP_PASSWORD.strip() or not SMTP_FROM.strip():
        print(f"[backend_py] QQ SMTP is not configured; skipping verification email for {email}")
        return False
    message = EmailMessage()
    message["From"] = SMTP_FROM
    message["To"] = email
    message["Subject"] = "Relay - 验证码"
    message.set_content(f"你的 Relay 验证码是 {code}，有效期 {ttl_minutes} 分钟。")
    message.add_alternative(verification_email_html(code, ttl_minutes), subtype="html")
    try:
        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=ssl.create_default_context()) as smtp:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
                smtp.send_message(message)
        print(f"[backend_py] sent register code email to {email}")
        return True
    except Exception as exc:
        print(f"[backend_py] failed to send register code email for {email}: {exc}; code={code}")
        return False


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def model_to_response(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "provider": row["provider"],
        "inputPrice": float(row["input_price"]),
        "outputPrice": float(row["output_price"]),
        "cachedInputPrice": float(row["cached_input_price"]),
        "cacheCreationPrice": float(row["cache_creation_price"]),
        "tags": [tag.strip() for tag in (row["tags"] or "").split(",") if tag.strip()],
    }


class RegisterCodeRequest(BaseModel):
    email: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    verificationCode: str
    turnstileToken: str | None = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1)


class WebChatMessageRequest(BaseModel):
    message: str | None = ""
    newConversation: bool | None = False
    model: str | None = None
    images: list[dict[str, Any]] | None = []


class RedeemCodeRequest(BaseModel):
    code: str


class CreateNovelRequest(BaseModel):
    title: str
    author: str | None = ""
    content: str


class RateNovelRequest(BaseModel):
    score: int


class AdminRowRequest(BaseModel):
    values: dict[str, Any]


class AdminSqlRequest(BaseModel):
    sql: str


class AdminMaintenanceRequest(BaseModel):
    writeDisabled: bool


class AdminSettingImageRequest(BaseModel):
    settingKey: str
    fileName: str
    dataUrl: str


class AdminSettingImageDeleteRequest(BaseModel):
    settingKey: str


class AdminBalanceCreditRequest(BaseModel):
    email: str
    amount: Decimal


app = FastAPI(title="Relay Python Backend")
app.router.route_class = WriteGuardRoute
origins = [origin.strip() for origin in os.getenv("RELAY_PY_CORS_ORIGINS", "*").split(",") if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return api_fail(exc.status, exc.code, exc.message, exc.details)


@app.exception_handler(HTTPException)
def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return api_fail(exc.status_code, "HTTP_ERROR", message)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health() -> dict[str, Any]:
    return api_ok({"status": "UP", "service": "relay-backend-py", "timestamp": now_iso()})


@app.get("/api/bootstrap")
def bootstrap() -> dict[str, Any]:
    return api_ok(
        {
            "status": "ready",
            "modules": ["auth", "user", "billing", "proxy", "admin", "log", "web_chat"],
            "coreFeatures": [
                "signup",
                "login",
                "balance",
                "api_keys",
                "model_catalog",
                "chat_proxy",
                "web_chat",
                "request_logs",
                "sqlite",
            ],
            "turnstile": {
                "enabled": turnstile_enabled(),
                "siteKey": TURNSTILE_SITE_KEY,
            },
            "rechargePayment": recharge_payment_settings(),
        }
    )


@app.post("/api/auth/register-code")
@db_write_api
def send_register_code(payload: RegisterCodeRequest) -> dict[str, Any]:
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise AppError(400, "VALIDATION_FAILED", "Invalid email")
    code = f"{random.randint(0, 999999):06d}"
    ttl_minutes = max(1, VERIFICATION_CODE_TTL_MINUTES)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)).isoformat()
    with db() as con:
        con.execute(
            """
            insert into verification_codes(email, code, expires_at) values (?, ?, ?)
            on conflict(email) do update set code=excluded.code, expires_at=excluded.expires_at
            """,
            (email, code, expires_at),
        )
    mail_sent = send_verification_email(email, code, ttl_minutes)
    data = {"email": email, "expiresInMinutes": ttl_minutes, "mailSent": mail_sent}
    if ALLOW_DEV_VERIFY_CODE:
        data["debugCode"] = code
    print(f"[backend_py] register code for {email}: {code}")
    return api_ok(data)


@app.post("/api/auth/register")
@db_write_api
def register(payload: RegisterRequest, request: Request) -> dict[str, Any]:
    verify_turnstile(payload.turnstileToken, request)
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise AppError(400, "VALIDATION_FAILED", "Invalid email")
    if not payload.password:
        raise AppError(400, "VALIDATION_FAILED", "Password is required")
    with db() as con:
        code_row = con.execute("select * from verification_codes where email = ?", (email,)).fetchone()
        if not code_row or code_row["code"] != payload.verificationCode:
            raise AppError(400, "INVALID_VERIFICATION_CODE", "Invalid or expired verification code")
        if datetime.fromisoformat(code_row["expires_at"]) <= datetime.now(timezone.utc):
            raise AppError(400, "INVALID_VERIFICATION_CODE", "Invalid or expired verification code")
        user_id = str(uuid.uuid4())
        try:
            con.execute(
                """
                insert into users(id, email, password_hash, registration_ip, balance, status, created_at)
                values (?, ?, ?, ?, ?, 'active', ?)
                """,
                (
                    user_id,
                    email,
                    payload.password,
                    client_ip(request),
                    decimal_text(DEFAULT_BALANCE),
                    now_iso(),
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise AppError(409, "CONFLICT", "Email or registration IP has already been used") from exc
        con.execute("delete from verification_codes where email = ?", (email,))
        user = con.execute("select * from users where id = ?", (user_id,)).fetchone()
    return api_ok(auth_response(user))


@app.post("/api/auth/login")
@db_write_api
def login(payload: LoginRequest) -> dict[str, Any]:
    email = payload.email.strip().lower()
    with db() as con:
        user = con.execute("select * from users where email = ?", (email,)).fetchone()
    if not user or payload.password != user["password_hash"]:
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid email or password")
    with db() as con:
        deduct_expired_redeem_codes(con, user["id"])
        user = con.execute("select * from users where id = ?", (user["id"],)).fetchone()
    return api_ok(auth_response(user))


def auth_response(user: sqlite3.Row) -> dict[str, Any]:
    return {"userId": user["id"], "email": user["email"], "balance": float(user["balance"]), "token": issue_jwt(user)}


@app.get("/api/balance")
@db_write_api
def balance(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    with db() as con:
        deduct_expired_redeem_codes(con, user_id)
        user = con.execute("select balance from users where id = ?", (user_id,)).fetchone()
    if not user:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")
    return api_ok({"balance": float(user["balance"])})


@app.get("/api/balance/stream")
@db_write_api
def balance_stream(authorization: str | None = Header(default=None)) -> StreamingResponse:
    user_id = current_user_id(authorization)
    with db() as con:
        deduct_expired_redeem_codes(con, user_id)
        user = con.execute("select balance from users where id = ?", (user_id,)).fetchone()
    if not user:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")
    payload = json.dumps({"balance": float(user["balance"])}, ensure_ascii=False)
    return StreamingResponse(iter([f"event: balance\ndata: {payload}\n\n"]), media_type="text/event-stream")


@app.get("/api/api-keys")
def list_api_keys(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    with db() as con:
        rows = con.execute(
            "select * from api_keys where user_id = ? and status = 'active' order by id desc", (user_id,)
        ).fetchall()
    return api_ok([api_key_response(row) for row in rows])


@app.post("/api/api-keys")
@db_write_api
def create_api_key(payload: CreateApiKeyRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    name = payload.name.strip()
    key = issue_api_key()
    with db() as con:
        exists = con.execute(
            "select 1 from api_keys where user_id = ? and name = ? and status = 'active'", (user_id, name)
        ).fetchone()
        if exists:
            raise AppError(409, "CONFLICT", "API key name already exists")
        con.execute(
            "insert into api_keys(user_id, key_hash, key_value, name, status, created_at) values (?, ?, ?, ?, 'active', ?)",
            (user_id, sha256_key(key), key, name, now_iso()),
        )
        row = con.execute("select * from api_keys where id = last_insert_rowid()").fetchone()
    return api_ok(api_key_response(row))


@app.delete("/api/api-keys/{key_id}")
@db_write_api
def revoke_api_key(key_id: int, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    with db() as con:
        cur = con.execute(
            "update api_keys set status = 'revoked' where id = ? and user_id = ? and status = 'active'",
            (key_id, user_id),
        )
        if cur.rowcount == 0:
            raise AppError(404, "NOT_FOUND", "API key not found")
    return api_ok(None)


def api_key_response(row: sqlite3.Row) -> dict[str, Any]:
    key = row["key_value"] or display_key(row["key_hash"])
    return {"id": row["id"], "name": row["name"], "key": key, "status": row["status"], "createdAt": row["created_at"]}


@app.get("/api/request-logs")
def request_logs(limit: int = 100, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    limit = max(1, min(int(limit), 200))
    with db() as con:
        rows = con.execute(
            "select * from request_logs where user_id = ? order by created_at desc limit ?", (user_id, limit)
        ).fetchall()
    return api_ok([request_log_response(row) for row in rows])


def request_log_response(row: sqlite3.Row) -> dict[str, Any]:
    detail = row["detail"] or ""
    return {
        "id": row["id"],
        "createdAt": row["created_at"],
        "token": row["token_name"],
        "group": row["group_key"],
        "type": row["request_type"],
        "model": row["model"],
        "useTimeMs": row["use_time_ms"],
        "firstTokenMs": row["first_token_ms"],
        "inputTokens": row["prompt_tokens"],
        "outputTokens": row["completion_tokens"],
        "cacheReadTokens": row["cache_read_tokens"],
        "cacheCreationTokens": row["cache_creation_tokens"],
        "cost": float(row["cost"]),
        "ip": row["ip"],
        "status": row["status"],
        "upstreamServiceId": row["upstream_service_id"],
        "detailLines": detail.splitlines() if detail else [],
    }


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def admin_table_names(con: sqlite3.Connection) -> set[str]:
    rows = con.execute(
        """
        select name from sqlite_master
        where type = 'table' and name not like 'sqlite_%'
        order by name
        """
    ).fetchall()
    return {row["name"] for row in rows}


def admin_require_table(con: sqlite3.Connection, table: str) -> str:
    names = admin_table_names(con)
    if table not in names:
        raise AppError(404, "NOT_FOUND", "SQLite table not found")
    return table


def admin_columns(con: sqlite3.Connection, table: str) -> list[dict[str, Any]]:
    rows = con.execute(f"pragma table_info({quote_ident(table)})").fetchall()
    return [
        {
            "name": row["name"],
            "type": row["type"] or "",
            "notNull": bool(row["notnull"]),
            "defaultValue": row["dflt_value"],
            "primaryKey": int(row["pk"] or 0),
        }
        for row in rows
    ]


def admin_json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"type": "blob", "base64": base64.b64encode(value).decode("ascii")}
    return value


def admin_row_response(row: sqlite3.Row) -> dict[str, Any]:
    return {key: admin_json_value(row[key]) for key in row.keys()}


def admin_sql_result_rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [admin_row_response(row) for row in rows]


def admin_clean_values(columns: list[dict[str, Any]], values: dict[str, Any]) -> dict[str, Any]:
    allowed = {column["name"] for column in columns}
    cleaned: dict[str, Any] = {}
    rejected = []
    for key, value in values.items():
        if key in {"rowid", "_rowid"}:
            continue
        if key not in allowed:
            rejected.append(key)
            continue
        if isinstance(value, (dict, list)):
            cleaned[key] = json.dumps(value, ensure_ascii=False)
        else:
            cleaned[key] = value
    if rejected:
        raise AppError(400, "VALIDATION_FAILED", "Unknown SQLite column", {"columns": rejected})
    return cleaned


@app.get("/api/admin/sqlite/tables")
def admin_sqlite_tables(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    current_owner_user_id(authorization)
    with db() as con:
        tables = []
        for name in sorted(admin_table_names(con)):
            qname = quote_ident(name)
            row_count = con.execute(f"select count(*) as count from {qname}").fetchone()["count"]
            columns = admin_columns(con, name)
            tables.append(
                {
                    "name": name,
                    "rowCount": row_count,
                    "columnCount": len(columns),
                    "primaryKey": [column["name"] for column in columns if column["primaryKey"]],
                }
            )
    return api_ok({"tables": tables, "ownerEmail": OWNER_EMAIL})


@app.get("/api/admin/maintenance")
def admin_maintenance(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    current_owner_user_id(authorization)
    return api_ok({"writeDisabled": maintenance_write_disabled()})


@app.put("/api/admin/maintenance")
@db_write_api
@maintenance_control_api
def admin_set_maintenance(
    payload: AdminMaintenanceRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    value = "true" if payload.writeDisabled else "false"
    with db() as con:
        con.execute(
            """
            insert into app_settings(setting_key, setting_value, description, updated_at)
            values (?, ?, ?, ?)
            on conflict(setting_key) do update set
              setting_value=excluded.setting_value,
              description=excluded.description,
              updated_at=excluded.updated_at
            """,
            ("maintenance.write_disabled", value, "Disable database write APIs during migration", now_iso()),
        )
    return api_ok({"writeDisabled": payload.writeDisabled})


@app.post("/api/admin/settings/image")
@db_write_api
def admin_upload_setting_image(
    payload: AdminSettingImageRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    setting_key = payload.settingKey.strip()
    if not setting_key:
        raise AppError(400, "VALIDATION_FAILED", "Setting key is required")
    with db() as con:
        row = con.execute("select setting_value from app_settings where setting_key = ?", (setting_key,)).fetchone()
        if not row:
            raise AppError(404, "NOT_FOUND", "Setting not found")
        old_value = str(row["setting_value"] or "")
        relative_url = save_setting_image(payload.fileName, payload.dataUrl, setting_key)
        if old_value != relative_url:
            delete_setting_image(old_value)
        con.execute(
            """
            update app_settings
            set setting_value = ?, updated_at = ?
            where setting_key = ?
            """,
            (relative_url, now_iso(), setting_key),
        )
    return api_ok({"settingKey": setting_key, "settingValue": relative_url})


@app.post("/api/admin/settings/image/delete")
@db_write_api
def admin_delete_setting_image(
    payload: AdminSettingImageDeleteRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    setting_key = payload.settingKey.strip()
    if not setting_key:
        raise AppError(400, "VALIDATION_FAILED", "Setting key is required")
    with db() as con:
        row = con.execute("select setting_value from app_settings where setting_key = ?", (setting_key,)).fetchone()
        if not row:
            raise AppError(404, "NOT_FOUND", "Setting not found")
        delete_setting_image(str(row["setting_value"] or ""))
        con.execute(
            """
            update app_settings
            set setting_value = '', updated_at = ?
            where setting_key = ?
            """,
            (now_iso(), setting_key),
        )
    return api_ok({"settingKey": setting_key, "settingValue": ""})


@app.post("/api/admin/users/balance-credit")
@db_write_api
def admin_credit_user_balance(
    payload: AdminBalanceCreditRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    email = payload.email.strip().lower()
    if not email or "@" not in email:
        raise AppError(400, "VALIDATION_FAILED", "Invalid email")
    if payload.amount <= 0:
        raise AppError(400, "VALIDATION_FAILED", "Amount must be greater than 0")
    credit = parse_decimal(payload.amount) * Decimal("10")
    with db() as con:
        user = con.execute("select * from users where email = ?", (email,)).fetchone()
        if not user:
            raise AppError(404, "NOT_FOUND", "User not found")
        next_balance = add_balance(con, user["id"], credit)
    return api_ok(
        {
            "email": email,
            "inputAmount": float(payload.amount),
            "creditedAmount": float(credit),
            "balance": float(next_balance),
        }
    )


@app.get("/api/admin/sqlite/tables/{table}/rows")
def admin_sqlite_rows(
    table: str,
    limit: int = 100,
    offset: int = 0,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    with db() as con:
        admin_require_table(con, table)
        qname = quote_ident(table)
        columns = admin_columns(con, table)
        total = con.execute(f"select count(*) as count from {qname}").fetchone()["count"]
        rows = con.execute(f"select rowid as _rowid, * from {qname} order by rowid desc limit ? offset ?", (limit, offset)).fetchall()
    return api_ok(
        {
            "table": table,
            "columns": columns,
            "rows": [admin_row_response(row) for row in rows],
            "limit": limit,
            "offset": offset,
            "total": total,
        }
    )


@app.post("/api/admin/sqlite/tables/{table}/rows")
@db_write_api
def admin_sqlite_create_row(
    table: str,
    payload: AdminRowRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    with db() as con:
        admin_require_table(con, table)
        qname = quote_ident(table)
        columns = admin_columns(con, table)
        values = admin_clean_values(columns, payload.values or {})
        try:
            if values:
                names = list(values.keys())
                sql = f"insert into {qname} ({', '.join(quote_ident(name) for name in names)}) values ({', '.join('?' for _ in names)})"
                cur = con.execute(sql, [values[name] for name in names])
            else:
                cur = con.execute(f"insert into {qname} default values")
            row = con.execute(f"select rowid as _rowid, * from {qname} where rowid = ?", (cur.lastrowid,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise AppError(400, "SQLITE_CONSTRAINT", str(exc)) from exc
        except sqlite3.OperationalError as exc:
            raise AppError(400, "SQLITE_ERROR", str(exc)) from exc
    return api_ok({"row": admin_row_response(row) if row else None})


@app.put("/api/admin/sqlite/tables/{table}/rows/{rowid}")
@db_write_api
def admin_sqlite_update_row(
    table: str,
    rowid: int,
    payload: AdminRowRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    with db() as con:
        admin_require_table(con, table)
        qname = quote_ident(table)
        exists = con.execute(f"select 1 from {qname} where rowid = ?", (rowid,)).fetchone()
        if not exists:
            raise AppError(404, "NOT_FOUND", "SQLite row not found")
        columns = admin_columns(con, table)
        values = admin_clean_values(columns, payload.values or {})
        try:
            if values:
                names = list(values.keys())
                assignments = ", ".join(f"{quote_ident(name)} = ?" for name in names)
                con.execute(f"update {qname} set {assignments} where rowid = ?", [values[name] for name in names] + [rowid])
            row = con.execute(f"select rowid as _rowid, * from {qname} where rowid = ?", (rowid,)).fetchone()
        except sqlite3.IntegrityError as exc:
            raise AppError(400, "SQLITE_CONSTRAINT", str(exc)) from exc
        except sqlite3.OperationalError as exc:
            raise AppError(400, "SQLITE_ERROR", str(exc)) from exc
    return api_ok({"row": admin_row_response(row) if row else None})


@app.delete("/api/admin/sqlite/tables/{table}/rows/{rowid}")
@db_write_api
def admin_sqlite_delete_row(
    table: str,
    rowid: int,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    with db() as con:
        admin_require_table(con, table)
        qname = quote_ident(table)
        exists = con.execute(f"select 1 from {qname} where rowid = ?", (rowid,)).fetchone()
        if not exists:
            raise AppError(404, "NOT_FOUND", "SQLite row not found")
        try:
            con.execute(f"delete from {qname} where rowid = ?", (rowid,))
        except sqlite3.IntegrityError as exc:
            raise AppError(400, "SQLITE_CONSTRAINT", str(exc)) from exc
    return api_ok(None)


@app.post("/api/admin/sqlite/sql")
@db_write_api
def admin_sqlite_execute_sql(
    payload: AdminSqlRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    current_owner_user_id(authorization)
    sql = (payload.sql or "").strip()
    if not sql:
        raise AppError(400, "VALIDATION_FAILED", "SQL is required")
    if "\x00" in sql:
        raise AppError(400, "VALIDATION_FAILED", "SQL contains invalid characters")
    with db() as con:
        before = con.total_changes
        try:
            try:
                cur = con.execute(sql)
                columns = [item[0] for item in cur.description] if cur.description else []
                rows = cur.fetchmany(500) if cur.description else []
                truncated = bool(cur.fetchone()) if cur.description else False
                statement_count = 1
            except sqlite3.ProgrammingError as exc:
                if "one statement at a time" not in str(exc).lower():
                    raise
                con.executescript(sql)
                columns = []
                rows = []
                truncated = False
                statement_count = len([part for part in sql.split(";") if part.strip()])
        except sqlite3.IntegrityError as exc:
            raise AppError(400, "SQLITE_CONSTRAINT", str(exc)) from exc
        except sqlite3.Error as exc:
            raise AppError(400, "SQLITE_ERROR", str(exc)) from exc
        changed = con.total_changes - before
    return api_ok(
        {
            "columns": columns,
            "rows": admin_sql_result_rows(rows),
            "rowCount": len(rows),
            "truncated": truncated,
            "changes": changed,
            "statementCount": statement_count,
        }
    )


@app.get("/api/models")
def models() -> dict[str, Any]:
    with db() as con:
        rows = con.execute(
            """
            select * from model_catalog
            where enabled = 1
            order by sort_order, id
            """
        ).fetchall()
    return api_ok([model_to_response(row) for row in rows])


@app.get("/v1/models")
def openai_models() -> dict[str, Any]:
    with db() as con:
        rows = con.execute(
            """
            select * from model_catalog
            where enabled = 1
              and provider = 'OpenAI'
            order by sort_order, id
            """
        ).fetchall()
    return {
        "object": "list",
        "data": [
            {
                "id": row["id"],
                "object": "model",
                "created": 0,
                "owned_by": "relay",
            }
            for row in rows
        ],
    }


@app.post("/v1/chat/completions")
@db_write_api
async def openai_chat_completions(request: Request) -> Response:
    body = await request.body()
    raw_key = bearer_token(request.headers.get("authorization")) or request.headers.get("x-api-key")
    try:
        api_key = authenticate_api_key(raw_key)
    except AppError as exc:
        return openai_error(exc.status, exc.message)
    if user_balance(api_key["user_id"]) < Decimal("0"):
        return openai_error(402, "余额不足")

    try:
        payload = json.loads(body.decode("utf-8") or "{}")
    except Exception:
        return openai_error(400, "Request body must be valid JSON")
    if not isinstance(payload, dict):
        return openai_error(400, "Request body must be a JSON object")

    message = openai_messages_to_text(payload.get("messages"))
    if not message:
        return openai_error(400, "messages is required")
    model = str(payload.get("model") or DEFAULT_WEB_MODEL)
    web_payload = WebChatMessageRequest(
        message=message,
        newConversation=bool(payload.get("new_conversation", True)),
        model=model,
        images=openai_messages_to_images(payload.get("messages")),
    )
    stream = bool(payload.get("stream"))
    if stream:
        return StreamingResponse(
            openai_chat_completion_stream(api_key["user_id"], web_payload, model),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    try:
        result = send_web_chat_turn(api_key["user_id"], web_payload, None)
    except Exception as exc:
        message = exc.message if isinstance(exc, AppError) else exception_summary(exc)
        return openai_error(502, message)
    return JSONResponse(openai_chat_completion_response(model, result.get("answer") or ""))


@app.get("/api/announcements")
def announcements(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    with db() as con:
        rows = con.execute(
            "select * from announcements where active = 1 order by published_at desc, id desc"
        ).fetchall()
        state = con.execute("select * from announcement_user_state where user_id = ?", (user_id,)).fetchone()
        last_seen = state["last_seen_at"] if state else "1970-01-01T00:00:00Z"
        badge_default = int(setting(con, "announcements.badge_default", "0"))
    items = [announcement_response(row) for row in rows]
    unread = sum(1 for row in rows if row["published_at"] > last_seen)
    return api_ok({"announcements": items, "unreadCount": unread, "badgeCount": max(unread, badge_default)})


@app.post("/api/announcements/read")
@db_write_api
def mark_announcements_read(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    ts = now_iso()
    with db() as con:
        con.execute(
            """
            insert into announcement_user_state(user_id, last_seen_at, updated_at) values (?, ?, ?)
            on conflict(user_id) do update set last_seen_at=excluded.last_seen_at, updated_at=excluded.updated_at
            """,
            (user_id, ts, ts),
        )
    return announcements(authorization)


def announcement_response(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "content": row["content"],
        "publishedAt": row["published_at"],
    }


@app.post("/api/redeem-codes/redeem")
@db_write_api
def redeem_code(payload: RedeemCodeRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    code = payload.code.strip()
    with db() as con:
        deduct_expired_redeem_codes(con, user_id)
        row = con.execute("select * from redeem_codes where code = ?", (code,)).fetchone()
        if not row:
            raise AppError(404, "NOT_FOUND", "Redeem code does not exist")
        if row["holder_user_id"]:
            raise AppError(409, "CONFLICT", "Redeem code has already been used")
        if row["expires_at"] <= now_iso():
            raise AppError(400, "VALIDATION_FAILED", "Redeem code has expired")
        amount = parse_decimal(row["amount"])
        balance_value = add_balance(con, user_id, amount)
        con.execute(
            "update redeem_codes set holder_user_id = ?, redeemed_at = ?, updated_at = ? where id = ?",
            (user_id, now_iso(), now_iso(), row["id"]),
        )
    return api_ok({"amount": float(amount), "balance": float(balance_value), "expiresAt": row["expires_at"]})


@app.get("/api/novels")
def list_novels(
    page: int = 1,
    size: int = 20,
    q: str = "",
    cursor: str = "",
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    page = max(1, page)
    size = max(1, min(size, 100))
    conditions: list[str] = []
    params: list[Any] = []
    total_params: list[Any] = []
    trimmed_query = q.strip()
    if trimmed_query:
        query = f"%{trimmed_query}%"
        conditions.append("(title like ? or author like ? or excerpt like ?)")
        params.extend([query, query, query])
        total_params.extend([query, query, query])
    if cursor.strip():
        cursor_created_at, cursor_id = decode_novel_cursor(cursor.strip())
        conditions.append("(created_at < ? or (created_at = ? and id < ?))")
        params.extend([cursor_created_at, cursor_created_at, cursor_id])
    where_sql = f"where {' and '.join(conditions)}" if conditions else ""
    total_where_sql = (
        "where title like ? or author like ? or excerpt like ?" if trimmed_query else ""
    )
    with db() as con:
        total = con.execute(f"select count(*) from novels {total_where_sql}", tuple(total_params)).fetchone()[0]
        rows = con.execute(
            f"select * from novels {where_sql} order by created_at desc, id desc limit ?",
            tuple(params) + (size + 1,),
        ).fetchall()
        page_rows = rows[:size]
        ratings = my_ratings(con, user_id)
    has_more = len(rows) > size
    return api_ok(
        {
            "items": [novel_summary(row, ratings.get(row["id"])) for row in page_rows],
            "page": page,
            "size": size,
            "total": total,
            "totalRatings": sum(row["rating_count"] for row in page_rows),
            "hasMore": has_more,
            "nextCursor": encode_novel_cursor(page_rows[-1]) if has_more and page_rows else "",
        }
    )


@app.get("/api/novels/ranking")
def ranking(limit: int = 20, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    limit = max(1, min(limit, 100))
    with db() as con:
        rows = con.execute(
            "select * from novels order by rating_count desc, cast(rating_total as real) desc, created_at desc limit ?",
            (limit,),
        ).fetchall()
        ratings = my_ratings(con, user_id)
    return api_ok([novel_summary(row, ratings.get(row["id"])) for row in rows])


@app.get("/api/novels/{novel_id}")
def novel_detail(novel_id: int, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    with db() as con:
        row = con.execute("select * from novels where id = ?", (novel_id,)).fetchone()
        if not row:
            raise AppError(404, "NOT_FOUND", "Novel not found")
        rating = con.execute(
            "select score from novel_ratings where novel_id = ? and user_id = ?", (novel_id, user_id)
        ).fetchone()
    return api_ok(novel_full(row, rating["score"] if rating else None))


@app.post("/api/novels")
@db_write_api
def create_novel(payload: CreateNovelRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    title = payload.title.strip()
    content = payload.content.strip()
    if not title or not content:
        raise AppError(400, "VALIDATION_FAILED", "Title and content are required")
    excerpt = content[:180]
    ts = now_iso()
    storage = store_novel_to_github(user_id, title, content)
    with db() as con:
        con.execute(
            """
            insert into novels(
              user_id, title, author, excerpt, content_object_key, content_url,
              content_size, content_sha256, created_at, updated_at
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                title,
                (payload.author or "").strip(),
                excerpt,
                storage["objectKey"],
                storage["url"],
                storage["size"],
                storage["sha256"],
                ts,
                ts,
            ),
        )
        row = con.execute("select * from novels where id = last_insert_rowid()").fetchone()
    return api_ok(novel_full(row, None))


@app.post("/api/novels/{novel_id}/ratings")
@db_write_api
def rate_novel(novel_id: int, payload: RateNovelRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    if payload.score < 1 or payload.score > 5:
        raise AppError(400, "VALIDATION_FAILED", "Score must be between 1 and 5")
    ts = now_iso()
    with db() as con:
        row = con.execute("select * from novels where id = ?", (novel_id,)).fetchone()
        if not row:
            raise AppError(404, "NOT_FOUND", "Novel not found")
        old = con.execute(
            "select score from novel_ratings where novel_id = ? and user_id = ?", (novel_id, user_id)
        ).fetchone()
        if old:
            delta_count = 0
            delta_total = payload.score - int(old["score"])
            con.execute(
                "update novel_ratings set score = ?, updated_at = ? where novel_id = ? and user_id = ?",
                (payload.score, ts, novel_id, user_id),
            )
        else:
            delta_count = 1
            delta_total = payload.score
            con.execute(
                "insert into novel_ratings(novel_id, user_id, score, created_at, updated_at) values (?, ?, ?, ?, ?)",
                (novel_id, user_id, payload.score, ts, ts),
            )
        con.execute(
            """
            update novels
            set rating_count = rating_count + ?,
                rating_total = cast(cast(rating_total as real) + ? as text),
                updated_at = ?
            where id = ?
            """,
            (delta_count, delta_total, ts, novel_id),
        )
        row = con.execute("select * from novels where id = ?", (novel_id,)).fetchone()
    return api_ok(novel_full(row, payload.score))


def my_ratings(con: sqlite3.Connection, user_id: str) -> dict[int, int]:
    rows = con.execute("select novel_id, score from novel_ratings where user_id = ?", (user_id,)).fetchall()
    return {row["novel_id"]: row["score"] for row in rows}


def safe_novel_title(title: str) -> str:
    value = re.sub(r"[^A-Za-z0-9\u4e00-\u9fa5._-]+", "-", (title or "").strip())
    value = value or "novel"
    return value[:48]


def novel_object_key(user_id: str, title: str) -> str:
    today = datetime.now().date()
    base_path = trim_slashes(GITHUB_NOVEL_BASE_PATH)
    prefix = f"{base_path}/" if base_path else ""
    return f"{prefix}{today.year}/{today.month:02d}/{user_id}-{uuid.uuid4()}-{safe_novel_title(title)}.txt"


def sha256_urlsafe(data: bytes) -> str:
    return b64url(hashlib.sha256(data).digest())


def store_novel_to_github(user_id: str, title: str, content: str) -> dict[str, Any]:
    object_key = novel_object_key(user_id, title)
    written = github_write_file(
        GITHUB_NOVEL_REPOSITORY,
        GITHUB_NOVEL_BRANCH,
        GITHUB_NOVEL_TOKEN,
        object_key,
        content,
        f"Upload novel {title}",
        "novel",
    )
    raw = content.encode("utf-8")
    return {
        "objectKey": object_key,
        "url": written["url"],
        "size": len(raw),
        "sha256": sha256_urlsafe(raw),
    }


def read_novel_from_github(object_key: str, content_url: str = "") -> str:
    if not object_key:
        raise AppError(500, "INTERNAL_ERROR", "Novel content object key is missing")
    content = github_read_file_content(
        GITHUB_NOVEL_REPOSITORY,
        GITHUB_NOVEL_BRANCH,
        GITHUB_NOVEL_TOKEN,
        object_key,
        "novel",
        content_url,
    )
    if not content.strip():
        raise AppError(500, "INTERNAL_ERROR", "GitHub returned empty novel content")
    return content


def avg_rating(row: sqlite3.Row) -> float:
    count = int(row["rating_count"])
    return 0.0 if count <= 0 else float(parse_decimal(row["rating_total"]) / Decimal(count))


def novel_summary(row: sqlite3.Row, my_rating: int | None) -> dict[str, Any]:
    return {
        "id": row["id"],
        "title": row["title"],
        "author": row["author"],
        "excerpt": row["excerpt"],
        "averageRating": avg_rating(row),
        "ratingCount": row["rating_count"],
        "myRating": my_rating,
        "createdAt": row["created_at"],
    }


def novel_full(row: sqlite3.Row, my_rating: int | None) -> dict[str, Any]:
    data = novel_summary(row, my_rating)
    data.update(
        {
            "content": read_novel_from_github(row["content_object_key"], row["content_url"]),
            "contentUrl": row["content_url"],
            "updatedAt": row["updated_at"],
        }
    )
    return data


@app.get("/api/web-chat/session")
@db_write_api
def web_chat_session(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return api_ok(session_response(find_or_create_web_session(current_user_id(authorization))))


@app.post("/api/web-chat/conversation/reset")
@db_write_api
def reset_web_chat(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    session = find_or_create_web_session(user_id)
    with db() as con:
        con.execute(
            """
            update web_chat_user_sessions
            set conversation_id = null, parent_message_id = ?, updated_at = ?
            where user_id = ?
            """,
            (ROOT_PARENT_MESSAGE_ID, now_iso(), user_id),
        )
    session["conversation_id"] = None
    session["parent_message_id"] = ROOT_PARENT_MESSAGE_ID
    return api_ok(session_response(session))


@app.post("/api/web-chat/messages")
@db_write_api
def web_chat_message(payload: WebChatMessageRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    result = send_web_chat_turn(user_id, payload, None)
    return api_ok(result)


@app.post("/api/web-chat/messages/stream")
@db_write_api
def web_chat_message_stream(payload: WebChatMessageRequest, authorization: str | None = Header(default=None)) -> StreamingResponse:
    user_id = current_user_id(authorization)

    def generate() -> Iterable[str]:
        try:
            stream = stream_web_chat_turn(user_id, payload)
            result = None
            for item in stream:
                if isinstance(item, str):
                    yield item
                else:
                    result = item
            if result is None:
                raise AppError(502, "INTERNAL_ERROR", "Web chat stream ended without a response")
            yield sse_event("done", result)
        except Exception as exc:
            message = exc.message if isinstance(exc, AppError) else str(exc)
            yield sse_event("error", {"message": message})

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.get("/api/web-chat/images/{config_id}/{file_id}")
def web_chat_generated_image(config_id: int, file_id: str, token: str) -> Response:
    verify_web_chat_image_token(config_id, file_id, token)
    with db() as con:
        config = con.execute("select * from web_chat_model_configs where id = ?", (config_id,)).fetchone()
    if not config:
        raise AppError(404, "NOT_FOUND", "Web chat image config not found")
    content, media_type = download_generated_web_image(row_to_dict(config), file_id)
    return Response(content=content, media_type=media_type)


@app.get("/api/web-chat/history")
def chat_history(page: int = 1, size: int = 20, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    page = max(1, page)
    size = max(1, min(size, 50))
    offset = (page - 1) * size
    with db() as con:
        total = con.execute("select count(*) from web_chat_history_files where user_id = ?", (user_id,)).fetchone()[0]
        rows = con.execute(
            """
            select * from web_chat_history_files
            where user_id = ?
            order by updated_at desc, sequence desc
            limit ? offset ?
            """,
            (user_id, size, offset),
        ).fetchall()
    return api_ok(
        {
            "items": [chat_history_file_response(row) for row in rows],
            "page": page,
            "size": size,
            "total": total,
            "hasMore": offset + len(rows) < total,
        }
    )


@app.get("/api/web-chat/history/{turn_id}")
def chat_history_detail(turn_id: int, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = current_user_id(authorization)
    with db() as con:
        row = con.execute(
            "select * from web_chat_history_files where id = ? and user_id = ?", (turn_id, user_id)
        ).fetchone()
    if not row:
        raise AppError(404, "NOT_FOUND", "Chat history not found")
    content = github_read_file_content(
        GITHUB_CHAT_HISTORY_REPOSITORY,
        GITHUB_CHAT_HISTORY_BRANCH,
        GITHUB_CHAT_HISTORY_TOKEN,
        row["object_key"],
        "chat history",
        row["content_url"],
    )
    return api_ok({"file": chat_history_file_response(row), "turns": parse_chat_history_turns(content)})


def chat_history_file_response(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "sequence": row["sequence"],
        "objectKey": row["object_key"],
        "contentUrl": row["content_url"],
        "sizeBytes": row["size_bytes"],
        "turnCount": row["turn_count"],
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
    }


def chat_history_object_key(user_id: str, sequence: int) -> str:
    base_path = trim_slashes(GITHUB_CHAT_HISTORY_BASE_PATH)
    prefix = f"{base_path}/" if base_path else ""
    return f"{prefix}{user_id}/{user_id}-{sequence:06d}.jsonl"


def image_history_documents(images: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for image in images or []:
        if not isinstance(image, dict):
            continue
        result.append(
            {
                "id": image.get("id"),
                "name": image.get("name"),
                "media_type": image.get("mediaType") or image.get("media_type"),
                "size": image.get("size"),
                "width": image.get("width"),
                "height": image.get("height"),
                "data": image.get("data"),
                "url": image.get("url"),
                "page_url": image.get("pageUrl") or image.get("page_url"),
                "source": image.get("source"),
            }
        )
    return result


def source_history_documents(sources: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        result.append(
            {
                "title": source.get("title"),
                "url": source.get("url"),
                "attribution": source.get("attribution"),
                "snippet": source.get("snippet"),
                "pub_date": source.get("pubDate") or source.get("pub_date"),
            }
        )
    return result


def chat_history_turn_document(user_id: str, request_payload: WebChatMessageRequest, response: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "created_at": now_iso(),
        "user_id": user_id,
        "conversation_id": response.get("conversationId"),
        "parent_message_id": response.get("parentMessageId"),
        "model": response.get("model"),
        "config_id": response.get("configId"),
        "config_name": response.get("configName"),
        "user": {
            "message": request_payload.message or "",
            "images": image_history_documents(request_payload.images),
        },
        "assistant": {
            "answer": response.get("answer") or "",
            "images": image_history_documents(response.get("images")),
            "sources": source_history_documents(response.get("sources")),
        },
    }


def parse_chat_history_turns(content: str) -> list[dict[str, Any]]:
    turns: list[dict[str, Any]] = []
    for line in (content or "").splitlines():
        if not line.strip():
            continue
        try:
            node = json.loads(line)
        except Exception:
            continue
        user = node.get("user") if isinstance(node.get("user"), dict) else {}
        assistant = node.get("assistant") if isinstance(node.get("assistant"), dict) else {}
        images = [history_image_response(image) for image in user.get("images") or [] if isinstance(image, dict)]
        assistant_images = [
            history_image_response(image)
            for image in assistant.get("images") or []
            if isinstance(image, dict)
        ]
        assistant_sources = [
            history_source_response(source)
            for source in assistant.get("sources") or []
            if isinstance(source, dict)
        ]
        turns.append(
            {
                "createdAt": node.get("created_at"),
                "conversationId": node.get("conversation_id"),
                "parentMessageId": node.get("parent_message_id"),
                "model": node.get("model"),
                "configName": node.get("config_name"),
                "userMessage": user.get("message"),
                "images": images,
                "assistantImages": assistant_images,
                "assistantSources": assistant_sources,
                "assistantAnswer": clean_web_answer(assistant.get("answer") or ""),
            }
        )
    turns.reverse()
    return turns


def history_image_response(image: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": image.get("id"),
        "name": image.get("name"),
        "mediaType": image.get("media_type") or image.get("mediaType"),
        "size": image.get("size"),
        "width": image.get("width"),
        "height": image.get("height"),
        "data": image.get("data"),
        "url": image.get("url"),
        "pageUrl": image.get("page_url") or image.get("pageUrl"),
        "source": image.get("source"),
    }


def history_source_response(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": source.get("title"),
        "url": source.get("url"),
        "attribution": source.get("attribution"),
        "snippet": source.get("snippet"),
        "pubDate": source.get("pub_date") or source.get("pubDate"),
    }


def create_chat_history_file(con: sqlite3.Connection, user_id: str, sequence: int) -> sqlite3.Row:
    ts = now_iso()
    con.execute(
        """
        insert into web_chat_history_files
          (user_id, sequence, object_key, content_url, size_bytes, turn_count, created_at, updated_at)
        values (?, ?, ?, '', 0, 0, ?, ?)
        """,
        (user_id, sequence, chat_history_object_key(user_id, sequence), ts, ts),
    )
    return con.execute(
        "select * from web_chat_history_files where user_id = ? and sequence = ?", (user_id, sequence)
    ).fetchone()


def append_web_chat_history(
    con: sqlite3.Connection,
    user_id: str,
    request_payload: WebChatMessageRequest,
    response: dict[str, Any],
) -> None:
    if not CHAT_HISTORY_ENABLED:
        return
    line = json.dumps(chat_history_turn_document(user_id, request_payload, response), ensure_ascii=False) + "\n"
    line_bytes = len(line.encode("utf-8"))
    max_file_bytes = max(128 * 1024, CHAT_HISTORY_MAX_FILE_BYTES)
    target = con.execute(
        """
        select * from web_chat_history_files
        where user_id = ?
        order by sequence desc
        limit 1
        """,
        (user_id,),
    ).fetchone()
    if target is None or (int(target["size_bytes"] or 0) > 0 and int(target["size_bytes"]) + line_bytes > max_file_bytes):
        sequence = 1 if target is None else int(target["sequence"]) + 1
        target = create_chat_history_file(con, user_id, sequence)

    if github_is_configured(GITHUB_CHAT_HISTORY_REPOSITORY, GITHUB_CHAT_HISTORY_TOKEN):
        stored = github_read_json_file(
            GITHUB_CHAT_HISTORY_REPOSITORY,
            GITHUB_CHAT_HISTORY_BRANCH,
            GITHUB_CHAT_HISTORY_TOKEN,
            target["object_key"],
            "chat history",
        )
        current_content = (stored or {}).get("content") or ""
        sha = (stored or {}).get("sha") or None
    else:
        current_content = github_read_raw_file(target["content_url"], GITHUB_CHAT_HISTORY_TOKEN, "chat history") or ""
        sha = None
    if current_content and len(current_content.encode("utf-8")) + line_bytes > max_file_bytes:
        target = create_chat_history_file(con, user_id, int(target["sequence"]) + 1)
        current_content = ""
        sha = None

    written = github_write_file(
        GITHUB_CHAT_HISTORY_REPOSITORY,
        GITHUB_CHAT_HISTORY_BRANCH,
        GITHUB_CHAT_HISTORY_TOKEN,
        target["object_key"],
        current_content + line,
        f"Append web chat history {user_id}",
        "chat history",
        sha=sha,
    )
    con.execute(
        """
        update web_chat_history_files
        set content_url = ?, size_bytes = ?, turn_count = ?, updated_at = ?
        where id = ?
        """,
        (written["url"], written["size"], int(target["turn_count"] or 0) + 1, now_iso(), target["id"]),
    )


def find_or_create_web_session(user_id: str) -> dict[str, Any]:
    with db() as con:
        row = con.execute(
            """
            select s.user_id, s.conversation_id, s.parent_message_id,
                   c.*
            from web_chat_user_sessions s
            join web_chat_model_configs c on c.id = s.config_id
            where s.user_id = ? and c.enabled = 1
            """,
            (user_id,),
        ).fetchone()
        if row:
            return row_to_dict(row)
        configs = con.execute("select * from web_chat_model_configs where enabled = 1 order by id").fetchall()
        if not configs:
            raise AppError(404, "NOT_FOUND", "No web chat model config is enabled")
        config = configs[abs(hash(user_id)) % len(configs)]
        con.execute(
            """
            insert into web_chat_user_sessions(user_id, config_id, conversation_id, parent_message_id, updated_at)
            values (?, ?, null, ?, ?)
            on conflict(user_id) do update set config_id=excluded.config_id, updated_at=excluded.updated_at
            """,
            (user_id, config["id"], ROOT_PARENT_MESSAGE_ID, now_iso()),
        )
        return row_to_dict(
            con.execute(
                """
                select s.user_id, s.conversation_id, s.parent_message_id, c.*
                from web_chat_user_sessions s join web_chat_model_configs c on c.id = s.config_id
                where s.user_id = ?
                """,
                (user_id,),
            ).fetchone()
        )


def session_response(session: dict[str, Any]) -> dict[str, Any]:
    conversation_id = session.get("conversation_id")
    return {
        "configId": session["id"],
        "configName": session["name"],
        "model": first_non_blank(session.get("model"), DEFAULT_WEB_MODEL),
        "conversationId": conversation_id,
        "hasConversation": bool(conversation_id),
    }


def send_web_chat_turn(
    user_id: str,
    request_payload: WebChatMessageRequest,
    sink: Any,
    sse_emit: bool = False,
) -> dict[str, Any]:
    message = (request_payload.message or "").strip()
    images = request_payload.images or []
    if not message and not images:
        raise AppError(400, "VALIDATION_FAILED", "Message or image is required")
    session = find_or_create_web_session(user_id)
    new_conversation = bool(request_payload.newConversation)
    conversation_id = None if new_conversation else first_non_blank(session.get("conversation_id"))
    parent_message_id = ROOT_PARENT_MESSAGE_ID if new_conversation else first_non_blank(session.get("parent_message_id"), ROOT_PARENT_MESSAGE_ID)
    model = first_non_blank(request_payload.model, session.get("model"), DEFAULT_WEB_MODEL)
    conduit_token = session.get("conduit_token")
    if session.get("call_prepare"):
        conduit_token = prepare_web_turn(session, message, model, conversation_id, parent_message_id)
    if not conduit_token:
        raise AppError(503, "VALIDATION_FAILED", "Web chat config requires conduit_token or call_prepare=true")
    uploaded_images = upload_web_images(session, images)
    events: list[str] = []

    def emit(kind: str, data: dict[str, Any]) -> None:
        if sse_emit:
            events.append(sse_event(kind, data))
        if sink:
            sink(kind, data)

    result = send_web_conversation(session, message, model, conversation_id, parent_message_id, conduit_token, uploaded_images, emit)
    next_conversation_id = first_non_blank(result.get("conversationId"), conversation_id)
    next_parent_id = first_non_blank(result.get("parentMessageId"), parent_message_id)
    response = {
        "answer": result.get("answer") or "",
        "images": result.get("images") or [],
        "sources": result.get("sources") or [],
        "conversationId": next_conversation_id,
        "parentMessageId": next_parent_id,
        "model": model,
        "configId": session["id"],
        "configName": session["name"],
    }
    with db() as con:
        con.execute(
            """
            update web_chat_user_sessions
            set conversation_id = ?, parent_message_id = ?, updated_at = ?
            where user_id = ?
            """,
            (next_conversation_id, next_parent_id, now_iso(), user_id),
        )
        append_web_chat_history(con, user_id, request_payload, response)
    if sse_emit:
        response["_events"] = events
    return response


def stream_web_chat_turn(user_id: str, request_payload: WebChatMessageRequest) -> Iterable[str | dict[str, Any]]:
    message = (request_payload.message or "").strip()
    images = request_payload.images or []
    if not message and not images:
        raise AppError(400, "VALIDATION_FAILED", "Message or image is required")
    session = find_or_create_web_session(user_id)
    new_conversation = bool(request_payload.newConversation)
    conversation_id = None if new_conversation else first_non_blank(session.get("conversation_id"))
    parent_message_id = ROOT_PARENT_MESSAGE_ID if new_conversation else first_non_blank(session.get("parent_message_id"), ROOT_PARENT_MESSAGE_ID)
    model = first_non_blank(request_payload.model, session.get("model"), DEFAULT_WEB_MODEL)
    conduit_token = session.get("conduit_token")
    if session.get("call_prepare"):
        conduit_token = prepare_web_turn(session, message, model, conversation_id, parent_message_id)
    if not conduit_token:
        raise AppError(503, "VALIDATION_FAILED", "Web chat config requires conduit_token or call_prepare=true")
    uploaded_images = upload_web_images(session, images)

    path = "/backend-api/f/conversation"
    update_last_used_model_config(session, model, conversation_id)
    body = conversation_payload(message, model, conversation_id, parent_message_id, uploaded_images)
    headers = web_headers(session, path, conversation_id, "text/event-stream", conduit_token)
    url = trim_slash(session.get("base_url") or "https://chatgpt.com") + path
    answer = ""
    response_images: list[dict[str, Any]] = []
    web_image_candidates: list[dict[str, str]] = []
    web_sources: list[dict[str, Any]] = []
    image_placeholder_total = 0
    result_conversation_id = conversation_id
    assistant_id = None
    handoff_topic_id = None
    stream_handoff = False
    handoff_completed = False
    with httpx.Client(timeout=180) as client:
        with client.stream("POST", url, json=body, headers=headers) as response:
            if response.status_code < 200 or response.status_code >= 300:
                upstream_body = response.read().decode("utf-8", "replace")
                raise AppError(502, "INTERNAL_ERROR", truncate(upstream_body or f"Web chat upstream HTTP {response.status_code}", 1000))
            for line in response.iter_lines():
                event = parse_sse_data_line(line)
                if event is None:
                    continue
                if event == "[DONE]":
                    break
                for image in collect_generated_images(event, session):
                    if append_unique_image(response_images, image):
                        yield sse_event("image", image)
                new_candidates = collect_web_image_candidates(event)
                web_image_candidates.extend(new_candidates)
                for candidate in new_candidates:
                    image = direct_web_image_from_candidate(candidate)
                    if image and append_unique_image(response_images, image):
                        yield sse_event("image", image)
                for source in collect_web_sources(event):
                    if append_unique_source(web_sources, source):
                        yield sse_event("source", source)
                next_answer = apply_event(answer, event)
                if next_answer is not None and next_answer != answer:
                    next_placeholder_total = web_image_placeholder_count(next_answer)
                    if next_placeholder_total > image_placeholder_total:
                        image_placeholder_total = next_placeholder_total
                        yield sse_event("image_placeholder", {"count": image_placeholder_total})
                    if next_answer.startswith(answer):
                        delta = next_answer[len(answer) :]
                        if delta:
                            yield sse_event("delta", {"delta": delta})
                    else:
                        yield sse_event("replace", {"text": next_answer})
                    answer = next_answer
                result_conversation_id = first_non_blank(get_text(event, "conversation_id"), result_conversation_id)
                assistant_id = first_non_blank(extract_assistant_message_id(event), assistant_id)
                if get_text(event, "type") == "stream_handoff":
                    stream_handoff = True
                handoff_topic_id = first_non_blank(extract_topic_id(event), handoff_topic_id)
                if stream_handoff and handoff_topic_id:
                    for handoff in read_handoff_topic_stream(session, handoff_topic_id, result_conversation_id, answer):
                        for image in handoff.get("images") or []:
                            if append_unique_image(response_images, image):
                                yield sse_event("image", image)
                        new_candidates = handoff.get("webImageCandidates") or []
                        web_image_candidates.extend(new_candidates)
                        for candidate in new_candidates:
                            image = direct_web_image_from_candidate(candidate)
                            if image and append_unique_image(response_images, image):
                                yield sse_event("image", image)
                        for source in handoff.get("webSources") or []:
                            if append_unique_source(web_sources, source):
                                yield sse_event("source", source)
                        if handoff["type"] == "delta":
                            next_placeholder_total = web_image_placeholder_count(handoff["answer"])
                            if next_placeholder_total > image_placeholder_total:
                                image_placeholder_total = next_placeholder_total
                                yield sse_event("image_placeholder", {"count": image_placeholder_total})
                            answer = handoff["answer"]
                            assistant_id = handoff.get("assistantMessageId") or assistant_id
                            yield sse_event("delta", {"delta": handoff["delta"]})
                        elif handoff["type"] == "replace":
                            next_placeholder_total = web_image_placeholder_count(handoff["answer"])
                            if next_placeholder_total > image_placeholder_total:
                                image_placeholder_total = next_placeholder_total
                                yield sse_event("image_placeholder", {"count": image_placeholder_total})
                            answer = handoff["answer"]
                            assistant_id = handoff.get("assistantMessageId") or assistant_id
                            yield sse_event("replace", {"text": answer})
                        elif handoff["type"] == "done":
                            answer = handoff["answer"]
                            assistant_id = handoff.get("assistantMessageId") or assistant_id
                    handoff_completed = True
                    break
                if is_done_event(event):
                    break
    if stream_handoff and handoff_topic_id and not handoff_completed:
        for handoff in read_handoff_topic_stream(session, handoff_topic_id, result_conversation_id, answer):
            for image in handoff.get("images") or []:
                if append_unique_image(response_images, image):
                    yield sse_event("image", image)
            new_candidates = handoff.get("webImageCandidates") or []
            web_image_candidates.extend(new_candidates)
            for candidate in new_candidates:
                image = direct_web_image_from_candidate(candidate)
                if image and append_unique_image(response_images, image):
                    yield sse_event("image", image)
            for source in handoff.get("webSources") or []:
                if append_unique_source(web_sources, source):
                    yield sse_event("source", source)
            if handoff["type"] == "delta":
                next_placeholder_total = web_image_placeholder_count(handoff["answer"])
                if next_placeholder_total > image_placeholder_total:
                    image_placeholder_total = next_placeholder_total
                    yield sse_event("image_placeholder", {"count": image_placeholder_total})
                answer = handoff["answer"]
                assistant_id = handoff.get("assistantMessageId") or assistant_id
                yield sse_event("delta", {"delta": handoff["delta"]})
            elif handoff["type"] == "replace":
                next_placeholder_total = web_image_placeholder_count(handoff["answer"])
                if next_placeholder_total > image_placeholder_total:
                    image_placeholder_total = next_placeholder_total
                    yield sse_event("image_placeholder", {"count": image_placeholder_total})
                answer = handoff["answer"]
                assistant_id = handoff.get("assistantMessageId") or assistant_id
                yield sse_event("replace", {"text": answer})
            elif handoff["type"] == "done":
                answer = handoff["answer"]
                assistant_id = handoff.get("assistantMessageId") or assistant_id
    cleaned_answer = clean_web_answer(answer)
    if cleaned_answer != answer:
        answer = cleaned_answer
        yield sse_event("replace", {"text": answer})
    for image in resolve_web_images(answer, web_image_candidates):
        if append_unique_image(response_images, image):
            yield sse_event("image", image)
    next_conversation_id = first_non_blank(result_conversation_id, conversation_id)
    next_parent_id = first_non_blank(assistant_id, parent_message_id)
    result_payload = {
        "answer": answer,
        "images": response_images,
        "sources": web_sources,
        "conversationId": next_conversation_id,
        "parentMessageId": next_parent_id,
        "model": model,
        "configId": session["id"],
        "configName": session["name"],
    }
    with db() as con:
        con.execute(
            """
            update web_chat_user_sessions
            set conversation_id = ?, parent_message_id = ?, updated_at = ?
            where user_id = ?
            """,
            (next_conversation_id, next_parent_id, now_iso(), user_id),
        )
        append_web_chat_history(con, user_id, request_payload, result_payload)
    yield result_payload


def sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def web_chat_image_token(config_id: int, file_id: str, ttl_seconds: int = 3600) -> str:
    payload = {"configId": int(config_id), "fileId": file_id, "exp": int(time.time()) + ttl_seconds}
    encoded = b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signature = b64url(hmac.new(JWT_SECRET.encode(), encoded.encode(), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def verify_web_chat_image_token(config_id: int, file_id: str, token: str) -> None:
    if not re.fullmatch(r"file_[A-Za-z0-9]+", file_id or ""):
        raise AppError(400, "VALIDATION_FAILED", "Invalid image id")
    try:
        encoded, signature = token.split(".", 1)
        expected = b64url(hmac.new(JWT_SECRET.encode(), encoded.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature):
            raise ValueError("bad signature")
        payload = json.loads(b64url_decode(encoded).decode("utf-8"))
        if int(payload.get("configId", -1)) != int(config_id) or payload.get("fileId") != file_id:
            raise ValueError("mismatch")
        if int(payload.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired")
    except Exception as exc:
        raise AppError(401, "UNAUTHORIZED", "Invalid image token") from exc


def generated_web_image_url(config: dict[str, Any], file_id: str) -> str:
    config_id = int(config["id"])
    token = web_chat_image_token(config_id, file_id)
    return f"/api/web-chat/images/{config_id}/{quote(file_id, safe='')}?token={quote(token, safe='')}"


def download_generated_web_image(config: dict[str, Any], file_id: str) -> tuple[bytes, str]:
    if not re.fullmatch(r"file_[A-Za-z0-9]+", file_id or ""):
        raise AppError(400, "VALIDATION_FAILED", "Invalid image id")
    base = trim_slash(config.get("base_url") or "https://chatgpt.com")
    metadata_path = f"/backend-api/files/{file_id}/download"
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        metadata_response = client.get(base + metadata_path, headers=web_headers(config, metadata_path, None, "*/*"))
        if metadata_response.status_code < 200 or metadata_response.status_code >= 300:
            raise AppError(
                502,
                "INTERNAL_ERROR",
                truncate(metadata_response.text or f"Image metadata HTTP {metadata_response.status_code}", 1000),
            )
        metadata = metadata_response.json()
        download_url = metadata.get("download_url") if isinstance(metadata, dict) else None
        if not isinstance(download_url, str) or not download_url:
            raise AppError(502, "INTERNAL_ERROR", "Generated image download URL missing")
        parsed = urlparse(download_url)
        content_path = parsed.path or "/backend-api/estuary/content"
        content_url = urljoin(base + "/", download_url)
        image_response = client.get(content_url, headers=web_headers(config, content_path, None, "*/*"))
        if image_response.status_code < 200 or image_response.status_code >= 300:
            raise AppError(
                502,
                "INTERNAL_ERROR",
                truncate(image_response.text or f"Image download HTTP {image_response.status_code}", 1000),
            )
    media_type = image_response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not media_type.startswith("image/"):
        if image_response.content.startswith(b"\x89PNG\r\n\x1a\n"):
            media_type = "image/png"
        else:
            media_type = metadata.get("mime_type") or "application/octet-stream"
    return image_response.content, media_type


def append_unique_image(images: list[dict[str, Any]], image: dict[str, Any]) -> bool:
    key = image.get("id") or image.get("url") or image.get("pageUrl")
    if not key:
        return False
    for existing in images:
        if key in {existing.get("id"), existing.get("url"), existing.get("pageUrl")}:
            return False
    images.append(image)
    return True


def append_unique_source(sources: list[dict[str, Any]], source: dict[str, Any]) -> bool:
    url = source.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return False
    if any(existing.get("url") == url for existing in sources):
        return False
    sources.append(source)
    return True


def collect_web_sources(node: Any) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []

    def add(value: Any) -> None:
        if not isinstance(value, dict):
            return
        url = value.get("url")
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return
        source = {
            "title": str(value.get("title") or value.get("attribution") or url),
            "url": url,
            "attribution": value.get("attribution") or urlparse(url).netloc,
            "snippet": value.get("snippet") or "",
            "pubDate": value.get("pub_date") or value.get("pubDate"),
        }
        append_unique_source(sources, source)

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        if value.get("type") == "search_result":
            add(value)
        for key in ("items", "sources", "supporting_websites", "entries"):
            if isinstance(value.get(key), list):
                for item in value[key]:
                    if isinstance(item, dict):
                        add(item)
                        walk(item)
        for child in value.values():
            walk(child)

    walk(node)
    return sources


def collect_generated_images(node: Any, config: dict[str, Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        asset_pointer = value.get("asset_pointer")
        if value.get("content_type") == "image_asset_pointer" and isinstance(asset_pointer, str):
            file_id = asset_pointer.removeprefix("sediment://")
            if re.fullmatch(r"file_[A-Za-z0-9]+", file_id or ""):
                metadata = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
                generation = metadata.get("generation") if isinstance(metadata.get("generation"), dict) else {}
                image = {
                    "id": file_id,
                    "fileId": file_id,
                    "name": f"{file_id}.png",
                    "mediaType": "image/png",
                    "size": value.get("size_bytes"),
                    "width": value.get("width"),
                    "height": value.get("height"),
                    "url": generated_web_image_url(config, file_id),
                    "source": "generated",
                }
                if generation.get("gen_id"):
                    image["generationId"] = generation["gen_id"]
                append_unique_image(found, image)
        for child in value.values():
            walk(child)

    walk(node)
    return found


def collect_web_image_candidates(node: Any) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []

    def add(url: Any, title: Any = None) -> None:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return
        if any(item["url"] == url for item in candidates):
            return
        lowered = url.lower()
        title_text = str(title or "")
        if is_probable_web_image_url(lowered) or any(marker in title_text.lower() for marker in ["image", "photo", "picture"]):
            candidates.append({"url": url, "title": title_text})

    def add_urls_from_text(text: Any, title: Any = None) -> None:
        if not isinstance(text, str):
            return
        for url in urls_from_text(text):
            add(url, title)

    def walk(value: Any) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return
        if value.get("type") == "search_result":
            add(value.get("url"), value.get("title"))
        if isinstance(value.get("image_result"), dict):
            image = value["image_result"]
            title = image.get("title")
            for key in ["content_url", "thumbnail_url", "original_content_url", "url"]:
                add(image.get(key), title)
        title = value.get("title") or value.get("alt")
        for key in ["content_url", "thumbnail_url", "original_content_url", "image_url", "url"]:
            add(value.get(key), title)
        safe_urls = value.get("safe_urls")
        if isinstance(safe_urls, list):
            for url in safe_urls:
                add(url, title)
        add_urls_from_text(value.get("alt"), title)
        add_urls_from_text(value.get("matched_text"), title)
        for child in value.values():
            walk(child)

    walk(node)
    return candidates


def is_probable_web_image_url(value: str) -> bool:
    parsed = urlparse(value)
    path = parsed.path.lower()
    host = parsed.netloc.lower()
    return (
        path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
        or "images.openai.com" in host
        or "image" in path
        or "images" in path
        or "photo" in path
        or "photos" in path
        or "asset" in path
        or "hubble" in path
    )


def urls_from_text(text: str) -> list[str]:
    urls = re.findall(r"https?://[^\s)\]\"<>]+", text or "")
    result: list[str] = []
    for url in urls:
        url = html_lib.unescape(url.rstrip(".,;:"))
        if url not in result:
            result.append(url)
    return result


def clean_web_answer(answer: str) -> str:
    cleaned = re.sub(r"image_group.*?", "", answer or "", flags=re.S)
    cleaned = re.sub(r"(?:cite|i)[^]*", "", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def web_image_placeholder_count(answer: str, limit: int = 8) -> int:
    count = 0
    for match in re.finditer(r"image_group(.*?)(?:|$)", answer or "", flags=re.S):
        payload = match.group(1) or ""
        refs = re.search(r'"image_refs"\s*:\s*\[(.*?)\]', payload, flags=re.S)
        if refs:
            count += len(re.findall(r'"[^"]+"', refs.group(1))) or 1
        else:
            count += 1
    if not count and "image" in (answer or ""):
        count = 1
    return min(count, limit)


def direct_web_image_from_candidate(candidate: dict[str, str]) -> dict[str, Any] | None:
    url = html_lib.unescape(candidate.get("url") or "")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    is_direct = (
        path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))
        or host == "images.openai.com"
        or host.endswith(".images.openai.com")
        or "purpose=fullsize" in query
    )
    if not is_direct:
        return None
    media_type = ""
    if path.endswith(".png"):
        media_type = "image/png"
    elif path.endswith((".jpg", ".jpeg")):
        media_type = "image/jpeg"
    elif path.endswith(".webp"):
        media_type = "image/webp"
    elif path.endswith(".gif"):
        media_type = "image/gif"
    return {
        "id": sha256_urlsafe(url.encode("utf-8"))[:16],
        "name": candidate.get("title") or Path(parsed.path).name or "web image",
        "mediaType": media_type,
        "url": url,
        "pageUrl": url,
        "source": "web",
    }


def resolve_web_images(answer: str, candidates: list[dict[str, str]], limit: int = 8) -> list[dict[str, Any]]:
    merged: list[dict[str, str]] = [{"url": url, "title": ""} for url in urls_from_text(answer)]
    for candidate in candidates:
        if not any(item["url"] == candidate["url"] for item in merged):
            merged.append(candidate)

    images: list[dict[str, Any]] = []
    ordered = sorted(enumerate(merged), key=lambda item: (-web_image_candidate_score(item[1]["url"]), item[0]))
    for _, candidate in ordered[:48]:
        resolved = resolve_web_image(candidate["url"], candidate.get("title") or "")
        if resolved and append_unique_image(images, resolved) and len(images) >= limit:
            break
    return images


def web_image_candidate_score(url: str) -> int:
    parsed = urlparse(html_lib.unescape(url or ""))
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    if path.endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return 5
    if host == "images.openai.com" or host.endswith(".images.openai.com"):
        return 4
    if "purpose=fullsize" in query:
        return 4
    if "thumbnail" in path or "purpose=inline" in query:
        return 3
    if any(marker in path for marker in ["/image", "/images", "/photo", "/photos", "/asset"]):
        return 2
    return 1


def resolve_web_image(url: str, title: str = "") -> dict[str, Any] | None:
    url = html_lib.unescape(url)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    try:
        with httpx.Client(timeout=8, follow_redirects=True) as client:
            response = client.get(url, headers={"accept": "image/*,text/html;q=0.9,*/*;q=0.8"})
    except Exception:
        return None
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    final_url = str(response.url)
    if response.status_code >= 200 and response.status_code < 300 and content_type.startswith("image/"):
        return {
            "id": sha256_urlsafe(final_url.encode("utf-8"))[:16],
            "name": title or Path(urlparse(final_url).path).name or "web image",
            "mediaType": content_type,
            "url": final_url,
            "pageUrl": final_url,
            "source": "web",
        }
    if response.status_code < 200 or response.status_code >= 300 or "html" not in content_type:
        return None
    html = response.text[:262144]
    image_url = first_non_blank(
        html_meta_content(html, "og:image"),
        html_meta_content(html, "twitter:image"),
        html_link_href(html, "image_src"),
    )
    if not image_url:
        return None
    image_url = html_lib.unescape(urljoin(final_url, image_url))
    return {
        "id": sha256_urlsafe((final_url + "\n" + image_url).encode("utf-8"))[:16],
        "name": title or html_title(html) or Path(urlparse(image_url).path).name or "web image",
        "mediaType": "",
        "url": image_url,
        "pageUrl": final_url,
        "source": "web",
    }


def html_meta_content(html: str, property_name: str) -> str | None:
    pattern = rf'<meta\s+[^>]*(?:property|name)=["\']{re.escape(property_name)}["\'][^>]*content=["\']([^"\']+)["\']'
    match = re.search(pattern, html, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    pattern = rf'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*(?:property|name)=["\']{re.escape(property_name)}["\']'
    match = re.search(pattern, html, re.IGNORECASE)
    return match.group(1).strip() if match else None


def html_link_href(html: str, rel_name: str) -> str | None:
    pattern = rf'<link\s+[^>]*rel=["\'][^"\']*{re.escape(rel_name)}[^"\']*["\'][^>]*href=["\']([^"\']+)["\']'
    match = re.search(pattern, html, re.IGNORECASE)
    return match.group(1).strip() if match else None


def html_title(html: str) -> str | None:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip()


def web_headers(config: dict[str, Any], path: str, conversation_id: str | None, accept: str, conduit: str | None = None) -> dict[str, str]:
    base = trim_slash(config.get("base_url") or "https://chatgpt.com")
    referer = f"{base}/c/{conversation_id}" if conversation_id else f"{base}/"
    headers = {
        "accept": accept,
        "content-type": "application/json",
        "origin": base,
        "referer": referer,
        "user-agent": first_non_blank(config.get("user_agent"), DEFAULT_USER_AGENT),
        "oai-language": "zh-CN",
        "oai-client-build-number": first_non_blank(config.get("oai_client_build_number"), DEFAULT_OAI_CLIENT_BUILD_NUMBER),
        "oai-client-version": first_non_blank(config.get("oai_client_version"), DEFAULT_OAI_CLIENT_VERSION),
        "x-openai-target-path": path,
        "x-openai-target-route": path,
    }
    auth = first_non_blank(config.get("auth_header"))
    if not auth and config.get("bearer_token"):
        token = str(config["bearer_token"]).strip()
        auth = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    if auth:
        headers["authorization"] = auth
    for name, key in [
        ("ChatGPT-Account-ID", "account_id"),
        ("cookie", "cookie"),
        ("oai-device-id", "oai_device_id"),
        ("oai-session-id", "oai_session_id"),
        ("openai-sentinel-chat-requirements-token", "sentinel_token"),
        ("x-oai-is", "oai_is"),
    ]:
        value = config.get(key)
        if value and not str(value).startswith("PASTE_"):
            headers[name] = str(value)
    if conduit:
        headers["x-conduit-token"] = conduit
    headers["x-oai-turn-trace-id"] = str(uuid.uuid4())
    return headers


def prepare_web_turn(config: dict[str, Any], message: str, model: str, conversation_id: str | None, parent_id: str) -> str:
    payload: dict[str, Any] = {
        "action": "next",
        "fork_from_shared_post": False,
        "parent_message_id": parent_id,
        "model": model,
        "timezone_offset_min": -480,
        "timezone": "Asia/Shanghai",
        "conversation_mode": {"kind": "primary_assistant"},
        "system_hints": [],
        "supports_buffering": True,
        "supported_encodings": ["v1"],
        "client_contextual_info": {"app_name": "chatgpt.com"},
    }
    if conversation_id:
        payload["conversation_id"] = conversation_id
    else:
        payload["partial_query"] = {
            "id": str(uuid.uuid4()),
            "author": {"role": "user"},
            "content": {"content_type": "text", "parts": [message]},
        }
    data = send_web_json(config, "/backend-api/f/conversation/prepare", payload, conversation_id, "*/*")
    token = data.get("conduit_token") if isinstance(data, dict) else None
    if not token:
        raise AppError(502, "INTERNAL_ERROR", "Web chat prepare did not return conduit_token")
    return str(token)


def send_web_json(config: dict[str, Any], path: str, payload: dict[str, Any], conversation_id: str | None, accept: str) -> Any:
    url = trim_slash(config.get("base_url") or "https://chatgpt.com") + path
    with httpx.Client(timeout=120) as client:
        response = client.post(url, json=payload, headers=web_headers(config, path, conversation_id, accept))
    if response.status_code < 200 or response.status_code >= 300:
        raise AppError(502, "INTERNAL_ERROR", truncate(response.text or f"Web chat upstream HTTP {response.status_code}", 1000))
    try:
        return response.json()
    except Exception as exc:
        raise AppError(502, "INTERNAL_ERROR", "Unexpected web chat JSON response") from exc


def upload_web_images(config: dict[str, Any], images: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [upload_web_image(config, image) for image in images]


def upload_web_image(config: dict[str, Any], image: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_web_image(image)
    create_payload = {
        "file_name": normalized["name"],
        "file_size": normalized["size"],
        "use_case": "multimodal",
        "timezone_offset_min": -480,
        "reset_rate_limits": False,
        "store_in_library": True,
    }
    created = send_web_json(config, "/backend-api/files", create_payload, None, "application/json")
    file_id = created.get("file_id") if isinstance(created, dict) else None
    upload_url = created.get("upload_url") if isinstance(created, dict) else None
    if not isinstance(file_id, str) or not isinstance(upload_url, str):
        raise AppError(502, "INTERNAL_ERROR", "Unexpected image upload create response")
    upload_raw_web_image(config, upload_url, normalized["bytes"], normalized["mediaType"])
    library_file_id = process_uploaded_web_file(config, file_id, normalized["name"])
    return {
        "fileId": file_id,
        "libraryFileId": library_file_id,
        "name": normalized["name"],
        "mediaType": normalized["mediaType"],
        "size": normalized["size"],
        "width": normalized["width"],
        "height": normalized["height"],
    }


def normalize_web_image(image: dict[str, Any]) -> dict[str, Any]:
    media_type = str(image.get("mediaType") or image.get("media_type") or "").strip().lower()
    if media_type == "image/jpg":
        media_type = "image/jpeg"
    if media_type not in SUPPORTED_IMAGE_MEDIA_TYPES:
        raise AppError(400, "VALIDATION_FAILED", f"Unsupported image media type: {media_type or '<empty>'}")
    encoded = str(image.get("data") or "")
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(re.sub(r"\s+", "", encoded), validate=True)
    except Exception as exc:
        raise AppError(400, "VALIDATION_FAILED", "Image data must be valid base64") from exc
    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        raise AppError(400, "VALIDATION_FAILED", "Image size must be between 1 byte and 10 MB")
    width = int(image.get("width") or 0)
    height = int(image.get("height") or 0)
    if width <= 0 or height <= 0:
        raise AppError(400, "VALIDATION_FAILED", "Image width and height are required")
    name = first_non_blank(image.get("name"), f"{uuid.uuid4()}{image_extension(media_type)}")
    return {
        "bytes": image_bytes,
        "mediaType": media_type,
        "name": name,
        "size": len(image_bytes),
        "width": width,
        "height": height,
    }


def upload_raw_web_image(config: dict[str, Any], upload_url: str, image_bytes: bytes, media_type: str) -> None:
    base = trim_slash(config.get("base_url") or "https://chatgpt.com")
    headers = {
        "content-type": media_type,
        "origin": base,
        "referer": base + "/",
        "x-ms-blob-type": "BlockBlob",
        "user-agent": first_non_blank(config.get("user_agent"), DEFAULT_USER_AGENT),
    }
    with httpx.Client(timeout=120) as client:
        response = client.put(upload_url, content=image_bytes, headers=headers)
    if response.status_code not in {200, 201}:
        raise AppError(502, "INTERNAL_ERROR", truncate(response.text or f"Image upload HTTP {response.status_code}", 1000))


def process_uploaded_web_file(config: dict[str, Any], file_id: str, file_name: str) -> str | None:
    path = "/backend-api/files/process_upload_stream"
    payload = {
        "file_id": file_id,
        "use_case": "multimodal",
        "index_for_retrieval": False,
        "file_name": file_name,
        "metadata": {"store_in_library": True},
    }
    url = trim_slash(config.get("base_url") or "https://chatgpt.com") + path
    headers = web_headers(config, path, None, "text/event-stream")
    library_file_id = None
    with httpx.Client(timeout=120) as client:
        with client.stream("POST", url, json=payload, headers=headers) as response:
            if response.status_code < 200 or response.status_code >= 300:
                body = response.read().decode("utf-8", "replace")
                raise AppError(502, "INTERNAL_ERROR", truncate(body or f"Image processing HTTP {response.status_code}", 1000))
            for line in response.iter_lines():
                event = parse_sse_data_line(line)
                if not isinstance(event, dict):
                    continue
                extra = event.get("extra")
                if isinstance(extra, dict) and isinstance(extra.get("metadata_object_id"), str):
                    library_file_id = extra["metadata_object_id"]
                if event.get("event") == "file.processing.failed":
                    raise AppError(502, "INTERNAL_ERROR", event.get("message") or "Failed processing uploaded image")
    return library_file_id


def image_extension(media_type: str) -> str:
    return {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(media_type, ".img")


def send_web_conversation(
    config: dict[str, Any],
    message: str,
    model: str,
    conversation_id: str | None,
    parent_id: str,
    conduit_token: str,
    images: list[dict[str, Any]],
    emit: Any,
) -> dict[str, Any]:
    path = "/backend-api/f/conversation"
    update_last_used_model_config(config, model, conversation_id)
    payload = conversation_payload(message, model, conversation_id, parent_id, images)
    headers = web_headers(config, path, conversation_id, "text/event-stream", conduit_token)
    url = trim_slash(config.get("base_url") or "https://chatgpt.com") + path
    answer = ""
    response_images: list[dict[str, Any]] = []
    web_image_candidates: list[dict[str, str]] = []
    web_sources: list[dict[str, Any]] = []
    image_placeholder_total = 0
    result_conversation_id = conversation_id
    assistant_id = None
    handoff_topic_id = None
    stream_handoff = False
    handoff_completed = False
    with httpx.Client(timeout=180) as client:
        with client.stream("POST", url, json=payload, headers=headers) as response:
            if response.status_code < 200 or response.status_code >= 300:
                body = response.read().decode("utf-8", "replace")
                raise AppError(502, "INTERNAL_ERROR", truncate(body or f"Web chat upstream HTTP {response.status_code}", 1000))
            for line in response.iter_lines():
                event = parse_sse_data_line(line)
                if event is None:
                    continue
                if event == "[DONE]":
                    break
                for image in collect_generated_images(event, config):
                    if append_unique_image(response_images, image):
                        emit("image", image)
                new_candidates = collect_web_image_candidates(event)
                web_image_candidates.extend(new_candidates)
                for candidate in new_candidates:
                    image = direct_web_image_from_candidate(candidate)
                    if image and append_unique_image(response_images, image):
                        emit("image", image)
                for source in collect_web_sources(event):
                    if append_unique_source(web_sources, source):
                        emit("source", source)
                next_answer = apply_event(answer, event)
                if next_answer is not None and next_answer != answer:
                    next_placeholder_total = web_image_placeholder_count(next_answer)
                    if next_placeholder_total > image_placeholder_total:
                        image_placeholder_total = next_placeholder_total
                        emit("image_placeholder", {"count": image_placeholder_total})
                    if next_answer.startswith(answer):
                        delta = next_answer[len(answer) :]
                        if delta:
                            emit("delta", {"delta": delta})
                    else:
                        emit("replace", {"text": next_answer})
                    answer = next_answer
                result_conversation_id = first_non_blank(get_text(event, "conversation_id"), result_conversation_id)
                assistant_id = first_non_blank(extract_assistant_message_id(event), assistant_id)
                if get_text(event, "type") == "stream_handoff":
                    stream_handoff = True
                handoff_topic_id = first_non_blank(extract_topic_id(event), handoff_topic_id)
                if stream_handoff and handoff_topic_id:
                    for handoff in read_handoff_topic_stream(config, handoff_topic_id, result_conversation_id, answer):
                        for image in handoff.get("images") or []:
                            if append_unique_image(response_images, image):
                                emit("image", image)
                        new_candidates = handoff.get("webImageCandidates") or []
                        web_image_candidates.extend(new_candidates)
                        for candidate in new_candidates:
                            image = direct_web_image_from_candidate(candidate)
                            if image and append_unique_image(response_images, image):
                                emit("image", image)
                        for source in handoff.get("webSources") or []:
                            if append_unique_source(web_sources, source):
                                emit("source", source)
                        if handoff["type"] in {"delta", "replace"}:
                            next_answer = handoff["answer"]
                            next_placeholder_total = web_image_placeholder_count(next_answer)
                            if next_placeholder_total > image_placeholder_total:
                                image_placeholder_total = next_placeholder_total
                                emit("image_placeholder", {"count": image_placeholder_total})
                            if handoff["type"] == "delta":
                                emit("delta", {"delta": handoff["delta"]})
                            else:
                                emit("replace", {"text": next_answer})
                            answer = next_answer
                            assistant_id = handoff.get("assistantMessageId") or assistant_id
                        elif handoff["type"] == "done":
                            answer = handoff["answer"]
                            assistant_id = handoff.get("assistantMessageId") or assistant_id
                    handoff_completed = True
                    break
                if is_done_event(event):
                    break
    if stream_handoff and handoff_topic_id and not handoff_completed:
        for handoff in read_handoff_topic_stream(config, handoff_topic_id, result_conversation_id, answer):
            for image in handoff.get("images") or []:
                if append_unique_image(response_images, image):
                    emit("image", image)
            new_candidates = handoff.get("webImageCandidates") or []
            web_image_candidates.extend(new_candidates)
            for candidate in new_candidates:
                image = direct_web_image_from_candidate(candidate)
                if image and append_unique_image(response_images, image):
                    emit("image", image)
            for source in handoff.get("webSources") or []:
                if append_unique_source(web_sources, source):
                    emit("source", source)
            if handoff["type"] in {"delta", "replace"}:
                next_answer = handoff["answer"]
                next_placeholder_total = web_image_placeholder_count(next_answer)
                if next_placeholder_total > image_placeholder_total:
                    image_placeholder_total = next_placeholder_total
                    emit("image_placeholder", {"count": image_placeholder_total})
                if handoff["type"] == "delta":
                    emit("delta", {"delta": handoff["delta"]})
                else:
                    emit("replace", {"text": next_answer})
                answer = next_answer
                assistant_id = handoff.get("assistantMessageId") or assistant_id
            elif handoff["type"] == "done":
                answer = handoff["answer"]
                assistant_id = handoff.get("assistantMessageId") or assistant_id
    cleaned_answer = clean_web_answer(answer)
    if cleaned_answer != answer:
        answer = cleaned_answer
        emit("replace", {"text": answer})
    for image in resolve_web_images(answer, web_image_candidates):
        if append_unique_image(response_images, image):
            emit("image", image)
    return {
        "answer": answer,
        "images": response_images,
        "sources": web_sources,
        "conversationId": result_conversation_id,
        "parentMessageId": assistant_id,
    }


def conversation_payload(message: str, model: str, conversation_id: str | None, parent_id: str, images: list[dict[str, Any]]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "developer_mode_connector_ids": [],
        "selected_connector_ids": [],
        "selected_sync_knowledge_store_ids": [],
        "selected_sources": [],
        "selected_github_repos": [],
        "selected_all_github_repos": False,
        "serialization_metadata": {"custom_symbol_offsets": []},
    }
    content: dict[str, Any]
    if images:
        parts: list[Any] = []
        attachments: list[dict[str, Any]] = []
        for image in images:
            file_id = image.get("fileId") or image.get("file_id")
            parts.append(
                {
                    "content_type": "image_asset_pointer",
                    "asset_pointer": f"sediment://{file_id}",
                    "size_bytes": image.get("size") or 0,
                    "width": image.get("width"),
                    "height": image.get("height"),
                }
            )
            attachment = {
                "id": file_id,
                "size": image.get("size") or 0,
                "name": image.get("name"),
                "mime_type": image.get("mediaType") or image.get("media_type"),
                "width": image.get("width"),
                "height": image.get("height"),
                "source": "local",
                "is_big_paste": False,
            }
            library_file_id = image.get("libraryFileId") or image.get("library_file_id")
            if library_file_id:
                attachment["library_file_id"] = library_file_id
            attachments.append(attachment)
        parts.append(message)
        content = {"content_type": "multimodal_text", "parts": parts}
        metadata["attachments"] = attachments
    else:
        content = {"content_type": "text", "parts": [message]}
    payload: dict[str, Any] = {
        "action": "next",
        "messages": [
            {
                "id": str(uuid.uuid4()),
                "author": {"role": "user"},
                "create_time": time.time(),
                "content": content,
                "metadata": metadata,
            }
        ],
        "parent_message_id": parent_id,
        "model": model,
        "timezone_offset_min": -480,
        "timezone": "Asia/Shanghai",
        "conversation_mode": {"kind": "primary_assistant"},
        "enable_message_followups": True,
        "system_hints": [],
        "supports_buffering": True,
        "supported_encodings": ["v1"],
        "client_contextual_info": {
            "is_dark_mode": False,
            "time_since_loaded": 1,
            "page_height": 703,
            "page_width": 1008,
            "pixel_ratio": 1.25,
            "screen_height": 864,
            "screen_width": 1536,
            "app_name": "chat.sharedchat.cc",
        },
        "paragen_cot_summary_display_override": "allow",
        "force_parallel_switch": "auto",
    }
    if "thinking" in model or model.endswith("-pro"):
        payload["thinking_effort"] = "extended"
    if conversation_id:
        payload["conversation_id"] = conversation_id
    return payload


def update_last_used_model_config(config: dict[str, Any], model: str, conversation_id: str | None) -> None:
    path = "/backend-api/settings/user_last_used_model_config"
    url = trim_slash(config.get("base_url") or "https://chatgpt.com") + path + "?model_slug=" + quote(model)
    try:
        with httpx.Client(timeout=30) as client:
            client.patch(url, content="{}", headers=web_headers(config, path, conversation_id, "application/json"))
    except Exception:
        pass


def fetch_websocket_url(config: dict[str, Any], conversation_id: str | None) -> str:
    path = "/backend-api/celsius/ws/user"
    url = trim_slash(config.get("base_url") or "https://chatgpt.com") + path
    with httpx.Client(timeout=30) as client:
        response = client.get(url, headers=web_headers(config, path, conversation_id, "*/*"))
    if response.status_code < 200 or response.status_code >= 300:
        raise AppError(502, "INTERNAL_ERROR", truncate(response.text or f"WebSocket URL HTTP {response.status_code}", 1000))
    try:
        ws_url = response.json().get("websocket_url")
    except Exception as exc:
        raise AppError(502, "INTERNAL_ERROR", "Unable to parse web chat websocket response") from exc
    if not isinstance(ws_url, str) or not ws_url.startswith(("ws://", "wss://")):
        raise AppError(502, "INTERNAL_ERROR", "websocket_url missing from upstream response")
    return ws_url


def read_handoff_topic_stream(
    config: dict[str, Any],
    topic_id: str,
    conversation_id: str | None,
    initial_answer: str,
) -> Iterable[dict[str, Any]]:
    try:
        from websockets.sync.client import connect
    except Exception as exc:
        raise AppError(502, "INTERNAL_ERROR", "websockets package is required for stream handoff") from exc

    ws_url = fetch_websocket_url(config, conversation_id)
    answer = initial_answer or ""
    assistant_id = None
    subscribe = json.dumps(websocket_subscribe_frame(topic_id), ensure_ascii=False, separators=(",", ":"))
    try:
        with connect(
            ws_url,
            origin=trim_slash(config.get("base_url") or "https://chatgpt.com"),
            additional_headers=websocket_headers(config),
            user_agent_header=first_non_blank(config.get("user_agent"), DEFAULT_USER_AGENT),
            open_timeout=30,
            ping_interval=20,
            ping_timeout=20,
            max_size=None,
        ) as websocket:
            websocket.send(subscribe)
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                try:
                    text = websocket.recv(timeout=max(1, min(30, int(deadline - time.monotonic()))))
                except TimeoutError:
                    continue
                if not text or topic_id not in str(text):
                    continue
                try:
                    message = json.loads(text)
                except Exception:
                    message = text
                result = handle_handoff_message(message, answer, config)
                next_answer = result["answer"]
                assistant_id = result.get("assistantMessageId") or assistant_id
                extras = {
                    "images": result.get("images") or [],
                    "webImageCandidates": result.get("webImageCandidates") or [],
                    "webSources": result.get("webSources") or [],
                }
                if next_answer != answer:
                    if next_answer.startswith(answer):
                        delta = next_answer[len(answer) :]
                        answer = next_answer
                        if delta:
                            yield {
                                "type": "delta",
                                "delta": delta,
                                "answer": answer,
                                "assistantMessageId": assistant_id,
                                **extras,
                            }
                    else:
                        answer = next_answer
                        yield {"type": "replace", "answer": answer, "assistantMessageId": assistant_id, **extras}
                elif extras["images"] or extras["webImageCandidates"] or extras["webSources"]:
                    yield {"type": "image", "answer": answer, "assistantMessageId": assistant_id, **extras}
                if result["done"]:
                    yield {"type": "done", "answer": answer, "assistantMessageId": assistant_id, **extras}
                    return
    except AppError:
        raise
    except Exception as exc:
        raise AppError(502, "INTERNAL_ERROR", f"Unable to read web chat WebSocket response: {exception_summary(exc)}") from exc
    yield {"type": "done", "answer": answer, "assistantMessageId": assistant_id}


def websocket_headers(config: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "oai-client-build-number": first_non_blank(config.get("oai_client_build_number"), DEFAULT_OAI_CLIENT_BUILD_NUMBER),
        "oai-client-version": first_non_blank(config.get("oai_client_version"), DEFAULT_OAI_CLIENT_VERSION),
    }
    auth = first_non_blank(config.get("auth_header"))
    if not auth and config.get("bearer_token"):
        token = str(config["bearer_token"]).strip()
        auth = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    optional = {
        "Authorization": auth,
        "chatgpt-account-id": config.get("account_id"),
        "Cookie": config.get("cookie"),
        "oai-device-id": config.get("oai_device_id"),
        "oai-session-id": config.get("oai_session_id"),
        "openai-sentinel-chat-requirements-token": config.get("sentinel_token"),
        "x-oai-is": config.get("oai_is"),
    }
    for key, value in optional.items():
        if value and not str(value).startswith("PASTE_"):
            headers[key] = str(value)
    return headers


def websocket_subscribe_frame(topic_id: str) -> list[dict[str, Any]]:
    offset = f"{int((time.time() - 30) * 1000)}-0"
    return [
        {"id": 1, "command": {"type": "connect", "presence": {"type": "presence", "state": "background"}}},
        {"id": 2, "command": {"type": "subscribe", "topic_id": "conversations"}},
        {"id": 3, "command": {"type": "subscribe", "topic_id": "app_notifications"}},
        {"id": 4, "command": {"type": "subscribe", "topic_id": topic_id, "offset": offset}},
    ]


def handle_handoff_message(message: Any, answer: str, config: dict[str, Any]) -> dict[str, Any]:
    done = False
    assistant_id = None
    images: list[dict[str, Any]] = []
    web_candidates: list[dict[str, str]] = []
    web_sources: list[dict[str, Any]] = []
    for encoded in extract_encoded_items(message):
        for event in parse_encoded_sse(encoded):
            if event == "[DONE]":
                done = True
                continue
            if not isinstance(event, dict):
                continue
            for image in collect_generated_images(event, config):
                append_unique_image(images, image)
            web_candidates.extend(collect_web_image_candidates(event))
            for source in collect_web_sources(event):
                append_unique_source(web_sources, source)
            assistant_id = extract_assistant_message_id(event) or assistant_id
            next_answer = apply_event(answer, event)
            if next_answer is not None:
                answer = next_answer
            if get_text(event, "type") in DONE_TYPES:
                done = True
    if is_ws_done_message(message):
        done = True
    return {
        "answer": answer,
        "done": done,
        "assistantMessageId": assistant_id,
        "images": images,
        "webImageCandidates": web_candidates,
        "webSources": web_sources,
    }


def extract_encoded_items(message: Any) -> list[str]:
    items: list[str] = []

    def walk(node: Any, key: str | None = None) -> None:
        if key == "encoded_item" and isinstance(node, str):
            items.append(node)
            return
        if key is None and isinstance(node, str) and "data:" in node:
            items.append(node)
            return
        if isinstance(node, list):
            for child in node:
                walk(child)
        elif isinstance(node, dict):
            for child_key, child_value in node.items():
                walk(child_value, child_key)

    walk(message)
    return items


def parse_encoded_sse(encoded_item: str) -> list[Any]:
    events: list[Any] = []
    data_lines: list[str] = []

    def flush() -> None:
        nonlocal data_lines
        if not data_lines:
            return
        data = "\n".join(data_lines)
        if data == "[DONE]":
            events.append("[DONE]")
        else:
            try:
                events.append(json.loads(data))
            except Exception:
                pass
        data_lines = []

    for raw_line in encoded_item.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())
    flush()
    return events


def is_ws_done_message(message: Any) -> bool:
    if not isinstance(message, list):
        return False
    for item in message:
        if not isinstance(item, dict):
            continue
        nested = item.get("payload", {}).get("payload") if isinstance(item.get("payload"), dict) else None
        if isinstance(nested, dict) and nested.get("type") == "done":
            return True
    return False


def extract_topic_id(event: Any) -> str | None:
    if not isinstance(event, dict):
        return None
    direct = get_text(event, "topic_id")
    if direct:
        return direct
    options = event.get("options")
    if isinstance(options, list):
        for option in options:
            if isinstance(option, dict) and option.get("topic_id"):
                return str(option["topic_id"])
    return topic_id_from_resume_token(get_text(event, "resume_token") or get_text(event, "token"))


def topic_id_from_resume_token(token: str | None) -> str | None:
    if not token:
        return None
    parts = token.split(".")
    if len(parts) < 2:
        return None
    try:
        payload = json.loads(b64url_decode(parts[1]))
        return first_non_blank(payload.get("turn_topic_id"), payload.get("topic_id"))
    except Exception:
        return None


def parse_sse_data_line(line: str | bytes | None) -> Any:
    if line is None:
        return None
    if isinstance(line, bytes):
        line = line.decode("utf-8", "replace")
    line = line.strip()
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data:
        return None
    if data == "[DONE]":
        return "[DONE]"
    try:
        return json.loads(data)
    except Exception:
        return None


def get_text(node: Any, key: str) -> str | None:
    if not isinstance(node, dict):
        return None
    value = node.get(key)
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value)
    return text if text else None


def apply_event(answer: str, event: Any) -> str | None:
    if not isinstance(event, dict):
        return answer
    event_type = get_text(event, "type")
    if event_type in TEXT_DELTA_TYPES:
        return answer + (get_text(event, "delta") or "")
    if event_type in TEXT_DONE_TYPES:
        return merge_full_text(answer, get_text(event, "text"))
    if event_type == "response.content_part.done":
        part = event.get("part") if isinstance(event.get("part"), dict) else {}
        return merge_full_text(answer, get_text(part, "text"))
    if event_type in {"response.output_item.done", "response.function_call_arguments.done"}:
        return merge_full_text(answer, extract_output_item_text(event.get("item")))
    if event_type == "response.completed":
        response = event.get("response") if isinstance(event.get("response"), dict) else {}
        return merge_full_text(answer, extract_output_text(response.get("output")))
    full = extract_assistant_message_text(event)
    if full is not None:
        return merge_full_text(answer, full)
    if is_patch_operation(event) and event.get("o") != "patch":
        return apply_patch_operation(answer, event)
    value = event.get("v")
    if isinstance(value, str) and not is_patch_operation(event):
        return answer + value
    if isinstance(value, list):
        updated = answer
        for item in value:
            if is_patch_operation(item):
                updated = apply_patch_operation(updated, item)
        return updated
    return answer


def extract_output_text(output: Any) -> str | None:
    if not isinstance(output, list):
        return None
    parts = [text for item in output if (text := extract_output_item_text(item)) is not None]
    return "".join(parts) if parts else None


def extract_output_item_text(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    if isinstance(item.get("text"), str):
        return item["text"]
    content = item.get("content")
    if not isinstance(content, list):
        return None
    parts = []
    for part in content:
        if isinstance(part, dict) and part.get("type") in OUTPUT_TEXT_TYPES and isinstance(part.get("text"), str):
            parts.append(part["text"])
    return "".join(parts) if parts else None


def extract_assistant_message_text(event: dict[str, Any]) -> str | None:
    candidates = []
    if isinstance(event.get("message"), dict):
        candidates.append(event["message"])
    value_message = event.get("v", {}).get("message") if isinstance(event.get("v"), dict) else None
    if isinstance(value_message, dict):
        candidates.append(value_message)
    for candidate in candidates:
        role = candidate.get("author", {}).get("role") if isinstance(candidate.get("author"), dict) else None
        if role and role != "assistant":
            continue
        parts = candidate.get("content", {}).get("parts") if isinstance(candidate.get("content"), dict) else None
        if isinstance(parts, list) and parts and isinstance(parts[0], str):
            return parts[0]
    return None


def extract_assistant_message_id(event: dict[str, Any]) -> str | None:
    if not isinstance(event, dict):
        return None
    for path in [("response", "id"), ("item", "id")]:
        node = event.get(path[0])
        if isinstance(node, dict) and node.get(path[1]):
            return str(node[path[1]])
    for key in ["item_id", "message_id"]:
        if event.get(key):
            return str(event[key])
    message = event.get("message")
    if isinstance(message, dict) and message.get("id"):
        return str(message["id"])
    return None


def is_patch_operation(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("p"), str) and isinstance(value.get("o"), str)


def apply_patch_operation(answer: str, op: dict[str, Any]) -> str:
    path = op.get("p")
    operation = op.get("o")
    value = op.get("v")
    if path == "/message/content/parts/0" and isinstance(value, str):
        if operation == "append":
            return answer + value
        if operation in {"replace", "add"}:
            return merge_full_text(answer, value)
    if path == "/message/content/parts" and operation in {"replace", "add"} and isinstance(value, list) and value and isinstance(value[0], str):
        return merge_full_text(answer, value[0])
    if path == "/message" and operation in {"replace", "add"} and isinstance(value, dict):
        return merge_full_text(answer, extract_assistant_message_text({"message": value}))
    return answer


def merge_full_text(answer: str, full_text: str | None) -> str:
    if not full_text:
        return answer
    if not answer or full_text.startswith(answer):
        return full_text
    if answer.endswith(full_text):
        return answer
    return answer + "\n\n" + full_text


def is_done_event(event: Any) -> bool:
    return isinstance(event, dict) and event.get("type") in DONE_TYPES


def openai_error(status: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": "relay_error", "code": "relay_error"}},
    )


def openai_messages_to_text(messages: Any) -> str:
    if not isinstance(messages, list):
        return ""
    parts: list[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "user")
        content = openai_content_to_text(message.get("content"))
        if content:
            parts.append(f"{role}: {content}" if role in {"system", "developer"} else content)
    return "\n\n".join(parts).strip()


def openai_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text" and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(part.strip() for part in parts if part and part.strip())
    return ""


def openai_messages_to_images(messages: Any) -> list[dict[str, Any]]:
    images: list[dict[str, Any]] = []
    if not isinstance(messages, list):
        return images
    for message in messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "image_url":
                continue
            image_url = item.get("image_url")
            url = image_url.get("url") if isinstance(image_url, dict) else image_url
            if isinstance(url, str) and url.strip():
                images.append({"url": url.strip(), "name": "image"})
    return images


def openai_chat_completion_response(model: str, answer: str) -> dict[str, Any]:
    completion_id = "chatcmpl-" + uuid.uuid4().hex
    created = int(time.time())
    return {
        "id": completion_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": answer},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def openai_chat_completion_stream(user_id: str, payload: WebChatMessageRequest, model: str) -> Iterable[str]:
    completion_id = "chatcmpl-" + uuid.uuid4().hex
    created = int(time.time())
    yield "data: " + json.dumps(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n\n"
    try:
        for item in stream_web_chat_turn(user_id, payload):
            if isinstance(item, str):
                chunk = sse_data_from_line(item)
                if isinstance(chunk, dict) and isinstance(chunk.get("delta"), str) and chunk["delta"]:
                    yield "data: " + json.dumps(
                        {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [{"index": 0, "delta": {"content": chunk["delta"]}, "finish_reason": None}],
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ) + "\n\n"
    except Exception as exc:
        message = exc.message if isinstance(exc, AppError) else exception_summary(exc)
        yield "data: " + json.dumps({"error": {"message": message, "type": "relay_error", "code": "relay_error"}}, ensure_ascii=False) + "\n\n"
    yield "data: " + json.dumps(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ) + "\n\n"
    yield "data: [DONE]\n\n"


def sse_data_from_line(line: str) -> Any:
    for text in line.splitlines():
        text = text.strip()
        if not text.startswith("data:"):
            continue
        data = text[5:].strip()
        if not data or data == "[DONE]":
            return None
        try:
            return json.loads(data)
        except Exception:
            return None
    return None


@app.api_route("/v1/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@app.api_route("/backend-api/codex/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@db_write_api
async def proxy(path: str, request: Request) -> Response:
    body = await request.body()
    event_stream = "text/event-stream" in (request.headers.get("accept") or "")
    raw_key = bearer_token(request.headers.get("authorization")) or request.headers.get("x-api-key")
    try:
        api_key = authenticate_api_key(raw_key)
    except AppError as exc:
        return local_proxy_error(exc.status, exc.message, event_stream)
    if user_balance(api_key["user_id"]) < Decimal("0"):
        return local_proxy_error(402, "余额不足", event_stream)
    client_type = detect_client_type(request, body)
    upstreams = acquire_upstreams(client_type)
    if not upstreams:
        return local_proxy_error(404, "No upstream service configured", event_stream)
    request_uri = request.url.path
    query_string = request.url.query
    started = time.monotonic()
    client: httpx.Client | None = None
    stream: httpx.Response | None = None
    upstream: dict[str, Any] | None = None
    prefetched_body: bytes | None = None
    last_error = "Unable to reach upstream service"
    for index, candidate in enumerate(upstreams):
        try:
            upstream_body = normalize_upstream_body(body, candidate, client_type, event_stream)
            upstream_url = join_upstream_url(upstream_endpoint(candidate), request_uri, query_string)
            headers = build_upstream_headers(request, candidate, client_type, upstream_body)
            client = httpx.Client(timeout=None)
            upstream_request = client.build_request(request.method, upstream_url, content=upstream_body, headers=headers)
            candidate_stream = client.send(upstream_request, stream=True)
            if should_inspect_quota_retry(client_type, candidate_stream.status_code):
                candidate_body = candidate_stream.read()
                candidate_stream.close()
                client.close()
                if is_retryable_quota_error(candidate_stream.status_code, candidate_body) and index < len(upstreams) - 1:
                    last_error = f"Upstream service {candidate.get('id')} quota limited"
                    continue
                stream = candidate_stream
                upstream = candidate
                prefetched_body = candidate_body
                break
            stream = candidate_stream
            upstream = candidate
            break
        except Exception as exc:
            last_error = exception_summary(exc)
            try:
                if stream is not None:
                    stream.close()
                if client is not None:
                    client.close()
            except Exception:
                pass
            if index < len(upstreams) - 1:
                continue
    if stream is None or upstream is None:
        return local_proxy_error(502, last_error, event_stream)
    response_headers = {
        key: value
        for key, value in stream.headers.items()
        if key.lower() not in DROP_RESPONSE_HEADERS
    }
    response_headers["cache-control"] = "no-cache"
    response_headers["x-accel-buffering"] = "no"
    media_type = stream.headers.get("content-type") or ("text/event-stream" if event_stream else "application/json")

    def generate() -> Iterable[bytes]:
        captured = bytearray()
        first_token_ms = 0
        response_bytes = 0
        saw_first = False
        status_code = stream.status_code
        try:
            source = [prefetched_body] if prefetched_body is not None else stream.iter_bytes()
            for chunk in source:
                if not chunk:
                    continue
                if not saw_first:
                    saw_first = True
                    first_token_ms = int((time.monotonic() - started) * 1000)
                response_bytes += len(chunk)
                if len(captured) < 256 * 1024:
                    captured.extend(chunk[: 256 * 1024 - len(captured)])
                yield chunk
        finally:
            try:
                if prefetched_body is None:
                    stream.close()
                if client is not None:
                    client.close()
            finally:
                use_time_ms = int((time.monotonic() - started) * 1000)
                record_proxy_request_sync(
                    api_key,
                    client_type,
                    request.method,
                    request_uri,
                    query_string,
                    client_ip(request),
                    request.headers.get("user-agent"),
                    body,
                    bytes(captured),
                    upstream.get("id") if upstream else None,
                    status_code,
                    use_time_ms,
                    first_token_ms or use_time_ms,
                )

    return StreamingResponse(generate(), status_code=stream.status_code, headers=response_headers, media_type=media_type)


def authenticate_api_key(key: str | None) -> sqlite3.Row:
    if not key or not key.startswith("relay_"):
        raise AppError(401, "UNAUTHORIZED", "Invalid API key")
    with db() as con:
        row = con.execute(
            "select * from api_keys where key_hash = ? and status = 'active'", (sha256_key(key),)
        ).fetchone()
    if not row:
        raise AppError(401, "UNAUTHORIZED", "Invalid API key")
    return row


def user_balance(user_id: str) -> Decimal:
    with db() as con:
        deduct_expired_redeem_codes(con, user_id)
        row = con.execute("select balance from users where id = ?", (user_id,)).fetchone()
    return parse_decimal(row["balance"]) if row else Decimal("-1")


def detect_client_type(request: Request, body: bytes) -> str:
    path = request.url.path.lower()
    headers = " ".join([request.headers.get("user-agent", ""), request.headers.get("originator", "")]).lower()
    body_text = body[:4096].decode("utf-8", "ignore").lower()
    if path.startswith("/backend-api/codex") or "codex" in headers or "codex" in body_text:
        return "CODEX"
    if "anthropic" in path or "claude" in headers or "claude" in body_text:
        return "CLAUDE"
    return "CODEX"


def acquire_upstreams(client_type: str) -> list[dict[str, Any]]:
    with db() as con:
        if client_type == "CLAUDE":
            rows = con.execute("select * from claude_services order by id").fetchall()
            return [row_to_dict(row) for row in rows]
        mode = int(setting(con, "openai.request_mode", "2"))
        if mode == 2:
            rows = con.execute(
                """
                select s.*, p.profile_name, p.auth_mode, p.openai_api_key, p.access_token,
                       p.account_id, p.base_url as profile_base_url, p.model, p.reasoning_effort
                from openai_services s
                join openai_codex_profiles p on p.openai_service_id = s.id
                order by s.id
                """
            ).fetchall()
        else:
            rows = con.execute("select * from openai_services order by id").fetchall()
        return [row_to_dict(row) for row in rows]


def upstream_endpoint(upstream: dict[str, Any]) -> str:
    return first_non_blank(upstream.get("profile_base_url"), upstream.get("api_endpoint"), "https://chatgpt.com/backend-api/codex")


def should_inspect_quota_retry(client_type: str, status_code: int) -> bool:
    return client_type == "CODEX" and status_code in {402, 403, 429}


def is_retryable_quota_error(status_code: int, body: bytes | None) -> bool:
    if status_code not in {402, 403, 429}:
        return False
    if not body:
        return status_code == 402
    text = body.decode("utf-8", "ignore").lower()
    markers = [
        "insufficient_quota",
        "rate_limit_exceeded",
        "quota",
        "billing",
        "credit",
        "balance",
        "rate limit",
        "额度",
        "配额",
        "余额",
        "棰濆害",
        "閰嶉",
        "浣欓",
    ]
    return any(marker in text for marker in markers)


def build_upstream_headers(request: Request, upstream: dict[str, Any], client_type: str, body: bytes) -> dict[str, str]:
    if client_type == "CODEX":
        accept = request.headers.get("accept")
        headers = {
            "accept": "text/event-stream" if not accept or b'"stream":true' in body else accept,
            "content-type": "application/json",
            "originator": "codex_cli_rs",
            "user-agent": "codex_cli_rs/0.126.0 (Windows 10; x86_64)",
            "version": "0.126.0",
        }
        token = first_non_blank(upstream.get("access_token"), upstream.get("openai_api_key"), upstream.get("token"))
        if token:
            headers["authorization"] = "Bearer " + clean_bearer(token)
        if upstream.get("account_id"):
            headers["ChatGPT-Account-ID"] = upstream["account_id"]
        return headers
    headers = {k: v for k, v in request.headers.items() if k.lower() not in DROP_REQUEST_HEADERS}
    token = clean_bearer(upstream.get("token") or "")
    headers["x-api-key"] = token
    if "token-plan-cn.xiaomimimo.com" in (upstream.get("api_endpoint") or "").lower():
        headers["authorization"] = "Bearer " + token
    return headers


def normalize_upstream_body(body: bytes, upstream: dict[str, Any], client_type: str, event_stream: bool) -> bytes:
    if not body:
        return body
    try:
        root = json.loads(body)
        if not isinstance(root, dict):
            return body
        if client_type == "CODEX":
            if upstream.get("profile_name"):
                if not root.get("model") and upstream.get("model"):
                    root["model"] = upstream["model"]
                root.setdefault("store", False)
                root.setdefault("parallel_tool_calls", True)
                effort = root.pop("reasoning_effort", None) or upstream.get("reasoning_effort")
                if effort and "reasoning" not in root:
                    root["reasoning"] = {"effort": effort}
            if event_stream:
                root["stream"] = True
            if "chatgpt.com/backend-api/codex" in upstream_endpoint(upstream).lower():
                root.pop("truncation", None)
        elif client_type == "CLAUDE" and "token-plan-cn.xiaomimimo.com" in upstream_endpoint(upstream).lower():
            if isinstance(root.get("model"), str):
                root["model"] = root["model"].lower()
        return json.dumps(root, ensure_ascii=False, separators=(",", ":")).encode()
    except Exception:
        return body


def join_upstream_url(base_url: str, request_uri: str, query: str) -> str:
    base = trim_slash(base_url)
    suffix = request_uri
    if suffix.startswith("/v1"):
        suffix = suffix[len("/v1") :]
    elif suffix.startswith("/backend-api/codex"):
        suffix = suffix[len("/backend-api/codex") :]
    target = base + suffix
    return target + ("?" + query if query else "")


def local_proxy_error(status: int, message: str, event_stream: bool) -> Response:
    body = {"error": {"message": message, "type": "relay_error", "code": "relay_error"}}
    if event_stream:
        return Response(
            content=sse_event("error", body),
            status_code=status,
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )
    return JSONResponse(status_code=status, content=body)


def record_proxy_request_sync(
    api_key: sqlite3.Row,
    client_type: str,
    request_method: str,
    request_uri: str,
    query_string: str,
    ip: str | None,
    user_agent: str | None,
    request_body: bytes,
    response_body: bytes,
    upstream_service_id: int | None,
    status_code: int,
    use_time_ms: int,
    first_token_ms: int,
) -> None:
    usage = parse_usage(request_body, response_body)
    with db() as con:
        price = con.execute("select * from model_catalog where id = ? and enabled = 1", (usage["model"],)).fetchone()
        cost = calculate_cost(con, usage, price)
        con.execute(
            """
            insert into request_logs
              (user_id, api_key_id, token_name, group_key, request_type, client_type, model,
               use_time_ms, first_token_ms, prompt_tokens, completion_tokens, cache_read_tokens,
               cache_creation_tokens, cost, ip, status, upstream_service_id, detail, created_at)
            values (?, ?, ?, ?, 'usage', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                api_key["user_id"],
                api_key["id"],
                api_key["name"] or display_key(api_key["key_hash"]),
                api_key["key_value"] or display_key(api_key["key_hash"]),
                client_type,
                usage["model"],
                use_time_ms,
                first_token_ms,
                usage["input"],
                usage["output"],
                usage["cache_read"],
                usage["cache_create"],
                decimal_text(cost),
                ip,
                "success" if 200 <= status_code < 300 else "error",
                upstream_service_id,
                response_body.decode("utf-8", "replace"),
                now_iso(),
            ),
        )
        if cost > 0:
            add_balance(con, api_key["user_id"], -cost)


def parse_usage(request_body: bytes, response_body: bytes) -> dict[str, Any]:
    texts = [response_body.decode("utf-8", "ignore"), request_body.decode("utf-8", "ignore")]
    payloads = []
    for text in texts:
        payloads.extend(parse_json_payloads(text))
    model = None
    input_tokens = output_tokens = cache_read = cache_create = 0
    for payload in payloads:
        usage = usage_from_payload(payload)
        model = first_non_blank(model, usage.get("model"))
        input_tokens = input_tokens or usage.get("input", 0)
        output_tokens = output_tokens or usage.get("output", 0)
        cache_read = cache_read or usage.get("cache_read", 0)
        cache_create = cache_create or usage.get("cache_create", 0)
    for text in texts:
        model = first_non_blank(model, regex_first(text, MODEL_RE), regex_first(text, NAME_RE))
    return {"model": model, "input": input_tokens, "output": output_tokens, "cache_read": cache_read, "cache_create": cache_create}


def parse_json_payloads(text: str) -> list[Any]:
    text = text.strip()
    if not text:
        return []
    if text.startswith("{") or text.startswith("["):
        try:
            return [json.loads(text)]
        except Exception:
            return []
    payloads = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            data = line[5:].strip()
            if data and data != "[DONE]":
                try:
                    payloads.append(json.loads(data))
                except Exception:
                    pass
    return payloads


def usage_from_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    response = payload.get("response") if isinstance(payload.get("response"), dict) else {}
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    usage = response.get("usage") or payload.get("usage") or message.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    return {
        "model": first_non_blank(response.get("model"), payload.get("model"), message.get("model")),
        "input": int_first(usage, ["input_tokens", "prompt_tokens", "inputTokens", "promptTokens"]),
        "output": int_first(usage, ["output_tokens", "completion_tokens", "outputTokens", "completionTokens"]),
        "cache_read": int_first_nested(usage, ["cache_read_input_tokens", "cache_read_tokens"], ["input_tokens_details", "prompt_tokens_details"], "cached_tokens"),
        "cache_create": int_first_nested(usage, ["cache_creation_input_tokens", "cache_creation_tokens"], ["input_tokens_details", "prompt_tokens_details"], "cache_creation_tokens"),
    }


def calculate_cost(con: sqlite3.Connection, usage: dict[str, Any], price: sqlite3.Row | None) -> Decimal:
    if not price:
        return Decimal("0.000000")
    regular_input = max(0, usage["input"] - usage["cache_read"] - usage["cache_create"])
    cost = (
        parse_decimal(price["input_price"]) * regular_input
        + parse_decimal(price["output_price"]) * usage["output"]
        + parse_decimal(price["cached_input_price"]) * usage["cache_read"]
        + parse_decimal(price["cache_creation_price"]) * usage["cache_create"]
    ) / Decimal(1_000_000)
    multiplier = parse_decimal(setting(con, "billing.cost_multiplier", "1.2"))
    return (cost * multiplier).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def add_balance(con: sqlite3.Connection, user_id: str, amount: Decimal) -> Decimal:
    row = con.execute("select balance from users where id = ?", (user_id,)).fetchone()
    if not row:
        raise AppError(401, "UNAUTHORIZED", "Unauthorized")
    next_balance = parse_decimal(row["balance"]) + amount
    con.execute("update users set balance = ? where id = ?", (decimal_text(next_balance), user_id))
    return next_balance


def deduct_expired_redeem_codes(con: sqlite3.Connection, user_id: str) -> Decimal | None:
    ts = now_iso()
    rows = con.execute(
        """
        select * from redeem_codes
        where holder_user_id = ?
          and expired_deducted_at is null
          and expires_at <= ?
        order by expires_at, id
        """,
        (user_id, ts),
    ).fetchall()
    balance_value: Decimal | None = None
    for row in rows:
        balance_value = add_balance(con, user_id, -parse_decimal(row["amount"]))
        con.execute(
            """
            update redeem_codes
            set expired_deducted_at = ?, updated_at = ?
            where id = ? and expired_deducted_at is null
            """,
            (ts, ts, row["id"]),
        )
    return balance_value


def setting(con: sqlite3.Connection, key: str, default: str) -> str:
    row = con.execute("select setting_value from app_settings where setting_key = ?", (key,)).fetchone()
    return row["setting_value"] if row else default


def bool_setting(con: sqlite3.Connection, key: str, default: bool) -> bool:
    raw = setting(con, key, "true" if default else "false")
    return str(raw).strip().lower() not in {"0", "false", "no", "off", ""}


def turnstile_enabled() -> bool:
    try:
        with db() as con:
            return bool_setting(con, "auth.turnstile_enabled", True)
    except sqlite3.Error:
        return True


def recharge_payment_settings() -> dict[str, str]:
    try:
        with db() as con:
            return {
                "alipayQrImage": setting(con, "recharge.alipay_qr_image", ""),
                "wechatQrImage": setting(con, "recharge.wechat_qr_image", ""),
            }
    except sqlite3.Error:
        return {"alipayQrImage": "", "wechatQrImage": ""}


def setting_image_dir() -> Path:
    return ROOT.parent / "frontend" / "public" / "uploads" / "settings"


def setting_image_path_from_url(value: str) -> Path | None:
    prefix = "/uploads/settings/"
    if not value.startswith(prefix):
        return None
    path = (setting_image_dir() / value[len(prefix) :]).resolve()
    upload_root = setting_image_dir().resolve()
    try:
        path.relative_to(upload_root)
    except ValueError:
        return None
    return path


def delete_setting_image(value: str) -> None:
    path = setting_image_path_from_url(value)
    if path and path.exists() and path.is_file():
        try:
            path.unlink()
        except OSError:
            pass


def save_setting_image(file_name: str, data_url: str, setting_key: str) -> str:
    match = re.match(r"^data:(image/(?:png|jpeg|jpg|webp|gif));base64,(.+)$", data_url or "", re.I | re.S)
    if not match:
        raise AppError(400, "VALIDATION_FAILED", "Image must be a PNG, JPG, WebP, or GIF data URL")
    media_type = match.group(1).lower()
    extension = {
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/webp": "webp",
        "image/gif": "gif",
    }[media_type]
    try:
        image_bytes = base64.b64decode(match.group(2), validate=True)
    except Exception as exc:
        raise AppError(400, "VALIDATION_FAILED", "Invalid image data") from exc
    if not image_bytes:
        raise AppError(400, "VALIDATION_FAILED", "Image is empty")
    if len(image_bytes) > 5 * 1024 * 1024:
        raise AppError(400, "VALIDATION_FAILED", "Image must be 5 MB or smaller")

    safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", setting_key).strip("-")[:80]
    if not safe_stem:
        safe_stem = "setting-image"
    upload_dir = setting_image_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    for old_file in upload_dir.glob(f"{safe_stem}.*"):
        if old_file.is_file():
            try:
                old_file.unlink()
            except OSError:
                pass
    target = upload_dir / f"{safe_stem}.{extension}"
    target.write_bytes(image_bytes)
    return f"/uploads/settings/{target.name}"


def verify_turnstile(token: str | None, request: Request) -> None:
    if not turnstile_enabled():
        return
    token = (token or "").strip()
    if not token or len(token) > 2048:
        raise AppError(400, "TURNSTILE_REQUIRED", "Human verification is required")
    if not TURNSTILE_SECRET.strip():
        raise AppError(500, "TURNSTILE_NOT_CONFIGURED", "Turnstile is not configured")

    body = {
        "secret": TURNSTILE_SECRET,
        "response": token,
    }
    ip = client_ip(request)
    if ip:
        body["remoteip"] = ip

    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(TURNSTILE_VERIFY_URL, data=body)
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        raise AppError(400, "TURNSTILE_FAILED", "Human verification failed") from exc

    if not payload.get("success"):
        raise AppError(400, "TURNSTILE_FAILED", "Human verification failed", payload.get("error-codes"))


def regex_first(text: str, pattern: re.Pattern[str]) -> str | None:
    match = pattern.search(text or "")
    return match.group(1) if match else None


def int_first(data: dict[str, Any], keys: list[str]) -> int:
    for key in keys:
        if key in data:
            try:
                return max(0, int(data[key]))
            except Exception:
                pass
    return 0


def int_first_nested(data: dict[str, Any], direct_keys: list[str], object_keys: list[str], nested_key: str) -> int:
    direct = int_first(data, direct_keys)
    if direct:
        return direct
    for object_key in object_keys:
        child = data.get(object_key)
        if isinstance(child, dict) and nested_key in child:
            try:
                return max(0, int(child[nested_key]))
            except Exception:
                pass
    return 0


def clean_bearer(token: str) -> str:
    token = token.strip()
    return token[7:].strip() if token.lower().startswith("bearer ") else token


def client_ip(request: Request) -> str | None:
    for header in ["cf-connecting-ip", "x-forwarded-for", "x-real-ip"]:
        value = request.headers.get(header)
        if value:
            return value.split(",")[0].strip()
    return request.client.host if request.client else None


def trim_slash(value: str) -> str:
    return value.rstrip("/")


def truncate(value: str, max_len: int) -> str:
    return value if len(value) <= max_len else value[:max_len] + "..."


def exception_summary(exc: Exception) -> str:
    message = str(exc) or exc.__class__.__name__
    return truncate(message, 180)
