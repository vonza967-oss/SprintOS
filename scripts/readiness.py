#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, List


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sprintos
from sprintos_core.ai_provider import DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_OPENAI_MODEL


RAW_IDEA = "I want a simple app where users paste study notes and get flashcards."


@contextmanager
def isolated_runtime() -> Iterator[Path]:
    tmpdir = tempfile.TemporaryDirectory()
    root = Path(tmpdir.name)
    original_paths = (
        sprintos.DATA_DIR,
        sprintos.EXPORT_DIR,
        sprintos.WORKFLOW_DIR,
        sprintos.DB_PATH,
        sprintos.WORKSPACE_DIR,
        sprintos.BACKUP_DIR,
    )
    original_env = {
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY"),
        "DEEPSEEK_BASE_URL": os.environ.get("DEEPSEEK_BASE_URL"),
        "SPRINTOS_AI_PROVIDER": os.environ.get("SPRINTOS_AI_PROVIDER"),
        "SPRINTOS_AI_ENABLED": os.environ.get("SPRINTOS_AI_ENABLED"),
        "SPRINTOS_MODEL": os.environ.get("SPRINTOS_MODEL"),
        "SPRINTOS_AI_TIMEOUT_SECONDS": os.environ.get("SPRINTOS_AI_TIMEOUT_SECONDS"),
        "SPRINTOS_AI_MAX_OUTPUT_TOKENS": os.environ.get("SPRINTOS_AI_MAX_OUTPUT_TOKENS"),
    }
    try:
        sprintos.DATA_DIR = root / "data"
        sprintos.EXPORT_DIR = root / "exports"
        sprintos.WORKFLOW_DIR = root / "workflows"
        sprintos.DB_PATH = sprintos.DATA_DIR / "sprintos.sqlite"
        sprintos.WORKSPACE_DIR = root / "workspaces"
        sprintos.BACKUP_DIR = root / "backups"
        os.environ["OPENAI_API_KEY"] = ""
        os.environ["DEEPSEEK_API_KEY"] = ""
        os.environ["DEEPSEEK_BASE_URL"] = DEFAULT_DEEPSEEK_BASE_URL
        os.environ["SPRINTOS_AI_PROVIDER"] = "offline"
        os.environ["SPRINTOS_AI_ENABLED"] = "false"
        os.environ["SPRINTOS_MODEL"] = DEFAULT_OPENAI_MODEL
        os.environ["SPRINTOS_AI_TIMEOUT_SECONDS"] = "20"
        os.environ["SPRINTOS_AI_MAX_OUTPUT_TOKENS"] = "2000"
        sprintos.ensure_dirs()
        sprintos.write_default_workflows()
        sprintos.init_db()
        yield root
    finally:
        sprintos.DATA_DIR, sprintos.EXPORT_DIR, sprintos.WORKFLOW_DIR, sprintos.DB_PATH, sprintos.WORKSPACE_DIR, sprintos.BACKUP_DIR = original_paths
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        tmpdir.cleanup()


def checkpoint(name: str, condition: bool, detail: str = "") -> Dict[str, Any]:
    return {
        "name": name,
        "passed": bool(condition),
        "detail": str(detail or ""),
    }


def run_readiness_check() -> Dict[str, Any]:
    warnings: List[str] = []
    blockers: List[str] = []
    checks: List[Dict[str, Any]] = []
    project_id = ""
    project_title = ""
    workspace_path = ""
    release_path = ""
    next_tiny_action = ""

    with isolated_runtime():
        setup_doctor = sprintos.run_setup_doctor(record_activity=False)
        checks.append(
            checkpoint(
                "Setup Doctor helper works",
                isinstance(setup_doctor.get("sections"), dict) and "runtime" in setup_doctor["sections"],
                setup_doctor.get("status", ""),
            )
        )
        warnings.extend(list(setup_doctor.get("warnings") or []))

        guided_demo = sprintos.run_guided_demo("quick")
        checks.append(
            checkpoint(
                "Guided Demo quick works",
                str(guided_demo.get("run_status") or "") in {"completed", "completed_with_warnings", "partial"},
                guided_demo.get("demo_run_id", ""),
            )
        )
        warnings.extend(list(guided_demo.get("warnings") or []))
        blockers.extend(list(guided_demo.get("blockers") or []))

        quick_launch = sprintos.run_quick_launch(
            raw_idea=RAW_IDEA,
            launch_goal="codex_build_ready",
            timebox_minutes=120,
            energy_level="medium",
            end_output="a local testable flashcard prototype",
            generation_mode="offline",
        )
        project_id = str(quick_launch.get("project_id") or "")
        project = sprintos.get_project(project_id)
        if not project:
            raise ValueError("Quick Launch project could not be reloaded")
        project_title = str(project.get("title") or project.get("sprint", {}).get("title") or "Sprint")
        checks.append(
            checkpoint(
                "Quick Launch works",
                str(quick_launch.get("status") or "") in {"completed", "completed_with_warnings", "partial"},
                quick_launch.get("quick_launch_id", ""),
            )
        )

        prototype = project.get("latest_prototype")
        build_pack = project.get("latest_build_pack")
        checks.append(checkpoint("Sprint exists", bool(project.get("sprint")), project_id))
        checks.append(checkpoint("Prototype exists", bool(prototype), str((prototype or {}).get("path") or "")))
        checks.append(checkpoint("Build Pack exists", bool(build_pack), str((build_pack or {}).get("path") or "")))

        if not build_pack:
            raise ValueError("Quick Launch did not create a Build Pack")

        workspace = sprintos.write_workspace_export(project, build_pack)
        workspace_path = str(workspace.get("path") or "")
        checks.append(checkpoint("Workspace Export works", bool(workspace_path), workspace_path))

        sprintos.run_workspace_sync(project_id, workspace_id=workspace["workspace_id"], run_checks=True, allow_git=False)
        verification = sprintos.run_project_verification(project_id, verification_scope="all_latest")
        checks.append(
            checkpoint(
                "Run & Verify works",
                str(verification.get("status") or "") in {"passed", "passed_with_warnings", "partial"},
                str(verification.get("report_path") or ""),
            )
        )

        release_pack = sprintos.create_workspace_release_pack(
            project_id,
            workspace_id=workspace["workspace_id"],
            release_label="readiness-rc",
            run_checks=True,
        )
        release_path = str(release_pack.get("path") or "")
        checks.append(checkpoint("Release Pack works", bool(release_path), release_path))

        command_center = sprintos.build_project_command_summary(sprintos.get_project(project_id) or project)
        next_tiny_action = str(command_center.get("next_tiny_action") or "")
        checks.append(
            checkpoint(
                "Command Center exists for created project",
                bool((command_center.get("recommended_action") or {}).get("action_id")),
                next_tiny_action,
            )
        )

        backup = sprintos.create_local_backup(backup_label="readiness-audit")
        checks.append(
            checkpoint(
                "Local Backup works",
                bool(backup.get("backup_id")) and Path(str(backup.get("backup_path") or "")).exists(),
                str(backup.get("backup_path") or ""),
            )
        )

        dashboard = sprintos.build_today_dashboard_summary()
        checks.append(
            checkpoint(
                "Today Dashboard works",
                bool((dashboard.get("stats") or {}).get("total_projects", 0) >= 1)
                and isinstance(dashboard.get("setup_doctor"), dict),
                str((dashboard.get("global_recommended_action") or {}).get("action_id") or ""),
            )
        )

        artifact_history = sprintos.get_project_artifact_history(project_id, limit_per_type=10)
        checks.append(
            checkpoint(
                "Artifact History works",
                int(artifact_history.get("total_count") or 0) >= 1,
                str(artifact_history.get("latest_artifact_type") or ""),
            )
        )

        warnings.extend(list(quick_launch.get("warnings") or []))
        blockers.extend(list(quick_launch.get("blockers") or []))
        warnings.extend(list(verification.get("warnings") or []))
        blockers.extend(list(verification.get("blockers") or []))
        warnings.extend(list(release_pack.get("warnings") or []))
        blockers.extend(list(release_pack.get("blockers") or []))

    failed_checks = [item["name"] for item in checks if not item["passed"]]
    if failed_checks:
        blockers.extend(f"Failed readiness check: {item}" for item in failed_checks)
    return {
        "ok": not failed_checks,
        "checks": checks,
        "project_id": project_id,
        "project_title": project_title,
        "workspace_path": workspace_path,
        "release_path": release_path,
        "next_tiny_action": next_tiny_action,
        "warnings": sprintos.dedupe_items(warnings),
        "blockers": sprintos.dedupe_items(blockers),
    }


def print_report(result: Dict[str, Any]) -> None:
    print(f"Readiness: {'PASS' if result.get('ok') else 'FAIL'}")
    for item in result.get("checks") or []:
        status = "PASS" if item.get("passed") else "FAIL"
        detail = f" - {item.get('detail')}" if item.get("detail") else ""
        print(f"- {status}: {item.get('name')}{detail}")
    print(f"- Project ID: {result.get('project_id') or 'n/a'}")
    print(f"- Project title: {result.get('project_title') or 'n/a'}")
    print(f"- Workspace path: {result.get('workspace_path') or 'n/a'}")
    print(f"- Release path: {result.get('release_path') or 'n/a'}")
    print(f"- Next tiny action: {result.get('next_tiny_action') or 'n/a'}")
    print("- Warnings:")
    for item in result.get("warnings") or ["none"]:
        print(f"  - {item}")
    print("- Blockers:")
    for item in result.get("blockers") or ["none"]:
        print(f"  - {item}")


def main() -> int:
    result = run_readiness_check()
    print_report(result)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
