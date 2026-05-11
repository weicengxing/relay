from __future__ import annotations

import base64
import asyncio
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
from typing import Any, AsyncIterable, Iterable
from urllib.parse import quote, urljoin, urlparse

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool


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
