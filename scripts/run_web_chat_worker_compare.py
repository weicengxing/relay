from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]


def parse_csv_ints(value: str) -> list[int]:
    items: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        number = int(part)
        if number <= 0:
            raise argparse.ArgumentTypeError("values must be positive integers")
        items.append(number)
    if not items:
        raise argparse.ArgumentTypeError("at least one value is required")
    return items


def wait_health(base_url: str, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    last_error = ""
    with httpx.Client(timeout=3) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get(f"{base_url.rstrip('/')}/health")
                if response.status_code == 200:
                    return
                last_error = f"HTTP {response.status_code}: {response.text[:200]}"
            except Exception as exc:
                last_error = repr(exc)
            time.sleep(0.5)
    raise RuntimeError(f"server did not become healthy within {timeout_s:.0f}s: {last_error}")


def start_server(port: int, workers: int, log_file: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env.setdefault("CHAT_HISTORY_ENABLED", "false")
    env.setdefault("RELAY_PY_THREAD_TOKENS", "200")
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
        str(workers),
    ]
    return subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)


def stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def run_stress(args: argparse.Namespace, workers: int) -> int:
    json_out = args.out_dir / f"web-chat-stress-workers-{workers}.json"
    command = [
        sys.executable,
        "scripts/web_chat_stress.py",
        "--base-url",
        f"http://127.0.0.1:{args.port}/api",
        "--levels",
        ",".join(str(level) for level in args.levels),
        "--multiplier",
        str(args.multiplier),
        "--timeout",
        str(args.request_timeout),
        "--json-out",
        str(json_out),
    ]
    if args.requests_per_level:
        command.extend(["--requests-per-level", str(args.requests_per_level)])
    if args.prompt:
        command.extend(["--prompt", args.prompt])
    if args.model:
        command.extend(["--model", args.model])
    print(" ".join(command), flush=True)
    completed = subprocess.run(command, cwd=ROOT, text=True)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Relay web chat stress results across uvicorn worker counts.")
    parser.add_argument("--port", type=int, default=8085)
    parser.add_argument("--workers", type=parse_csv_ints, default=parse_csv_ints("1,2"))
    parser.add_argument("--levels", type=parse_csv_ints, default=parse_csv_ints("1,2,4"))
    parser.add_argument("--requests-per-level", type=int, default=0)
    parser.add_argument("--multiplier", type=int, default=2)
    parser.add_argument("--startup-timeout", type=float, default=45)
    parser.add_argument("--request-timeout", type=float, default=180)
    parser.add_argument("--prompt", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "backend_py" / "stress-results")
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    exit_code = 0
    for workers in args.workers:
        log_file = args.out_dir / f"uvicorn-workers-{workers}.log"
        print(f"\n### workers={workers} port={args.port}", flush=True)
        proc = start_server(args.port, workers, log_file)
        try:
            wait_health(f"http://127.0.0.1:{args.port}/api", args.startup_timeout)
            print(f"server healthy pid={proc.pid} log={log_file}", flush=True)
            code = run_stress(args, workers)
            exit_code = exit_code or code
        except Exception as exc:
            exit_code = exit_code or 1
            print(f"worker run failed: {exc}", flush=True)
            if log_file.exists():
                print(log_file.read_text(encoding="utf-8", errors="replace")[-4000:], flush=True)
        finally:
            stop_server(proc)
            time.sleep(2)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
