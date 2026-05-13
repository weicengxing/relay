from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
import statistics
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from test_codex_upstream import DEFAULT_DB, request_body


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROMPT = 'Reply with exactly this JSON: {"message":"direct codex ok"}'


@dataclass
class Result:
    ok: bool
    status_code: int | None
    total_ms: float
    first_event_ms: float | None
    bytes_read: int
    completed: bool
    error: str | None


def load_profile(db_path: Path, service_id: int) -> dict[str, Any]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            """
            select s.id, s.api_endpoint, s.concurrent_limit, p.profile_name, p.access_token,
                   p.openai_api_key, p.account_id, p.base_url, p.model, p.reasoning_effort
            from openai_services s
            join openai_codex_profiles p on p.openai_service_id = s.id
            where s.id = ?
            """,
            (service_id,),
        ).fetchone()
        if not row:
            raise RuntimeError(f"Codex profile service id {service_id} was not found")
        profile = dict(row)
        token = (profile.get("access_token") or profile.get("openai_api_key") or "").strip()
        if not token:
            raise RuntimeError(f"Codex profile service id {service_id} has no token")
        return profile
    finally:
        con.close()


def endpoint(profile: dict[str, Any]) -> str:
    base = (profile.get("base_url") or profile.get("api_endpoint") or "https://chatgpt.com/backend-api/codex").rstrip("/")
    if base.endswith("/responses"):
        return base
    return base + "/responses"


def clean_bearer(token: str) -> str:
    token = token.strip()
    return token[7:].strip() if token.lower().startswith("bearer ") else token


def headers(profile: dict[str, Any]) -> dict[str, str]:
    token = clean_bearer(profile.get("access_token") or profile.get("openai_api_key") or "")
    result = {
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Originator": "codex_cli_rs",
        "User-Agent": "codex_cli_rs/0.126.0 direct-upstream-stress",
        "Version": "0.126.0",
        "X-Client-Request-Id": str(uuid.uuid4()),
    }
    account_id = (profile.get("account_id") or "").strip()
    if account_id:
        result["ChatGPT-Account-ID"] = account_id
    return result


def parse_sse_block(block: str) -> tuple[str, Any]:
    event = "message"
    data_lines: list[str] = []
    for line in block.splitlines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    raw = "\n".join(data_lines)
    if not raw:
        return event, None
    if raw == "[DONE]":
        return event, raw
    try:
        return event, json.loads(raw)
    except json.JSONDecodeError:
        return event, raw


async def call_once(client: httpx.AsyncClient, url: str, profile: dict[str, Any], body: dict[str, Any], timeout_s: float) -> Result:
    started = time.perf_counter()
    first_event_ms: float | None = None
    bytes_read = 0
    status_code: int | None = None
    completed = False
    error: str | None = None
    buffer = ""
    try:
        async with asyncio.timeout(timeout_s):
            async with client.stream("POST", url, headers=headers(profile), json=body) as response:
                status_code = response.status_code
                if response.status_code >= 400:
                    content = await response.aread()
                    return Result(
                        ok=False,
                        status_code=status_code,
                        total_ms=(time.perf_counter() - started) * 1000,
                        first_event_ms=None,
                        bytes_read=len(content),
                        completed=False,
                        error=f"HTTP {status_code}: {content[:1200].decode('utf-8', 'replace')}",
                    )
                async for chunk in response.aiter_text():
                    if first_event_ms is None:
                        first_event_ms = (time.perf_counter() - started) * 1000
                    bytes_read += len(chunk.encode("utf-8"))
                    buffer += chunk
                    blocks = buffer.replace("\r\n", "\n").split("\n\n")
                    buffer = blocks.pop() or ""
                    for block in blocks:
                        if not block.strip() or block.startswith(":"):
                            continue
                        event, payload = parse_sse_block(block)
                        payload_type = payload.get("type") if isinstance(payload, dict) else None
                        completed = completed or event == "response.completed" or payload_type == "response.completed"
                        if event == "error" or (isinstance(payload, dict) and payload.get("error")):
                            error = json.dumps(payload, ensure_ascii=False)[:1200]
    except TimeoutError:
        error = f"timeout after {timeout_s:.0f}s"
    except Exception as exc:
        error = repr(exc)
    if status_code == 200 and not completed and not error:
        error = "stream ended without response.completed"
    return Result(
        ok=status_code == 200 and completed and not error,
        status_code=status_code,
        total_ms=(time.perf_counter() - started) * 1000,
        first_event_ms=first_event_ms,
        bytes_read=bytes_read,
        completed=completed,
        error=error,
    )


def pct(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    return values[int((len(values) - 1) * q)]


def summarize(profile: dict[str, Any], url: str, concurrency: int, elapsed_s: float, results: list[Result]) -> dict[str, Any]:
    ok = [item for item in results if item.ok]
    total = [item.total_ms for item in ok]
    first = [item.first_event_ms for item in ok if item.first_event_ms is not None]
    errors: dict[str, int] = {}
    for item in results:
        if item.ok:
            continue
        key = (item.error or "unknown")[:400]
        errors[key] = errors.get(key, 0) + 1
    return {
        "service_id": profile["id"],
        "profile_name": profile["profile_name"],
        "configured_concurrent_limit": profile["concurrent_limit"],
        "url": url,
        "concurrency": concurrency,
        "requests": len(results),
        "success": len(ok),
        "failed": len(results) - len(ok),
        "elapsed_s": round(elapsed_s, 3),
        "rps": round(len(results) / elapsed_s, 3) if elapsed_s else None,
        "total_ms": {
            "avg": round(statistics.mean(total), 1) if total else None,
            "p50": round(pct(total, 0.50), 1) if total else None,
            "p95": round(pct(total, 0.95), 1) if total else None,
            "max": round(max(total), 1) if total else None,
        },
        "first_event_ms": {
            "avg": round(statistics.mean(first), 1) if first else None,
            "p50": round(pct(first, 0.50), 1) if first else None,
            "p95": round(pct(first, 0.95), 1) if first else None,
        },
        "errors": errors,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description="Stress test a single Codex official upstream profile directly.")
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB)
    parser.add_argument("--service-id", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=10)
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--model", default="")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--json-out", type=Path, default=ROOT / "backend_py" / "direct-codex-official-stress.json")
    args = parser.parse_args()

    profile = load_profile(args.db_path, args.service_id)
    url = endpoint(profile)
    model = args.model or profile.get("model") or "gpt-5.4-mini"
    semaphore = asyncio.Semaphore(args.concurrency)
    timeout = httpx.Timeout(connect=10, read=None, write=30, pool=None)
    limits = httpx.Limits(max_connections=max(args.concurrency * 2, 10), max_keepalive_connections=max(args.concurrency, 10))
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        async def one(index: int) -> Result:
            async with semaphore:
                body = request_body(model, f"{args.prompt} [direct={index}]", stream=True)
                return await call_once(client, url, profile, body, args.timeout)

        results = await asyncio.gather(*(one(i) for i in range(args.requests)))

    summary = summarize(profile, url, args.concurrency, time.perf_counter() - started, results)
    output = {"summary": summary, "results": [asdict(item) for item in results]}
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote={args.json_out}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
