#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


STATUS_URL = "http://127.0.0.1:8844/api/server_status"


def fetch_server_status() -> dict:
    request = urllib.request.Request(STATUS_URL, headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=2) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("ok") is not True or payload.get("app") != "SprintOS":
        raise RuntimeError("Local server responded, but it does not look like SprintOS.")
    return payload


def main() -> int:
    try:
        status = fetch_server_status()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        print("SprintOS does not appear to be running at http://127.0.0.1:8844.")
        print("Start it with `python3 scripts/launch.py` or `python3 sprintos.py`.")
        return 1
    except Exception as exc:
        print(f"Could not read SprintOS status: {exc}")
        return 1

    print("SprintOS is running.")
    print(f"App URL: {status.get('url') or 'http://127.0.0.1:8844'}")
    print(f"PID: {status.get('pid') or 'unknown'}")
    print(f"Started at: {status.get('started_at') or 'unknown'}")
    print(f"Uptime seconds: {status.get('uptime_seconds') or 0}")
    print(f"Data: {status.get('data_dir') or 'data'}")
    print(f"Exports: {status.get('exports_dir') or 'exports'}")
    print(f"Workspaces: {status.get('workspaces_dir') or 'workspaces'}")
    print(f"Backups: {status.get('backups_dir') or 'backups'}")
    print("To stop SprintOS, press Ctrl+C in the terminal running SprintOS.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
