#!/usr/bin/env python3
"""Fail when unsafe local/runtime files are tracked or staged."""

from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


MAX_SCAN_BYTES = 5 * 1024 * 1024

BLOCKED_RUNTIME_PARTS = {
    ".cache",
    ".mypy_cache",
    ".next",
    ".nuxt",
    ".parcel-cache",
    ".playwright-cli",
    ".pytest_cache",
    ".ruff_cache",
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
    ("OpenAI-style API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b")),
    ("DeepSeek API key assignment", re.compile(r"\bDEEPSEEK_API_KEY\s*=\s*[\"']?[A-Za-z0-9_-]{20,}", re.IGNORECASE)),
    ("Authorization bearer token", re.compile(r"\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._-]{20,}", re.IGNORECASE)),
    ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{30,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
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


def main() -> int:
    repo_root = find_repo_root()
    tracked_files = git_list(repo_root, ["ls-files", "-z"])
    staged_files = git_list(repo_root, ["diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"])
    staged_set = set(staged_files)
    files_to_check = sorted(set(tracked_files) | staged_set)
    findings: dict[str, list[str]] = defaultdict(list)

    for rel_file in files_to_check:
        path = Path(rel_file)
        parts = path.parts
        name = path.name

        if is_env_file(name):
            findings["Tracked/staged env files are blocked"].append(rel_file)
            continue
        if any(part in BLOCKED_RUNTIME_PARTS for part in parts):
            findings["Tracked/staged runtime folders are blocked"].append(rel_file)
            continue
        if any(pattern.search(rel_file) for pattern in RAW_PROMPT_OR_PAYLOAD_PATTERNS):
            findings["Tracked/staged raw prompt or provider payload files are blocked"].append(rel_file)
            continue
        if name.endswith((".pyc", ".pyo", ".log", ".sqlite", ".sqlite-shm", ".sqlite-wal", ".sqlite-journal")):
            findings["Tracked/staged local runtime files are blocked"].append(rel_file)
            continue

        content = read_candidate(repo_root, rel_file, prefer_staged=rel_file in staged_set)
        if not content:
            continue
        for label, pattern in SECRET_PATTERNS:
            if has_non_placeholder_secret(pattern, content):
                findings["Obvious secret patterns found"].append(f"{rel_file} ({label})")
                break

    if findings:
        print("Safety check failed.", file=sys.stderr)
        for title in sorted(findings):
            print(f"{title}:", file=sys.stderr)
            for item in findings[title][:30]:
                print(f"- {item}", file=sys.stderr)
            if len(findings[title]) > 30:
                print(f"- ...and {len(findings[title]) - 30} more", file=sys.stderr)
        print("No secret values were printed. Remove these files from git tracking or replace real keys with safe placeholders.", file=sys.stderr)
        return 1

    print(f"Safety check passed. Checked {len(files_to_check)} tracked/staged file(s); no blocked env files, runtime folders, raw prompts, provider payloads, or obvious secrets found.")
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


def git_list(repo_root: Path, args: list[str]) -> list[str]:
    try:
        output = subprocess.check_output(["git", *args], cwd=repo_root)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [item for item in output.decode("utf-8", errors="replace").split("\0") if item]


def is_env_file(name: str) -> bool:
    return name == ".env" or name.startswith(".env.")


def read_candidate(repo_root: Path, rel_file: str, prefer_staged: bool) -> str:
    if prefer_staged:
        try:
            data = subprocess.check_output(
                ["git", "show", f":{rel_file}"],
                cwd=repo_root,
                stderr=subprocess.DEVNULL,
                timeout=5,
            )
            return decode_text(data)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            return ""

    try:
        data = (repo_root / rel_file).read_bytes()
    except OSError:
        return ""
    return decode_text(data)


def decode_text(data: bytes) -> str:
    if len(data) > MAX_SCAN_BYTES or b"\x00" in data[:8000]:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def has_non_placeholder_secret(pattern: re.Pattern[str], content: str) -> bool:
    for match in pattern.finditer(content):
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


if __name__ == "__main__":
    raise SystemExit(main())
