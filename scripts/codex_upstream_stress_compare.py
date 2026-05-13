from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import subprocess
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from test_codex_upstream import DEFAULT_DB, ensure_test_api_key, request_body


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_URL = "http://127.0.0.1:8085"
DEFAULT_EMAIL = "relay-codex-stress@local.test"
DEFAULT_PASSWORD = "relay-codex-stress-password"
DEFAULT_KEY_NAME = "codex-upstream-stress"
DEFAULT_MODEL = "gpt-5.4-mini"
DEFAULT_PROMPT = 'Reply with exactly this JSON: {"message":"codex stress ok"}'


@dataclass
class Result:
    ok: bool
    status_code: int | None
    total_ms: float
    first_event_ms: float | None
    bytes_read: int
    completed: bool
    response_created: bool
    error: str | None


def parse_csv_ints(value: str) -> list[int]:
    result: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if item:
            number = int(item)
            if number <= 0:
                raise argparse.ArgumentTypeError("values must be positive integers")
            result.append(number)
    if not result:
        raise argparse.ArgumentTypeError("at least one value is required")
    return result


def percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    index = int((len(values) - 1) * pct)
    return values[max(0, min(len(values) - 1, index))]


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


def start_server(port: int, workers: int, out_dir: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("CHAT_HISTORY_ENABLED", "false")
    env.setdefault("RELAY_PY_THREAD_TOKENS", "200")
    out_dir.mkdir(parents=True, exist_ok=True)
    log = (out_dir / f"codex-uvicorn-workers-{workers}.log").open("w", encoding="utf-8", errors="replace")
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
        str(workers),
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


async def call_once(client: httpx.AsyncClient, url: str, api_key: str, body: dict[str, Any], timeout_s: float) -> Result:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream",
        "Content-Type": "application/json",
        "Originator": "codex_cli_rs",
        "User-Agent": "codex_cli_rs/0.126.0 upstream-stress",
        "X-Client-Request-Id": str(uuid.uuid4()),
    }
    started = time.perf_counter()
    first_event_ms: float | None = None
    bytes_read = 0
    status_code: int | None = None
    response_created = False
    completed = False
    error: str | None = None
    buffer = ""
    try:
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
                        if not block.strip() or block.startswith(":"):
                            continue
                        event, payload = parse_sse_block(block)
                        payload_type = payload.get("type") if isinstance(payload, dict) else None
                        response_created = response_created or event == "response.created" or payload_type == "response.created"
                        completed = completed or event == "response.completed" or payload_type == "response.completed"
                        if event == "error" or (isinstance(payload, dict) and payload.get("error")):
                            error = json.dumps(payload, ensure_ascii=False)[:1200]
    except TimeoutError:
        error = f"timeout after {timeout_s:.0f}s"
    except Exception as exc:
        error = repr(exc)
    total_ms = (time.perf_counter() - started) * 1000
    ok = status_code == 200 and completed and not error
    if status_code and status_code >= 400 and not error:
        error = f"HTTP {status_code}"
    if status_code == 200 and not completed and not error:
        error = "stream ended without response.completed"
    return Result(ok, status_code, total_ms, first_event_ms, bytes_read, completed, response_created, error)


def summarize(workers: int, concurrency: int, elapsed_s: float, results: list[Result]) -> dict[str, Any]:
    ok = [item for item in results if item.ok]
    total_values = [item.total_ms for item in ok]
    first_values = [item.first_event_ms for item in ok if item.first_event_ms is not None]
    errors: dict[str, int] = {}
    for item in results:
        if item.ok:
            continue
        key = (item.error or "unknown")[:300]
        errors[key] = errors.get(key, 0) + 1
    return {
        "workers": workers,
        "concurrency": concurrency,
        "requests": len(results),
        "success": len(ok),
        "failed": len(results) - len(ok),
        "elapsed_s": round(elapsed_s, 3),
        "rps": round(len(results) / elapsed_s, 3) if elapsed_s else None,
        "total_ms": {
            "avg": round(statistics.mean(total_values), 1) if total_values else None,
            "p50": round(percentile(total_values, 0.50), 1) if total_values else None,
            "p95": round(percentile(total_values, 0.95), 1) if total_values else None,
            "max": round(max(total_values), 1) if total_values else None,
        },
        "first_event_ms": {
            "avg": round(statistics.mean(first_values), 1) if first_values else None,
            "p50": round(percentile(first_values, 0.50), 1) if first_values else None,
            "p95": round(percentile(first_values, 0.95), 1) if first_values else None,
        },
        "errors": errors,
    }


async def run_level(args: argparse.Namespace, api_key: str, workers: int, concurrency: int) -> tuple[dict[str, Any], list[Result]]:
    request_count = args.requests_per_level or max(concurrency * args.multiplier, concurrency)
    body = request_body(args.model, args.prompt, stream=True)
    url = f"{args.base_url.rstrip('/')}/v1/responses"
    limits = httpx.Limits(max_connections=max(concurrency * 2, 10), max_keepalive_connections=max(concurrency, 10))
    timeout = httpx.Timeout(connect=10, read=None, write=30, pool=None)
    semaphore = asyncio.Semaphore(concurrency)
    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        async def one(index: int) -> Result:
            async with semaphore:
                per_request_body = dict(body)
                per_request_body["input"] = [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": f"{args.prompt} [workers={workers}, concurrency={concurrency}, request={index}]",
                            }
                        ],
                    }
                ]
                return await call_once(client, url, api_key, per_request_body, args.timeout)

        results = await asyncio.gather(*(one(i) for i in range(request_count)))
    return summarize(workers, concurrency, time.perf_counter() - started, results), results


async def main() -> int:
    parser = argparse.ArgumentParser(description="Stress compare Relay Codex upstream proxy across worker and concurrency levels.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--port", type=int, default=8085)
    parser.add_argument("--workers", type=parse_csv_ints, default=parse_csv_ints("1,2"))
    parser.add_argument("--levels", type=parse_csv_ints, default=parse_csv_ints("1,2,4"))
    parser.add_argument("--requests-per-level", type=int, default=0)
    parser.add_argument("--multiplier", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--startup-timeout", type=float, default=45)
    parser.add_argument("--api-key", default=os.getenv("CODEX_STRESS_API_KEY", ""))
    parser.add_argument("--model", default=os.getenv("CODEX_STRESS_MODEL", DEFAULT_MODEL))
    parser.add_argument("--prompt", default=os.getenv("CODEX_STRESS_PROMPT", DEFAULT_PROMPT))
    parser.add_argument("--out-dir", type=Path, default=ROOT / "backend_py" / "codex-stress-results")
    args = parser.parse_args()

    api_key = args.api_key.strip() or ensure_test_api_key(DEFAULT_DB, DEFAULT_EMAIL, DEFAULT_PASSWORD, DEFAULT_KEY_NAME)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    all_summaries: list[dict[str, Any]] = []
    all_results: dict[str, list[dict[str, Any]]] = {}
    exit_code = 0

    for workers in args.workers:
        print(f"\n### workers={workers} port={args.port}", flush=True)
        proc = start_server(args.port, workers, args.out_dir)
        try:
            await wait_healthy(args.base_url, args.startup_timeout)
            for concurrency in args.levels:
                print(f"\n== workers={workers} concurrency={concurrency} ==", flush=True)
                summary, results = await run_level(args, api_key, workers, concurrency)
                all_summaries.append(summary)
                all_results[f"workers-{workers}-concurrency-{concurrency}"] = [asdict(item) for item in results]
                total = summary["total_ms"]
                first = summary["first_event_ms"]
                print(
                    "requests={requests} success={success} failed={failed} rps={rps} "
                    "total_avg_ms={avg} p50={p50} p95={p95} max={max} "
                    "first_avg_ms={first_avg} first_p95={first_p95}".format(
                        requests=summary["requests"],
                        success=summary["success"],
                        failed=summary["failed"],
                        rps=summary["rps"],
                        avg=total["avg"],
                        p50=total["p50"],
                        p95=total["p95"],
                        max=total["max"],
                        first_avg=first["avg"],
                        first_p95=first["p95"],
                    ),
                    flush=True,
                )
                for error, count in summary["errors"].items():
                    print(f"error x{count}: {error}", flush=True)
                if summary["failed"]:
                    exit_code = 1
        finally:
            stop_server(proc)
            await asyncio.sleep(2)

    output = {
        "target": args.base_url.rstrip("/"),
        "model": args.model,
        "workers": args.workers,
        "levels": args.levels,
        "summaries": all_summaries,
        "results": all_results,
    }
    out_file = args.out_dir / "codex-upstream-stress-compare.json"
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwrote={out_file}", flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
