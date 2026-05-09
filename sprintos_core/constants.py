"""Shared constants for SprintOS."""

from __future__ import annotations

from typing import Dict, Tuple

DEFAULT_VERIFICATION_COMMANDS = [
    "python3 -m unittest",
    "python3 scripts/smoke.py",
]

PROJECT_STATUSES: Tuple[str, ...] = ("active", "parked", "done", "abandoned")
DEFAULT_PROJECT_STATUS = "active"

PROTOTYPE_TYPES: Dict[str, str] = {
    "landing_page": "Landing page",
    "ai_text_tool": "AI text tool",
    "calculator": "Calculator",
    "quiz_funnel": "Quiz funnel",
    "codex_app_brief": "Codex app brief",
}

DEPLOY_TARGETS: Dict[str, str] = {
    "static": "Static",
    "github_pages": "GitHub Pages",
    "netlify": "Netlify",
    "vercel": "Vercel",
}

BUILD_TARGETS: Dict[str, str] = {
    "static_app": "Static app",
    "python_stdlib_app": "Python stdlib app",
    "ai_tool_stub": "AI tool stub",
    "codex_repo_brief": "Codex repo brief",
}

PIPELINE_GOALS: Dict[str, str] = {
    "validate_fast": "Validate fast",
    "public_static_test": "Public static test",
    "codex_build_ready": "Codex build ready",
}

PIPELINE_STATUSES: Tuple[str, ...] = ("completed", "completed_with_warnings", "partial", "failed")
QUICK_LAUNCH_STATUSES = PIPELINE_STATUSES
DEMO_RUN_STATUSES: Tuple[str, ...] = ("completed", "completed_with_warnings", "partial", "failed")
DEMO_RUN_MODES: Tuple[str, ...] = ("quick", "full")
WORKSPACE_STATUSES: Tuple[str, ...] = ("active", "archived")
WORKSPACE_SNAPSHOT_STATUSES: Tuple[str, ...] = ("created", "restored", "archived", "failed")
WORKSPACE_SYNC_STATUSES: Tuple[str, ...] = ("passed", "passed_with_warnings", "failed", "partial")
WORKSPACE_SYNC_CHECK_STATUSES: Tuple[str, ...] = ("passed", "passed_with_warnings", "failed", "partial", "skipped")
WORKSPACE_RELEASE_STATUSES: Tuple[str, ...] = ("ready", "ready_with_warnings", "blocked", "partial")
WORKSPACE_RELEASE_TYPES: Tuple[str, ...] = ("static_site", "local_python_app", "ai_tool_app", "repo_brief")
FOCUS_SESSION_STATUSES: Tuple[str, ...] = ("planned", "active", "completed", "stopped", "abandoned")
LOCAL_BACKUP_STATUSES: Tuple[str, ...] = ("created", "verified", "restored", "failed")
LOCAL_RESTORE_STATUSES: Tuple[str, ...] = ("completed", "completed_with_warnings", "failed", "dry_run")

VERIFICATION_SCOPES: Tuple[str, ...] = (
    "project",
    "prototype",
    "deploy_pack",
    "build_pack",
    "pipeline",
    "quick_launch",
    "all_latest",
)
VERIFICATION_RUN_STATUSES: Tuple[str, ...] = ("passed", "passed_with_warnings", "failed", "partial")

PIPELINE_REPORT_FILES: Tuple[str, ...] = (
    "pipeline-report.md",
    "artifact-index.md",
    "next-action.md",
    "codex-next-prompt.md",
    "share-message.md",
    "manual-test-checklist.md",
    "pipeline-run.json",
)

QUICK_LAUNCH_REPORT_FILES: Tuple[str, ...] = (
    "quick-launch-report.md",
    "artifact-index.md",
    "next-action.md",
    "codex-next-prompt.md",
    "share-message.md",
    "manual-test-checklist.md",
    "launch-bundle.json",
)

GUIDED_DEMO_REPORT_FILES: Tuple[str, ...] = (
    "demo-report.md",
    "demo-artifact-index.md",
    "demo-next-action.md",
    "demo-codex-prompt.md",
    "demo-summary.json",
)

VERIFICATION_REPORT_FILES: Tuple[str, ...] = (
    "verification-report.md",
    "check-results.json",
    "next-action.md",
    "codex-fix-prompt.md",
    "tester-share-readiness.md",
)

WORKSPACE_SYNC_REPORT_FILES: Tuple[str, ...] = (
    "workspace-sync-report.md",
    "changed-files.json",
    "changed-files.md",
    "run-test-summary.md",
    "next-action.md",
    "codex-followup-prompt.md",
    "sprintos-import-note.md",
    "workspace-sync.json",
)

WORKSPACE_RELEASE_REPORT_FILES: Tuple[str, ...] = (
    "RELEASE.md",
    "RELEASE_NOTES.md",
    "RUN_AND_TEST.md",
    "TESTER_INSTRUCTIONS.md",
    "DEPLOY_OR_SHARE.md",
    "CHANGE_SUMMARY.md",
    "RELEASE_CHECKLIST.md",
    "CODEX_NEXT_PROMPT.md",
    "release-pack.json",
)

WORKSPACE_SNAPSHOT_REPORT_FILES: Tuple[str, ...] = (
    "snapshot-manifest.json",
    "snapshot-report.md",
    "restore-instructions.md",
)

WORKSPACE_RESTORE_REPORT_FILES: Tuple[str, ...] = (
    "restore-report.md",
    "restore-result.json",
    "post-restore-next-action.md",
)

LOCAL_BACKUP_REPORT_FILES: Tuple[str, ...] = (
    "backup-manifest.json",
    "backup-report.md",
    "restore-instructions.md",
)

LOCAL_RESTORE_REPORT_FILES: Tuple[str, ...] = (
    "restore-report.md",
    "restore-result.json",
    "post-restore-next-action.md",
)

FOCUS_SESSION_REPORT_FILES: Tuple[str, ...] = (
    "focus-session-report.md",
    "session-summary.json",
    "next-action.md",
    "codex-next-prompt.md",
    "resume-note.md",
)

WORKSPACE_ADDED_FILES: Tuple[str, ...] = (
    "SPRINTOS_ORIGIN.md",
    "WORKSPACE_README.md",
    "CODEX_START_HERE.md",
    "RUN_AND_TEST.md",
    "LOCAL_ONLY_NOTICE.md",
    "workspace.json",
    "init_git.sh",
    "init_git.ps1",
)

PROTOTYPE_FILES: Tuple[str, ...] = (
    "index.html",
    "style.css",
    "app.js",
    "README.md",
    "feedback-questions.md",
    "feedback-import-instructions.md",
    "TEST_PLAN.md",
    "test-plan.md",
    "codex-build-prompt.md",
    "prototype.json",
)

DEPLOY_PACK_FILES: Tuple[str, ...] = (
    "index.html",
    "style.css",
    "app.js",
    "README.md",
    "DEPLOY.md",
    "feedback-questions.md",
    "test-plan.md",
    "codex-build-prompt.md",
    "deploy-pack.json",
)

BUILD_PACK_ROOT_FILES: Tuple[str, ...] = (
    "README.md",
    "AGENTS.md",
    "IMPLEMENTATION_BRIEF.md",
    "CODEX_BUILD_PROMPT.md",
    "ACCEPTANCE_CRITERIA.md",
    "TEST_PLAN.md",
    "ROADMAP.md",
    ".gitignore",
    "build-pack.json",
)

BUILD_PACK_TARGET_FILES: Dict[str, Tuple[str, ...]] = {
    "static_app": (
        "src/index.html",
        "src/style.css",
        "src/app.js",
        "tests/smoke_static.py",
    ),
    "python_stdlib_app": (
        "app.py",
        "src/templates/index.html",
        "src/static/style.css",
        "src/static/app.js",
        "tests/smoke_app.py",
    ),
    "ai_tool_stub": (
        "app.py",
        "src/templates/index.html",
        "src/static/style.css",
        "src/static/app.js",
        ".env.example",
        "tests/smoke_app.py",
    ),
    "codex_repo_brief": (
        "prototype-reference.md",
        "feedback-reference.md",
        "deploy-reference.md",
    ),
}

FEEDBACK_EXPORT_FIELDS: Tuple[str, ...] = (
    "rating",
    "pain_level",
    "would_use",
    "would_pay",
    "confusing_parts",
    "missing_features",
    "favorite_part",
    "freeform_feedback",
)

FEEDBACK_CHOICE_VALUES: Tuple[str, ...] = ("yes", "no", "maybe")
FEEDBACK_SOURCES: Tuple[str, ...] = ("manual", "imported_json", "local_preview")
ITERATION_DECISIONS: Tuple[str, ...] = ("iterate", "pivot", "park", "test with more people")
RELEASE_ITERATION_DECISIONS: Tuple[str, ...] = ("iterate", "fix_blockers", "test_more", "park", "release_ready")
TIMEBOX_MINUTES: Tuple[int, ...] = (30, 60, 120, 240)
FOCUS_SESSION_TIMEBOX_MINUTES: Tuple[int, ...] = (15, 30, 60, 120)

VAGUE_NEXT_ACTION_PREFIXES: Tuple[str, ...] = (
    "continue",
    "continue building",
    "continue working",
    "improve",
    "research",
    "work on",
    "make progress",
    "keep building",
    "keep working",
    "refine",
)

CODEX_FIX_NON_GOALS: Tuple[str, ...] = (
    "Do not add auth.",
    "Do not add cloud sync.",
    "Do not call external APIs.",
    "Do not create GitHub repos automatically.",
    "Do not deploy automatically.",
    "Do not add a frontend framework or package manager.",
)
