from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import statistics
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:8085/api"
DEFAULT_EMAIL = "relay-stress@local.test"
DEFAULT_PASSWORD = "relay-stress-password"
DEFAULT_PROMPT = "请用一句话回答：压力测试健康检查。"


@dataclass
class RequestResult:
    ok: bool
    status_code: int | None
    total_ms: float
    first_event_ms: float | None
    bytes_read: int
    events: int
    error: str | None = None


def parse_levels(value: str) -> list[int]:
    levels = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        level = int(item)
        if level <= 0:
            raise argparse.ArgumentTypeError("concurrency levels must be positive")
        levels.append(level)
    if not levels:
        raise argparse.ArgumentTypeError("at least one concurrency level is required")
    return levels


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * pct)))
    return ordered[index]


def fmt_ms(value: float | None) -> str:
    return "-" if value is None else f"{value:.0f}"


def ensure_local_user(db_path: Path, email: str, password: str) -> None:
    if not db_path.exists():
        return
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            """
            insert into users(id, email, password_hash, registration_ip, balance, status, created_at)
            values (?, ?, ?, null, '999.000000', 'active', ?)
            on conflict(email) do update set
              password_hash = excluded.password_hash,
              balance = case
                when cast(users.balance as real) < 100 then '999.000000'
                else users.balance
              end,
              status = 'active'
            """,
            (str(uuid.uuid4()), email, password, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
        )
        con.commit()
    finally:
        con.close()


async def login(base_url: str, email: str, password: str) -> str:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(f"{base_url}/auth/login", json={"email": email, "password": password})
    if response.status_code >= 400:
        raise RuntimeError(f"login failed: HTTP {response.status_code} {response.text[:500]}")
    payload = response.json()
    token = (((payload or {}).get("data") or {}).get("token") or "").strip()
    if not token:
        raise RuntimeError(f"login response did not contain token: {response.text[:500]}")
    return token


def parse_sse_events(block: str) -> tuple[str, Any]:
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
    try:
        return event, json.loads(raw)
    except json.JSONDecodeError:
        return event, raw


async def run_one(
    client: httpx.AsyncClient,
    url: str,
    token: str,
    message: str,
    model: str | None,
    timeout_s: float,
) -> RequestResult:
    started = time.perf_counter()
    first_event_ms: float | None = None
    events = 0
    bytes_read = 0
    status_code: int | None = None
    buffer = ""
    body: dict[str, Any] = {"message": message, "newConversation": True, "images": []}
    if model:
        body["model"] = model
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

    try:
        async with asyncio.timeout(timeout_s):
            async with client.stream("POST", url, json=body, headers=headers) as response:
                status_code = response.status_code
                if response.status_code >= 400:
                    text = await response.aread()
                    return RequestResult(
                        ok=False,
                        status_code=status_code,
                        total_ms=(time.perf_counter() - started) * 1000,
                        first_event_ms=None,
                        bytes_read=len(text),
                        events=0,
                        error=f"HTTP {status_code}: {text[:500].decode('utf-8', 'replace')}",
                    )
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
                        event, data = parse_sse_events(block)
                        events += 1
                        if event == "error":
                            message = data.get("message") if isinstance(data, dict) else str(data)
                            return RequestResult(
                                ok=False,
                                status_code=status_code,
                                total_ms=(time.perf_counter() - started) * 1000,
                                first_event_ms=first_event_ms,
                                bytes_read=bytes_read,
                                events=events,
                                error=f"SSE error: {message}",
                            )
        return RequestResult(
            ok=True,
            status_code=status_code,
            total_ms=(time.perf_counter() - started) * 1000,
            first_event_ms=first_event_ms,
            bytes_read=bytes_read,
            events=events,
        )
    except TimeoutError:
        return RequestResult(
            ok=False,
            status_code=status_code,
            total_ms=(time.perf_counter() - started) * 1000,
            first_event_ms=first_event_ms,
            bytes_read=bytes_read,
            events=events,
            error=f"timeout after {timeout_s:.0f}s",
        )
    except Exception as exc:
        return RequestResult(
            ok=False,
            status_code=status_code,
            total_ms=(time.perf_counter() - started) * 1000,
            first_event_ms=first_event_ms,
            bytes_read=bytes_read,
            events=events,
            error=repr(exc),
        )


def summarize(level: int, results: list[RequestResult], elapsed_s: float) -> dict[str, Any]:
    ok_results = [item for item in results if item.ok]
    failed = [item for item in results if not item.ok]
    totals = [item.total_ms for item in ok_results]
    first_events = [item.first_event_ms for item in ok_results if item.first_event_ms is not None]
    errors: dict[str, int] = {}
    for item in failed:
        key = (item.error or "unknown")[:220]
        errors[key] = errors.get(key, 0) + 1
    return {
        "concurrency": level,
        "requests": len(results),
        "success": len(ok_results),
        "failed": len(failed),
        "elapsed_s": round(elapsed_s, 3),
        "rps": round(len(results) / elapsed_s, 3) if elapsed_s > 0 else None,
        "total_ms": {
            "avg": round(statistics.mean(totals), 1) if totals else None,
            "p50": round(percentile(totals, 0.50), 1) if totals else None,
            "p95": round(percentile(totals, 0.95), 1) if totals else None,
            "p99": round(percentile(totals, 0.99), 1) if totals else None,
            "max": round(max(totals), 1) if totals else None,
        },
        "first_event_ms": {
            "avg": round(statistics.mean(first_events), 1) if first_events else None,
            "p50": round(percentile(first_events, 0.50), 1) if first_events else None,
            "p95": round(percentile(first_events, 0.95), 1) if first_events else None,
        },
        "errors": errors,
    }


async def run_level(args: argparse.Namespace, token: str, level: int) -> tuple[dict[str, Any], list[RequestResult]]:
    requests = args.requests_per_level or max(level * args.multiplier, level)
    timeout = httpx.Timeout(connect=10, read=None, write=30, pool=None)
    limits = httpx.Limits(max_connections=max(level * 2, 10), max_keepalive_connections=max(level, 10))
    url = f"{args.base_url.rstrip('/')}/web-chat/messages/stream"
    started = time.perf_counter()
    sem = asyncio.Semaphore(level)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        async def task(index: int) -> RequestResult:
            async with sem:
                message = f"{args.prompt} [level={level}, request={index}, run={args.run_id}]"
                return await run_one(client, url, token, message, args.model, args.timeout)

        results = await asyncio.gather(*(task(i) for i in range(requests)))

    elapsed_s = time.perf_counter() - started
    return summarize(level, results, elapsed_s), results


async def main() -> int:
    parser = argparse.ArgumentParser(description="Stress test Relay web chat SSE endpoint.")
    parser.add_argument("--base-url", default=os.getenv("RELAY_STRESS_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--token", default=os.getenv("RELAY_STRESS_TOKEN", ""))
    parser.add_argument("--email", default=os.getenv("RELAY_STRESS_EMAIL", DEFAULT_EMAIL))
    parser.add_argument("--password", default=os.getenv("RELAY_STRESS_PASSWORD", DEFAULT_PASSWORD))
    parser.add_argument("--db-path", default=os.getenv("RELAY_STRESS_DB", "backend_py/relay_py.db"))
    parser.add_argument("--no-seed-user", action="store_true", help="do not seed the dedicated local SQLite user")
    parser.add_argument("--levels", type=parse_levels, default=parse_levels(os.getenv("RELAY_STRESS_LEVELS", "1,2,4")))
    parser.add_argument("--requests-per-level", type=int, default=int(os.getenv("RELAY_STRESS_REQUESTS", "0")))
    parser.add_argument("--multiplier", type=int, default=int(os.getenv("RELAY_STRESS_MULTIPLIER", "2")))
    parser.add_argument("--timeout", type=float, default=float(os.getenv("RELAY_STRESS_TIMEOUT", "180")))
    parser.add_argument("--prompt", default=os.getenv("RELAY_STRESS_PROMPT", DEFAULT_PROMPT))
    parser.add_argument("--model", default=os.getenv("RELAY_STRESS_MODEL", ""))
    parser.add_argument("--json-out", default=os.getenv("RELAY_STRESS_JSON_OUT", ""))
    args = parser.parse_args()
    args.model = args.model or None
    args.run_id = uuid.uuid4().hex[:8]

    token = args.token.strip()
    if not token:
        if not args.no_seed_user:
            ensure_local_user(Path(args.db_path), args.email, args.password)
        token = await login(args.base_url.rstrip("/"), args.email, args.password)

    print(f"target={args.base_url.rstrip('/')} levels={','.join(str(x) for x in args.levels)} run={args.run_id}")
    all_summaries: list[dict[str, Any]] = []
    all_results: dict[str, list[dict[str, Any]]] = {}
    for level in args.levels:
        print(f"\n== concurrency {level} ==")
        summary, results = await run_level(args, token, level)
        all_summaries.append(summary)
        all_results[str(level)] = [asdict(item) for item in results]
        total = summary["total_ms"]
        first = summary["first_event_ms"]
        print(
            "requests={requests} success={success} failed={failed} rps={rps} "
            "total_avg_ms={avg} p50={p50} p95={p95} p99={p99} max={max} "
            "first_avg_ms={first_avg} first_p95={first_p95}".format(
                requests=summary["requests"],
                success=summary["success"],
                failed=summary["failed"],
                rps=summary["rps"],
                avg=fmt_ms(total["avg"]),
                p50=fmt_ms(total["p50"]),
                p95=fmt_ms(total["p95"]),
                p99=fmt_ms(total["p99"]),
                max=fmt_ms(total["max"]),
                first_avg=fmt_ms(first["avg"]),
                first_p95=fmt_ms(first["p95"]),
            )
        )
        if summary["errors"]:
            for error, count in summary["errors"].items():
                print(f"error x{count}: {error}")

    if args.json_out:
        output = {"target": args.base_url.rstrip("/"), "runId": args.run_id, "summaries": all_summaries, "results": all_results}
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.json_out}")
    return 0 if all(item["failed"] == 0 for item in all_summaries) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
