from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "backend_py" / "relay_py.db"
DEFAULT_BASE_URL = "http://127.0.0.1:8085"
DEFAULT_EMAIL = "relay-codex-test@local.test"
DEFAULT_PASSWORD = "relay-codex-test-password"
DEFAULT_KEY_NAME = "codex-upstream-test"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_PROMPT = "Reply with exactly this JSON: {\"message\":\"codex upstream ok\"}"


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_key(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def ensure_test_api_key(db_path: Path, email: str, password: str, key_name: str) -> str:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        user = con.execute("select * from users where email = ?", (email,)).fetchone()
        if user:
            user_id = user["id"]
            con.execute(
                "update users set password_hash = ?, balance = '999.000000', status = 'active' where id = ?",
                (password, user_id),
            )
        else:
            user_id = str(uuid.uuid4())
            con.execute(
                """
                insert into users(id, email, password_hash, registration_ip, balance, status, created_at)
                values (?, ?, ?, null, '999.000000', 'active', ?)
                """,
                (user_id, email, password, now_iso()),
            )

        row = con.execute(
            "select * from api_keys where user_id = ? and name = ? and status = 'active'",
            (user_id, key_name),
        ).fetchone()
        if row and row["key_value"]:
            key = row["key_value"]
            expected_hash = sha256_key(key)
            if row["key_hash"] != expected_hash:
                con.execute("update api_keys set key_hash = ? where id = ?", (expected_hash, row["id"]))
        else:
            key = "relay_" + secrets.token_urlsafe(32).replace("-", "").replace("_", "")[:43]
            con.execute(
                """
                insert into api_keys(user_id, key_hash, key_value, name, status, created_at)
                values (?, ?, ?, ?, 'active', ?)
                """,
                (user_id, sha256_key(key), key, key_name, now_iso()),
            )
        con.commit()
        return key
    finally:
        con.close()


def codex_profiles_summary(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            select s.id, s.api_endpoint, p.profile_name, p.base_url, p.model, p.reasoning_effort,
                   length(coalesce(p.access_token, '')) as access_token_len,
                   length(coalesce(p.openai_api_key, '')) as openai_api_key_len
            from openai_services s
            join openai_codex_profiles p on p.openai_service_id = s.id
            where s.enabled = 1
            order by s.id
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


async def is_healthy(base_url: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{base_url.rstrip('/')}/api/health")
        return response.status_code == 200
    except Exception:
        return False


async def wait_healthy(base_url: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if await is_healthy(base_url):
            return
        await asyncio.sleep(0.5)
    raise RuntimeError(f"{base_url} did not become healthy within {timeout_s:.0f}s")


def start_server(port: int) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("CHAT_HISTORY_ENABLED", "false")
    env.setdefault("RELAY_PY_THREAD_TOKENS", "100")
    log_file = ROOT / "backend_py" / "codex-upstream-8085.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log = log_file.open("w", encoding="utf-8", errors="replace")
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend_py.app:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--workers",
        "1",
    ]
    return subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)


def stop_server(proc: subprocess.Popen | None) -> None:
    if not proc or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def request_body(model: str, prompt: str, stream: bool) -> dict[str, Any]:
    return {
        "model": model,
        "instructions": "You are a concise upstream health-check responder.",
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            }
        ],
        "store": False,
        "parallel_tool_calls": True,
        "reasoning": {"effort": "low"},
        "stream": stream,
    }


def parse_sse_block(block: str) -> tuple[str, Any, str]:
    event = "message"
    data_lines: list[str] = []
    for line in block.splitlines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    raw = "\n".join(data_lines)
    if not raw:
        return event, None, raw
    if raw == "[DONE]":
        return event, "[DONE]", raw
    try:
        return event, json.loads(raw), raw
    except json.JSONDecodeError:
        return event, raw, raw


def extract_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    if isinstance(payload.get("delta"), str):
        return payload["delta"]
    if isinstance(payload.get("text"), str):
        return payload["text"]
    if payload.get("type") in {"response.output_text.delta", "response.refusal.delta"}:
        return str(payload.get("delta") or "")
    if payload.get("type") in {"response.output_text.done", "response.refusal.done"}:
        return str(payload.get("text") or "")
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        delta = choices[0].get("delta") if isinstance(choices[0], dict) else None
        if isinstance(delta, dict):
            return str(delta.get("content") or "")
    return ""


async def call_stream(base_url: str, api_key: str, body: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/v1/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Originator": "codex_cli_rs",
        "User-Agent": "codex_cli_rs/0.126.0 upstream-check",
        "X-Client-Request-Id": str(uuid.uuid4()),
    }
    started = time.perf_counter()
    first_event_ms: float | None = None
    event_counts: dict[str, int] = {}
    raw_preview: list[str] = []
    text_parts: list[str] = []
    errors: list[str] = []
    status_code: int | None = None
    bytes_read = 0
    buffer = ""

    timeout = httpx.Timeout(connect=10, read=None, write=30, pool=None)
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with asyncio.timeout(timeout_s):
            async with client.stream("POST", url, headers=headers, json=body) as response:
                status_code = response.status_code
                async for chunk in response.aiter_text():
                    if first_event_ms is None:
                        first_event_ms = (time.perf_counter() - started) * 1000
                    bytes_read += len(chunk.encode("utf-8"))
                    buffer += chunk
                    blocks = buffer.replace("\r\n", "\n").split("\n\n")
                    buffer = blocks.pop() or ""
                    for block in blocks:
                        if not block.strip():
                            continue
                        if block.startswith(":"):
                            event_counts["keepalive"] = event_counts.get("keepalive", 0) + 1
                            continue
                        event, payload, raw = parse_sse_block(block)
                        event_counts[event] = event_counts.get(event, 0) + 1
                        if raw and len(raw_preview) < 8:
                            raw_preview.append(raw[:1000])
                        text = extract_text(payload)
                        if text:
                            text_parts.append(text)
                        if event == "error" or (isinstance(payload, dict) and payload.get("error")):
                            errors.append(json.dumps(payload, ensure_ascii=False)[:2000])
                if buffer and len(raw_preview) < 8 and "\n\n" not in buffer:
                    raw_preview.append(buffer[:1000])

    if buffer.strip():
        event, payload, raw = parse_sse_block(buffer)
        if raw:
            event_counts[event] = event_counts.get(event, 0) + 1
            if len(raw_preview) < 8:
                raw_preview.append(raw[:1000])
        text = extract_text(payload)
        if text:
            text_parts.append(text)
        if event == "error" or (isinstance(payload, dict) and payload.get("error")):
            errors.append(json.dumps(payload, ensure_ascii=False)[:2000])

    return {
        "url": url,
        "status_code": status_code,
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
        "first_event_ms": round(first_event_ms, 1) if first_event_ms is not None else None,
        "bytes_read": bytes_read,
        "event_counts": event_counts,
        "text_preview": "".join(text_parts)[:2000],
        "errors": errors,
        "raw_preview": raw_preview,
    }


async def call_json(base_url: str, api_key: str, body: dict[str, Any], timeout_s: float) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/v1/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Originator": "codex_cli_rs",
        "User-Agent": "codex_cli_rs/0.126.0 upstream-check",
    }
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.post(url, headers=headers, json=body)
    text = response.text
    payload: Any
    try:
        payload = response.json()
    except Exception:
        payload = text[:4000]
    return {
        "url": url,
        "status_code": response.status_code,
        "total_ms": round((time.perf_counter() - started) * 1000, 1),
        "bytes_read": len(response.content),
        "payload_preview": payload if isinstance(payload, dict) else str(payload)[:4000],
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Send one health-check request through Relay's Codex upstream proxy.")
    parser.add_argument("--base-url", default=os.getenv("CODEX_UPSTREAM_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--port", type=int, default=8085)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--api-key", default=os.getenv("CODEX_UPSTREAM_API_KEY", ""))
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--key-name", default=DEFAULT_KEY_NAME)
    parser.add_argument("--model", default=os.getenv("CODEX_UPSTREAM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--prompt", default=os.getenv("CODEX_UPSTREAM_PROMPT", DEFAULT_PROMPT))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("CODEX_UPSTREAM_TIMEOUT", "180")))
    parser.add_argument("--no-start-server", action="store_true")
    parser.add_argument("--non-stream", action="store_true")
    parser.add_argument("--json-out", type=Path, default=ROOT / "backend_py" / "codex-upstream-result.json")
    args = parser.parse_args()

    api_key = args.api_key.strip() or ensure_test_api_key(args.db_path, args.email, args.password, args.key_name)
    profiles = codex_profiles_summary(args.db_path)
    started_proc: subprocess.Popen | None = None

    try:
        if not await is_healthy(args.base_url):
            if args.no_start_server:
                raise RuntimeError(f"{args.base_url} is not healthy")
            started_proc = start_server(args.port)
            await wait_healthy(args.base_url, 45)

        body = request_body(args.model, args.prompt, stream=not args.non_stream)
        print(f"target={args.base_url.rstrip('/')}/v1/responses")
        print(f"model={args.model} stream={not args.non_stream}")
        print(f"codex_profiles={json.dumps(profiles, ensure_ascii=False)}")
        if args.non_stream:
            result = await call_json(args.base_url, api_key, body, args.timeout)
        else:
            result = await call_stream(args.base_url, api_key, body, args.timeout)
        output = {"request": body, "profiles": profiles, "result": result}
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(f"wrote={args.json_out}")
        if result.get("errors"):
            return 1
        status_code = int(result.get("status_code") or 0)
        return 0 if 200 <= status_code < 300 else 1
    finally:
        stop_server(started_proc)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
