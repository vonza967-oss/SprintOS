"""Report-folder helpers for SprintOS."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .text_utils import slugify


def create_report_dir(root: Path, project_title: str, scope: str, stamp: str) -> Path:
    base_name = f"{slugify(project_title, 'project')}-{scope.replace('_', '-')}-{stamp}"
    report_dir = Path(root) / base_name
    counter = 2
    while report_dir.exists():
        report_dir = Path(root) / f"{base_name}-{counter}"
        counter += 1
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def write_text_files(report_dir: Path, file_contents: Mapping[str, str]) -> Path:
    for name, content in file_contents.items():
        (report_dir / name).write_text(content, encoding="utf-8")
    return report_dir
