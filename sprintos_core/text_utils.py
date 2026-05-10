"""Text helpers for SprintOS."""

from __future__ import annotations

import re
from pathlib import Path


def slugify(value: str, default: str = "idea") -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or default


def sanitize_filename(name: str, default_stem: str = "artifact", default_suffix: str = ".md") -> str:
    raw = str(name or "").strip().replace("\\", "/").split("/")[-1]
    path = Path(raw)
    suffix = path.suffix.lower()
    stem = path.stem if suffix else raw
    if not re.fullmatch(r"\.[a-z0-9]{1,10}", suffix):
        suffix = default_suffix
        stem = raw
    return f"{slugify(stem, default_stem)}{suffix or default_suffix}"


def unique_filename(filename: str, used: set[str]) -> str:
    path = Path(filename)
    stem = path.stem
    suffix = path.suffix
    candidate = filename
    counter = 2
    while candidate in used:
        candidate = f"{stem}-{counter}{suffix}"
        counter += 1
    used.add(candidate)
    return candidate


def first_sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    return text.rstrip(".") + "."
