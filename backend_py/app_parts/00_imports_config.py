from __future__ import annotations

import atexit
import base64
import asyncio
import copy
import concurrent.futures
import hashlib
import hmac
import html as html_lib
import json
import logging
import logging.handlers
import os
import queue as queue_lib
import random
import re
import secrets
import smtplib
import sqlite3
import ssl
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from email.message import EmailMessage
from pathlib import Path
from typing import Any, AsyncIterable, Iterable
from urllib import request as urllib_request
from urllib.parse import quote, urlencode, urljoin, urlparse

import httpx
import anyio.to_thread
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("RELAY_PY_DB", str(ROOT / "relay_py.db")))
JWT_SECRET = os.getenv("RELAY_PY_JWT_SECRET", "relay-python-dev-secret-change-me")
CHAT_PROFILES_PATH = Path(os.getenv("RELAY_PY_CHAT_PROFILES", r"D:\freeclaude\chat_profiles.json"))
CODEX_PROFILES_PATH = Path(os.getenv("RELAY_PY_CODEX_PROFILES", r"D:\freeclaude\codex_profiles.json"))
ALLOW_DEV_VERIFY_CODE = os.getenv("RELAY_PY_ALLOW_DEV_VERIFY_CODE", "1") == "1"
EMAIL_REGISTER_ENABLED = os.getenv("EMAIL_REGISTER_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}
DEFAULT_BALANCE = Decimal("5.000000")
OWNER_EMAIL = "2997657261@qq.com"
OWNER_EMAIL_ALIASES = {OWNER_EMAIL, "2997657261"}
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
DC_AUTH_ENABLED = os.getenv("DC_AUTH_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
DC_AUTH_ORIGIN = os.getenv("DC_AUTH_ORIGIN", "https://dc.hhhl.cc").rstrip("/")
DC_AUTH_APP_SECRET = os.getenv("DC_AUTH_APP_SECRET", "").strip()
DC_AUTH_PUBLIC_API_BASE_URL = os.getenv("DC_AUTH_PUBLIC_API_BASE_URL", "").strip().rstrip("/")
DC_AUTH_FRONTEND_BASE_URL = os.getenv("DC_AUTH_FRONTEND_BASE_URL", "").strip().rstrip("/")
DC_AUTH_STATE_TTL_SECONDS = int(os.getenv("DC_AUTH_STATE_TTL_SECONDS", "600"))
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
ASYNC_ACCESS_LOG_QUEUE_SIZE = int(os.getenv("RELAY_PY_ASYNC_ACCESS_LOG_QUEUE_SIZE", "10000"))
ASYNC_ACCESS_LOG_BATCH_SIZE = int(os.getenv("RELAY_PY_ASYNC_ACCESS_LOG_BATCH_SIZE", "256"))
ASYNC_ACCESS_LOG_FLUSH_INTERVAL = float(os.getenv("RELAY_PY_ASYNC_ACCESS_LOG_FLUSH_INTERVAL", "0.02"))


class AsyncBatchQueueHandler(logging.Handler):
    def __init__(self, log_queue: queue_lib.Queue[Any]):
        super().__init__()
        self.queue = log_queue
        self.dropped = 0
        self._dropped_lock = threading.Lock()

    def enqueue(self, record: logging.LogRecord) -> None:
        try:
            self.queue.put_nowait(record)
        except queue_lib.Full:
            with self._dropped_lock:
                self.dropped += 1

    def emit(self, record: logging.LogRecord) -> None:
        self.enqueue(copy.copy(record))

    def pop_dropped(self) -> int:
        with self._dropped_lock:
            value = self.dropped
            self.dropped = 0
            return value


class AsyncBatchLogWriter:
    def __init__(
        self,
        log_queue: queue_lib.Queue[Any],
        handlers: list[logging.Handler],
        queue_handler: AsyncBatchQueueHandler,
    ):
        self.queue = log_queue
        self.handlers = handlers
        self.queue_handler = queue_handler
        self.batch_size = max(1, ASYNC_ACCESS_LOG_BATCH_SIZE)
        self.flush_interval = max(0.001, ASYNC_ACCESS_LOG_FLUSH_INTERVAL)
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, name="relay-access-log-writer", daemon=True)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        try:
            self.queue.put_nowait(None)
        except queue_lib.Full:
            pass
        if self.thread.is_alive():
            self.thread.join(timeout=2)

    def run(self) -> None:
        while not self.stop_event.is_set():
            batch = self.read_batch()
            if batch:
                self.write_batch(batch)
        while True:
            try:
                record = self.queue.get_nowait()
            except queue_lib.Empty:
                break
            if record is not None:
                self.write_batch([record])

    def read_batch(self) -> list[logging.LogRecord]:
        try:
            first = self.queue.get(timeout=self.flush_interval)
        except queue_lib.Empty:
            return []
        if first is None:
            self.stop_event.set()
            return []

        batch = [first]
        deadline = time.monotonic() + self.flush_interval
        while len(batch) < self.batch_size:
            timeout = max(0.0, deadline - time.monotonic())
            try:
                record = self.queue.get(timeout=timeout)
            except queue_lib.Empty:
                break
            if record is None:
                self.stop_event.set()
                break
            batch.append(record)
        return batch

    def write_batch(self, records: list[logging.LogRecord]) -> None:
        dropped = self.queue_handler.pop_dropped()
        if dropped:
            records = [
                logging.LogRecord(
                    "uvicorn.access",
                    logging.WARNING,
                    __file__,
                    0,
                    "dropped %d access log records because the async log queue was full",
                    (dropped,),
                    None,
                )
            ] + records

        for handler in self.handlers:
            accepted = [
                record
                for record in records
                if record.levelno >= handler.level and handler.filter(record)
            ]
            if not accepted:
                continue
            if isinstance(handler, logging.StreamHandler):
                self.write_stream_batch(handler, accepted)
            else:
                for record in accepted:
                    handler.handle(record)

    def write_stream_batch(self, handler: logging.StreamHandler, records: list[logging.LogRecord]) -> None:
        stream = handler.stream
        terminator = getattr(handler, "terminator", "\n")
        try:
            message = "".join(handler.format(record) + terminator for record in records)
            handler.acquire()
            try:
                stream.write(message)
                handler.flush()
            finally:
                handler.release()
        except Exception:
            handler.handleError(records[0])


def configure_async_access_logger() -> None:
    logger = logging.getLogger("uvicorn.access")
    if getattr(logger, "_relay_async_queue_logging", False):
        return

    downstream_handlers = [
        handler for handler in logger.handlers if not isinstance(handler, AsyncBatchQueueHandler)
    ]
    if not downstream_handlers:
        downstream_handlers = [logging.StreamHandler()]

    log_queue: queue_lib.Queue[logging.LogRecord] = queue_lib.Queue(maxsize=ASYNC_ACCESS_LOG_QUEUE_SIZE)
    queue_handler = AsyncBatchQueueHandler(log_queue)
    queue_handler.setLevel(logging.NOTSET)
    writer = AsyncBatchLogWriter(log_queue, downstream_handlers, queue_handler)
    writer.start()

    logger.handlers = [queue_handler]
    logger.disabled = False
    logger.propagate = False
    setattr(logger, "_relay_async_queue_logging", True)
    setattr(logger, "_relay_async_queue_writer", writer)
    atexit.register(writer.stop)


configure_async_access_logger()


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


async def stream_in_dedicated_thread(factory: Any, *, name: str = "relay-stream-worker") -> AsyncIterable[Any]:
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
    stop = threading.Event()

    def enqueue(kind: str, value: Any = None) -> None:
        if stop.is_set() and kind != "done":
            return
        try:
            loop.call_soon_threadsafe(queue.put_nowait, (kind, value))
        except RuntimeError:
            stop.set()

    def worker() -> None:
        try:
            for item in factory():
                if stop.is_set():
                    break
                enqueue("item", item)
        except Exception as exc:
            enqueue("error", exc)
        finally:
            enqueue("done")

    thread = threading.Thread(target=worker, name=name, daemon=True)
    thread.start()
    try:
        while True:
            kind, value = await queue.get()
            if kind == "done":
                break
            if kind == "error":
                raise value
            yield value
    finally:
        stop.set()


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


_maintenance_state_lock = threading.Lock()
_maintenance_write_disabled_cache: bool | None = None


def set_maintenance_write_disabled_cache(value: bool) -> None:
    global _maintenance_write_disabled_cache
    with _maintenance_state_lock:
        _maintenance_write_disabled_cache = bool(value)


def refresh_maintenance_write_disabled_cache() -> bool:
    global _maintenance_write_disabled_cache
    try:
        with db() as con:
            row = con.execute(
                "select setting_value from app_settings where setting_key = ?",
                ("maintenance.write_disabled",),
            ).fetchone()
        value = str(row["setting_value"]).strip().lower() in {"1", "true", "yes", "on"} if row else False
    except sqlite3.Error:
        value = False
    with _maintenance_state_lock:
        _maintenance_write_disabled_cache = value
    return value


def maintenance_write_disabled() -> bool:
    with _maintenance_state_lock:
        cached = _maintenance_write_disabled_cache
    return bool(cached)


def owner_email_for_user_id(user_id: str) -> str | None:
    with db() as con:
        row = con.execute("select email from users where id = ?", (user_id,)).fetchone()
    return str(row["email"]).lower() if row and row["email"] else None


def is_owner_email(email: str | None) -> bool:
    return str(email or "").strip().lower() in OWNER_EMAIL_ALIASES


async def maintenance_request_is_owner(request: Request) -> bool:
    authorization = request.headers.get("authorization")
    if authorization and authorization.startswith("Bearer "):
        try:
            user_id = verify_jwt(authorization[len("Bearer ") :].strip())
            if is_owner_email(await run_in_threadpool(owner_email_for_user_id, user_id)):
                return True
        except Exception:
            pass

    if request.url.path in {"/api/auth/register-code", "/api/auth/register", "/api/auth/login"}:
        try:
            payload = await request.json()
            email = str(payload.get("email") or "").strip().lower() if isinstance(payload, dict) else ""
            return is_owner_email(email)
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
