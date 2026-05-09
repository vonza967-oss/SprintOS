#!/usr/bin/env python3

from __future__ import annotations

import py_compile
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPORT_DIR = ROOT / "exports"
SOURCE_SUFFIXES = {".py", ".md", ".json", ".toml", ".yaml", ".yml", ".txt", ".sh"}
SK_PREFIX = "sk" + "-"
SECRET_PATTERNS = (
    "OPENAI_API_KEY=" + SK_PREFIX,
    "DEEPSEEK_API_KEY=" + SK_PREFIX,
    "Bearer " + SK_PREFIX,
    SK_PREFIX + "proj-",
)
AUTH_LITERAL_PATTERN = re.compile(r"Authorization:\s*Bearer\s+sk-[A-Za-z0-9_-]+")
OPENAI_KEY_LITERAL_PATTERN = re.compile(r'OPENAI_API_KEY\s*[:=]\s*["\']?sk-[A-Za-z0-9_-]+')
DEEPSEEK_KEY_LITERAL_PATTERN = re.compile(r'DEEPSEEK_API_KEY\s*[:=]\s*["\']?sk-[A-Za-z0-9_-]+')
REQUIRED_DOCS = (
    ROOT / "AGENTS.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "CODEX_TASKS.md",
    ROOT / "docs" / "CODE_REVIEW.md",
)
REQUIRED_MAIN_FILES = (
    ROOT / "sprintos.py",
    ROOT / "tests" / "test_sprintos.py",
    ROOT / "scripts" / "smoke.py",
    ROOT / ".env.example",
    ROOT / ".gitignore",
)
REQUIRED_EXPORT_DIRS = (
    EXPORT_DIR / "prototypes",
    EXPORT_DIR / "deploy_packs",
    EXPORT_DIR / "build_packs",
    EXPORT_DIR / "workspace_snapshots",
    EXPORT_DIR / "workspace_restores",
    EXPORT_DIR / "workspace_syncs",
    EXPORT_DIR / "pipeline_runs",
    EXPORT_DIR / "quick_launches",
    EXPORT_DIR / "verification_runs",
)


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    return "__pycache__" in parts or "exports" in parts or "data" in parts


def python_files() -> list[Path]:
    return sorted(path for path in ROOT.rglob("*.py") if not should_skip(path))


def source_like_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or should_skip(path):
            continue
        if path.suffix.lower() in SOURCE_SUFFIXES:
            files.append(path)
    return sorted(files)


def compile_python_files() -> list[str]:
    failures: list[str] = []
    for path in python_files():
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            failures.append(f"{path.relative_to(ROOT)}: {exc.msg}")
    return failures


def scan_for_secrets() -> list[str]:
    findings: list[str] = []
    for path in source_like_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern in text:
                findings.append(f"{path.relative_to(ROOT)} contains `{pattern}`")
        if OPENAI_KEY_LITERAL_PATTERN.search(text):
            findings.append(f"{path.relative_to(ROOT)} contains a literal OPENAI_API_KEY value")
        if DEEPSEEK_KEY_LITERAL_PATTERN.search(text):
            findings.append(f"{path.relative_to(ROOT)} contains a literal DEEPSEEK_API_KEY value")
        if AUTH_LITERAL_PATTERN.search(text):
            findings.append(f"{path.relative_to(ROOT)} contains a literal Authorization bearer token")
    return findings


def scan_exports_for_secrets() -> list[str]:
    findings: list[str] = []
    if not EXPORT_DIR.exists():
        return findings
    for path in sorted(EXPORT_DIR.rglob("*")):
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern in text:
                findings.append(f"{path.relative_to(ROOT)} contains `{pattern}`")
        if OPENAI_KEY_LITERAL_PATTERN.search(text):
            findings.append(f"{path.relative_to(ROOT)} contains a literal OPENAI_API_KEY value")
        if DEEPSEEK_KEY_LITERAL_PATTERN.search(text):
            findings.append(f"{path.relative_to(ROOT)} contains a literal DEEPSEEK_API_KEY value")
        if AUTH_LITERAL_PATTERN.search(text):
            findings.append(f"{path.relative_to(ROOT)} contains a literal Authorization bearer token")
    return findings


def main() -> int:
    failures: list[str] = []

    for path in REQUIRED_DOCS + REQUIRED_MAIN_FILES:
        if not path.exists():
            failures.append(f"Missing required file: {path.relative_to(ROOT)}")

    gitignore_path = ROOT / ".gitignore"
    if gitignore_path.exists():
        try:
            gitignore_lines = {line.strip() for line in gitignore_path.read_text(encoding="utf-8").splitlines()}
        except UnicodeDecodeError:
            gitignore_lines = set()
        if ".env" not in gitignore_lines:
            failures.append(".gitignore must include `.env`")

    for path in REQUIRED_EXPORT_DIRS:
        path.mkdir(parents=True, exist_ok=True)
        if not path.exists() or not path.is_dir():
            failures.append(f"Could not create export directory: {path.relative_to(ROOT)}")

    failures.extend(compile_python_files())
    failures.extend(scan_for_secrets())
    failures.extend(scan_exports_for_secrets())

    if failures:
        print("health check failed")
        for item in failures:
            print(f"- {item}")
        return 1

    print("health ok")
    print(f"- docs checked: {len(REQUIRED_DOCS)}")
    print(f"- main files checked: {len(REQUIRED_MAIN_FILES)}")
    print(f"- python files compiled: {len(python_files())}")
    print(f"- export directories ensured: {len(REQUIRED_EXPORT_DIRS)}")
    print("- .env remains optional and untracked by default")
    print("- secret scan: no obvious API keys found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
