"""Path-safety helpers for SprintOS."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


def export_relative_path(path: Path, start: Path) -> str:
    try:
        return Path(os.path.relpath(path, start=start)).as_posix()
    except Exception:
        return path.name


def safe_flat_file_path(base: Path, filename: str, allowed: Iterable[str], error_message: str) -> Path:
    candidate = str(filename or "").strip()
    if not candidate or candidate != Path(candidate).name or candidate not in set(allowed):
        raise ValueError(error_message)
    resolved_base = Path(base).resolve()
    target = (resolved_base / candidate).resolve()
    if target.parent != resolved_base or not target.exists() or target.is_dir():
        raise ValueError(error_message)
    return target


def safe_relative_file_path(base: Path, relative_file_path: str, allowed: Iterable[str], error_message: str) -> Path:
    candidate = Path(str(relative_file_path or "").strip())
    normalized = candidate.as_posix()
    if not normalized or candidate.is_absolute() or ".." in candidate.parts or normalized not in set(allowed):
        raise ValueError(error_message)
    resolved_base = Path(base).resolve()
    target = (resolved_base / normalized).resolve()
    if not target.exists() or target.is_dir():
        raise ValueError(error_message)
    try:
        target.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(error_message) from exc
    return target


def safe_file_exists(base: Path, relative_path: str) -> bool:
    candidate = (Path(base).resolve() / relative_path).resolve()
    try:
        candidate.relative_to(Path(base).resolve())
    except ValueError:
        return False
    return candidate.exists() and candidate.is_file()


def safe_read_text(base: Path, relative_path: str, error_message: str) -> str:
    target = (Path(base).resolve() / relative_path).resolve()
    try:
        target.relative_to(Path(base).resolve())
    except ValueError as exc:
        raise ValueError(error_message) from exc
    return target.read_text(encoding="utf-8")
