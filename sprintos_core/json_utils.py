"""JSON helpers for SprintOS."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def safe_json_loads(raw: str, fallback: Any = None) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def read_json_file(path: Path, fallback: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def write_json_file(path: Path, data: Any, *, indent: int = 2, newline: bool = False) -> None:
    text = json.dumps(data, indent=indent)
    if newline:
        text += "\n"
    path.write_text(text, encoding="utf-8")
