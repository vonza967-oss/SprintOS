#!/usr/bin/env python3
"""Create a local source backup without runtime state or secrets."""

from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import tarfile
from dataclasses import dataclass
from pathlib import Path


MAX_SCAN_BYTES = 5 * 1024 * 1024


BLOCKED_DIRS = {
    ".cache",
    ".git",
    ".hg",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".parcel-cache",
    ".playwright-cli",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".turbo",
    ".venv",
    "__pycache__",
    "backups",
    "build",
    "coverage",
    "dist",
    "env",
    "exports",
    "htmlcov",
    "local_backups",
    "node_modules",
    "out",
    "tmp",
    "venv",
    "workspaces",
}

BLOCKED_FILE_SUFFIXES = {
    ".log",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite-journal",
    ".sqlite-shm",
    ".sqlite-wal",
}

BLOCKED_FILE_NAMES = {
    ".DS_Store",
}

RAW_PROMPT_OR_PAYLOAD_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"provider[-_ ]?payload",
        r"provider[-_ ]?response",
        r"provider[-_ ]?request",
        r"provider[-_ ]?prompt",
        r"raw[-_ ]?provider",
        r"raw[-_ ]?prompt",
        r"raw[-_ ]?response",
        r"prompt[-_ ]?payload",
        r"prompt[-_ ]?log",
        r"payload[-_ ]?log",
        r"ai[-_ ]?payload",
        r"llm[-_ ]?payload",
    )
]

SECRET_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b",
        r"\bDEEPSEEK_API_KEY\s*=\s*[\"']?[A-Za-z0-9_-]{20,}",
        r"\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._-]{20,}",
        r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b",
        r"\bgithub_pat_[A-Za-z0-9_]{30,}\b",
        r"\bAKIA[0-9A-Z]{16}\b",
        r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b",
    )
]

SAFE_PLACEHOLDER_MARKERS = {
    "example",
    "fake",
    "local-only",
    "placeholder",
    "test",
    "your_",
}

SAFE_PLACEHOLDER_PREFIXES = (
    "sk-deepseek-",
    "sk-live-",
    "sk-openai-",
    "sk-prototype-",
    "sk-release-",
    "sk-route-",
)


@dataclass
class OmissionCounts:
    env_files: int = 0
    git_internals: int = 0
    runtime_exports: int = 0
    local_caches: int = 0
    local_state: int = 0
    backup_recursion: int = 0
    raw_prompts_or_payloads: int = 0
    secret_matches: int = 0
    local_noise: int = 0
    symlinks: int = 0


def main() -> int:
    repo_root = find_repo_root()
    backup_dir = repo_root / "local_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    archive_name = f"sprintos-local-backup-{timestamp()}.tar.gz"
    archive_path = backup_dir / archive_name
    counts = OmissionCounts()
    included_files = 0

    with tarfile.open(archive_path, "w:gz") as archive:
        for path in sorted(repo_root.rglob("*")):
            rel_path = path.relative_to(repo_root)
            rel_posix = rel_path.as_posix()
            reason = exclusion_reason(path, rel_path)
            if reason:
                increment(counts, reason)
                if path.is_dir():
                    continue
                continue
            if path.is_symlink():
                counts.symlinks += 1
                continue
            if path.is_dir():
                continue
            if path.is_file() and file_contains_secret(path):
                counts.secret_matches += 1
                continue
            add_file(archive, path, rel_posix)
            included_files += 1

    verify_archive(archive_path)
    archive_size = archive_path.stat().st_size

    print(f"Backup created: {archive_path.relative_to(repo_root)}")
    print(f"Archive size: {format_bytes(archive_size)}")
    print(f"Included files: {included_files}")
    print("Omitted files/folders:")
    print(f"- env files: {counts.env_files}")
    print(f"- git internals: {counts.git_internals}")
    print(f"- runtime exports/workspaces: {counts.runtime_exports}")
    print(f"- local caches/dependencies: {counts.local_caches}")
    print(f"- local SQLite/runtime state: {counts.local_state}")
    print(f"- backup recursion: {counts.backup_recursion}")
    print(f"- raw prompts/provider payloads: {counts.raw_prompts_or_payloads}")
    print(f"- files with obvious secret patterns: {counts.secret_matches}")
    print(f"- local noise/symlinks: {counts.local_noise + counts.symlinks}")
    print("Verification passed: archive entries contain no blocked env files, git internals, caches, runtime exports, raw prompts, provider payloads, local backups, or obvious secret paths.")
    return 0


def find_repo_root() -> Path:
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
        if output:
            return Path(output).resolve()
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return Path.cwd().resolve()


def timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def exclusion_reason(path: Path, rel_path: Path) -> str | None:
    parts = rel_path.parts
    name = path.name
    rel_posix = rel_path.as_posix()

    if is_env_file(name):
        return "env_files"
    if ".git" in parts:
        return "git_internals"
    if any(part in {"exports", "workspaces"} for part in parts):
        return "runtime_exports"
    if any(part in {"local_backups", "backups"} for part in parts):
        return "backup_recursion"
    if any(part in BLOCKED_DIRS for part in parts):
        return "local_caches"
    if parts and parts[0] == "data" and path.is_file():
        return "local_state"
    if any(pattern.search(rel_posix) for pattern in RAW_PROMPT_OR_PAYLOAD_PATTERNS):
        return "raw_prompts_or_payloads"
    if name in BLOCKED_FILE_NAMES or any(name.endswith(suffix) for suffix in BLOCKED_FILE_SUFFIXES):
        return "local_noise"
    return None


def is_env_file(name: str) -> bool:
    return name == ".env" or name.startswith(".env.")


def file_contains_secret(path: Path) -> bool:
    try:
        if path.stat().st_size > MAX_SCAN_BYTES:
            return False
        data = path.read_bytes()
    except OSError:
        return False
    if b"\x00" in data[:8000]:
        return False
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(text):
            if not is_safe_placeholder_match(match.group(0)):
                return True
    return False


def is_safe_placeholder_match(value: str) -> bool:
    normalized = value.lower()
    if any(marker in normalized for marker in SAFE_PLACEHOLDER_MARKERS):
        return True
    token_match = re.search(r"sk-[a-z0-9_-]+", normalized)
    if token_match and token_match.group(0).startswith(SAFE_PLACEHOLDER_PREFIXES):
        return True
    return False


def add_file(archive: tarfile.TarFile, path: Path, rel_posix: str) -> None:
    info = archive.gettarinfo(str(path), arcname=rel_posix)
    info.uid = 0
    info.gid = 0
    info.uname = "sprintos"
    info.gname = "sprintos"
    with path.open("rb") as handle:
        archive.addfile(info, handle)


def verify_archive(archive_path: Path) -> None:
    violations: list[str] = []
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            member_path = Path(member.name)
            parts = member_path.parts
            name = member_path.name
            if member.name.startswith("/") or ".." in parts:
                violations.append(member.name)
            if is_env_file(name):
                violations.append(member.name)
            if ".git" in parts:
                violations.append(member.name)
            if any(part in {"exports", "workspaces", "local_backups", "backups"} for part in parts):
                violations.append(member.name)
            if any(part in BLOCKED_DIRS for part in parts):
                violations.append(member.name)
            if any(pattern.search(member.name) for pattern in RAW_PROMPT_OR_PAYLOAD_PATTERNS):
                violations.append(member.name)
    if violations:
        sample = ", ".join(violations[:10])
        raise RuntimeError(f"Backup verification failed; blocked entries were included: {sample}")


def increment(counts: OmissionCounts, field: str) -> None:
    setattr(counts, field, getattr(counts, field) + 1)


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


if __name__ == "__main__":
    raise SystemExit(main())
