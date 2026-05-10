"""ZIP helpers for SprintOS."""

from __future__ import annotations

import io
import zipfile
from typing import Callable, Iterable, Tuple


def build_zip_from_pairs(entries: Iterable[Tuple[str, str]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, content in entries:
            zf.writestr(name, content)
    return buffer.getvalue()


def build_zip_from_reader(names: Iterable[str], reader: Callable[[str], str]) -> bytes:
    return build_zip_from_pairs((name, reader(name)) for name in names)
