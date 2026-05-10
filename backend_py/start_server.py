from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = ROOT / "backend_py"
OUT_LOG = LOG_DIR / "uvicorn.out.log"
ERR_LOG = LOG_DIR / "uvicorn.err.log"
HEALTH_URL = "http://127.0.0.1:8081/api/health"


def health_ok() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=0.8) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def tail(path: Path, lines: int = 30) -> str:
    if not path.exists():
        return ""
    try:
        return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])
    except OSError:
        return ""


def main() -> None:
    if health_ok():
        print("backend already running: http://127.0.0.1:8081")
        return

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
        creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)

    out = OUT_LOG.open("ab")
    err = ERR_LOG.open("ab")
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend_py.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8081",
        ],
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=out,
        stderr=err,
        creationflags=creationflags,
        close_fds=False,
    )
    out.close()
    err.close()

    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if process.poll() is not None:
            print(f"backend failed to start, exit code: {process.returncode}")
            recent_err = tail(ERR_LOG)
            recent_out = tail(OUT_LOG)
            if recent_err:
                print("\n--- uvicorn.err.log ---")
                print(recent_err)
            if recent_out:
                print("\n--- uvicorn.out.log ---")
                print(recent_out)
            sys.exit(process.returncode or 1)
        if health_ok():
            print(f"backend started: pid={process.pid} url=http://127.0.0.1:8081")
            return
        time.sleep(0.4)

    print(f"backend process started but health check did not pass yet: pid={process.pid}")
    print(f"logs: {OUT_LOG} / {ERR_LOG}")
    sys.exit(1)


if __name__ == "__main__":
    main()
