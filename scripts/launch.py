#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any, Optional


APP_URL = "http://127.0.0.1:8844"
HEALTH_URL = APP_URL + "/api/health"
STATUS_URL = APP_URL + "/api/server_status"
MIN_PYTHON = (3, 9)
STARTUP_TIMEOUT_SECONDS = 20.0
HEALTH_POLL_INTERVAL_SECONDS = 0.25


def locate_repo_root(start: Optional[Path] = None) -> Path:
    candidates = [start or Path.cwd(), Path(__file__).resolve().parents[1]]
    seen: set[Path] = set()
    for candidate in candidates:
        for root in [candidate, *candidate.parents]:
            if root in seen:
                continue
            seen.add(root)
            if (root / "sprintos.py").exists() and (root / "scripts" / "launch.py").exists():
                return root
    raise RuntimeError("Could not locate the SprintOS repo root.")


def ensure_python_version() -> None:
    if sys.version_info < MIN_PYTHON:
        version = ".".join(str(part) for part in MIN_PYTHON)
        raise RuntimeError(f"SprintOS launcher requires Python {version}+.")


def fetch_json(url: str, timeout: float = 2.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_server_status(timeout: float = 2.0) -> Optional[dict[str, Any]]:
    try:
        payload = fetch_json(STATUS_URL, timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None
    if payload.get("ok") is True and payload.get("app") == "SprintOS":
        return payload
    return None


def is_server_healthy(timeout: float = 2.0) -> bool:
    try:
        payload = fetch_json(HEALTH_URL, timeout=timeout)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return False
    return payload.get("ok") is True and payload.get("app") == "SprintOS"


def wait_for_server(process: subprocess.Popen[bytes], timeout_seconds: float = STARTUP_TIMEOUT_SECONDS) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error = "Timed out waiting for SprintOS to respond."
    while time.monotonic() < deadline:
        if is_server_healthy(timeout=1.0):
            return fetch_server_status(timeout=1.0) or {"ok": True, "app": "SprintOS", "url": APP_URL}
        if process.poll() is not None:
            raise RuntimeError(f"SprintOS exited before becoming healthy (exit code {process.returncode}).")
        time.sleep(HEALTH_POLL_INTERVAL_SECONDS)
    raise RuntimeError(last_error)


def open_browser(url: str) -> None:
    try:
        webbrowser.open(url)
    except Exception as exc:
        print(f"Warning: could not open the browser automatically: {exc}")


def print_runtime_status(status: dict[str, Any], *, already_running: bool) -> None:
    repo_root = locate_repo_root()
    print("SprintOS is already running." if already_running else "SprintOS is running.")
    print(f"App URL: {status.get('url') or APP_URL}")
    print(f"PID: {status.get('pid') or 'unknown'}")
    print("Stop: press Ctrl+C in the terminal running SprintOS, or run `python3 scripts/stop.py` for status/help.")
    print(f"Data: {status.get('data_dir') or str(repo_root / 'data')}")
    print(f"Exports: {status.get('exports_dir') or str(repo_root / 'exports')}")
    print(f"Workspaces: {status.get('workspaces_dir') or str(repo_root / 'workspaces')}")
    print(f"Backups: {status.get('backups_dir') or str(repo_root / 'backups')}")


def start_server(repo_root: Path) -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["SPRINTOS_NO_BROWSER"] = "1"
    argv = [sys.executable, str(repo_root / "sprintos.py")]
    return subprocess.Popen(argv, cwd=str(repo_root), env=env)


def run_launcher() -> int:
    ensure_python_version()
    repo_root = locate_repo_root()
    os.chdir(repo_root)

    if is_server_healthy(timeout=1.5):
        status = fetch_server_status(timeout=1.5) or {"ok": True, "app": "SprintOS", "url": APP_URL}
        open_browser(str(status.get("url") or APP_URL))
        print_runtime_status(status, already_running=True)
        return 0

    print("Starting SprintOS...")
    process = start_server(repo_root)
    try:
        status = wait_for_server(process)
    except Exception as exc:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        print(f"Failed to start SprintOS: {exc}")
        return 1

    open_browser(str(status.get("url") or APP_URL))
    print_runtime_status(status, already_running=False)

    try:
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping SprintOS launcher.")
        try:
            return process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            return 0


def main() -> int:
    try:
        return run_launcher()
    except Exception as exc:
        print(f"Launcher error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
