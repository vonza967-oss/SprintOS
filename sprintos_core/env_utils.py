from __future__ import annotations

import os
from pathlib import Path


def load_local_env(root: Path | str | None = None) -> Path | None:
    base = Path(root) if root is not None else Path.cwd()
    env_path = base / ".env"
    if not env_path.exists() or not env_path.is_file():
        return None

    preexisting_keys = set(os.environ.keys())
    parsed: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        parsed[key] = value.strip()
    for key, value in parsed.items():
        if key in preexisting_keys:
            continue
        os.environ[key] = value
    return env_path
