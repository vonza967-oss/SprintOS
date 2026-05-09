#!/usr/bin/env python3

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sprintos
from sprintos_core.ai_provider import ai_enabled, load_ai_provider_config
from sprintos_core.env_utils import load_local_env
from sprintos_core.verification_utils import (
    infer_static_app_shape,
    static_app_shape_verification_checks,
    universal_app_contract_verification_checks,
)


ACCEPTANCE_REQUIRED_APP_FILES = (
    "index.html",
    "style.css",
    "app.js",
    "README.md",
    "TEST_PLAN.md",
)
SECRET_TEXT_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._-]+"),
    re.compile(r"(?i)\bOPENAI_API_KEY\b\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\bDEEPSEEK_API_KEY\b\s*[:=]\s*[^\s,;]+"),
)
CANONICAL_CASES = (
    {
        "name": "idea_scorer",
        "display_name": "Idea Scorecard",
        "shape": "business_idea_scorer",
        "raw_idea": "Build a simple app where founders paste a rough business idea and get a local score, risk notes, smallest test, and next action.",
        "desired_output": "a local business idea scoring app",
    },
    {
        "name": "budget_snapshot",
        "display_name": "Budget Snapshot",
        "shape": "budget_calculator",
        "raw_idea": "Create a personal budget calculator where users enter income and expenses and see savings, spending breakdown, and a practical recommendation.",
        "desired_output": "a local budget calculator app",
    },
    {
        "name": "study_card_builder",
        "display_name": "Study Card Builder",
        "shape": "flashcard_helper",
        "raw_idea": "I want a simple app where students paste study notes and get local flashcards they can review immediately.",
        "desired_output": "a local study flashcard app",
    },
    {
        "name": "decision_matrix",
        "display_name": "Decision Matrix",
        "shape": "decision_matrix",
        "raw_idea": "Build a decision matrix app where I enter options and criteria, compare them locally, see a ranked list, recommendation, and tradeoff notes.",
        "desired_output": "a local decision matrix app",
    },
    {
        "name": "pricing_roi_calculator",
        "display_name": "Pricing ROI Calculator",
        "shape": "pricing_roi_calculator",
        "raw_idea": "Build a pricing ROI calculator where I enter price, unit cost, customers, and investment, then see revenue, margin, break-even, payback, and a recommendation.",
        "desired_output": "a local pricing ROI calculator app",
    },
)
GENERIC_CUSTOM_CASES = (
    {
        "name": "habit_tracker",
        "display_name": "Habit Tracker",
        "shape": "",
        "contract": "universal_app_contract_v1",
        "case_summary": "Local habit tracker with habit entry, completion marking, daily progress, and day reset.",
        "raw_idea": "Create a local habit tracker that lets a user enter habits, mark completion, see today's progress, and reset the day.",
        "desired_output": "a local habit tracker app",
    },
    {
        "name": "mini_crm",
        "display_name": "Mini CRM",
        "shape": "",
        "contract": "universal_app_contract_v1",
        "case_summary": "Local freelancer lead tracker with status, next follow-up date, and notes.",
        "raw_idea": "Create a local mini CRM for freelancers to track leads, status, next follow-up date, and notes.",
        "desired_output": "a local freelancer CRM app",
    },
    {
        "name": "inventory_tracker",
        "display_name": "Inventory Tracker",
        "shape": "",
        "contract": "universal_app_contract_v1",
        "case_summary": "Local small-shop inventory tracker with quantity thresholds and low-stock alerts.",
        "raw_idea": "Create a local inventory tracker for a small shop with item name, quantity, reorder threshold, and low-stock alerts.",
        "desired_output": "a local small-shop inventory tracker app",
    },
    {
        "name": "content_calendar",
        "display_name": "Content Calendar",
        "shape": "",
        "contract": "universal_app_contract_v1",
        "case_summary": "Local content calendar with post ideas, channels, deadlines, statuses, and weekly overview.",
        "raw_idea": "Create a local content calendar planner with post idea, channel, deadline, status, and a weekly overview.",
        "desired_output": "a local content calendar planner app",
    },
)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).strip().lower()
            if (
                lowered in {"authorization", "headers", "api_key", "openai_api_key", "deepseek_api_key", "env", "environment"}
                or "prompt" in lowered
                or "payload" in lowered
                or "response" in lowered
                or lowered.endswith("_key")
            ):
                redacted[str(key)] = "[redacted]"
            else:
                redacted[str(key)] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        text = value
        for pattern in SECRET_TEXT_PATTERNS:
            text = pattern.sub("[redacted]", text)
        return sprintos.activity_redact_text(text, limit=500)
    return value


def _truthy_env(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _running_from_test_environment() -> bool:
    return (
        str(os.environ.get("NODE_ENV") or "").strip().lower() == "test"
        or _truthy_env("SPRINTOS_TEST_MODE")
        or bool(os.environ.get("PYTEST_CURRENT_TEST"))
    )


def _configure_runtime(run_root: Path) -> None:
    sprintos.DATA_DIR = run_root / "data"
    sprintos.EXPORT_DIR = run_root / "exports"
    sprintos.WORKFLOW_DIR = run_root / "workflows"
    sprintos.DB_PATH = sprintos.DATA_DIR / "sprintos.sqlite"
    sprintos.WORKSPACE_DIR = run_root / "workspaces"
    sprintos.BACKUP_DIR = run_root / "backups"
    sprintos.ensure_dirs()
    sprintos.write_default_workflows()
    sprintos.init_db()


def _create_offline_project(raw_idea: str, desired_output: str) -> dict[str, Any]:
    workflows = sprintos.load_workflows()
    sprint = sprintos.generate_sprint(
        raw_idea,
        "auto",
        120,
        "medium",
        desired_output,
        generation_mode="offline",
    )
    sprint["title"] = sprintos.title_from_idea(raw_idea)
    workflow_id = str(sprint.get("_workflow_id") or sprintos.infer_workflow(raw_idea, "auto", workflows))
    project_id = sprintos.save_project(
        raw_idea,
        workflow_id,
        120,
        "medium",
        desired_output,
        sprint,
    )
    project = sprintos.get_project(project_id)
    if not project:
        raise RuntimeError("Project was not saved correctly.")
    return project


def _safe_output_summary(value: Any) -> str:
    text = sprintos.activity_redact_text(value, limit=500)
    if not text:
        return ""
    traceback_start = text.lower().find("traceback (most recent call last)")
    if traceback_start >= 0:
        text = text[:traceback_start].strip() or "Command failed; full stack trace redacted."
    return text[:500]


def _diagnostic_for_project(project_id: str) -> dict[str, Any]:
    for item in sprintos.list_ai_diagnostics(limit=30):
        metadata = item.get("metadata") or {}
        if str(item.get("task_name") or "") == "app_file_generation" and str(metadata.get("project_id") or "") == project_id:
            return _redact(
                {
                    "provider": item.get("provider"),
                    "model": item.get("model"),
                    "used_ai": item.get("used_ai"),
                    "ok": item.get("ok"),
                    "fallback_reason": item.get("fallback_reason"),
                    "error_summary": item.get("error_summary"),
                    "warnings": metadata.get("provider_warnings") or item.get("warnings") or [],
                    "duration_ms": item.get("duration_ms"),
                    "input_size_chars": item.get("input_size_chars"),
                    "output_size_chars": item.get("output_size_chars"),
                    "estimated_input_tokens": item.get("estimated_input_tokens"),
                    "estimated_output_tokens": item.get("estimated_output_tokens"),
                    "estimated_cost_usd": item.get("estimated_cost_usd"),
                }
            )
    return {}


def _file_existence(base: Path, names: list[str]) -> dict[str, Any]:
    missing = [name for name in names if not (base / name).exists()]
    return {
        "ok": not missing,
        "base_path": str(base),
        "required": names,
        "missing": missing,
    }


def _zip_safety_result(zip_name: str, zip_bytes: bytes) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    names: list[str] = []
    if not zip_name or not zip_bytes:
        return {"ok": False, "entries": [], "blockers": ["ZIP was not created."], "warnings": []}
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            for name in names:
                parts = [part for part in Path(name).parts if part not in {".", ""}]
                if any(part == ".git" for part in parts):
                    blockers.append(f"ZIP contains forbidden .git path: {name}")
                if any(part == ".env" or part.startswith(".env.") for part in parts):
                    blockers.append(f"ZIP contains forbidden env file: {name}")
                if name.endswith("/"):
                    continue
                try:
                    data = zf.read(name)
                except KeyError:
                    warnings.append(f"Could not inspect ZIP entry: {name}")
                    continue
                text = data[:250_000].decode("utf-8", errors="ignore")
                for pattern in SECRET_TEXT_PATTERNS:
                    if pattern.search(text):
                        blockers.append(f"ZIP entry contains an obvious secret pattern: {name}")
                        break
    except zipfile.BadZipFile:
        blockers.append("ZIP payload is not a valid ZIP file.")
    return {
        "ok": not blockers,
        "entries": names,
        "blockers": [sprintos.activity_redact_text(item, limit=360) for item in blockers],
        "warnings": [sprintos.activity_redact_text(item, limit=240) for item in warnings],
    }


def _case_sets(case_set: str) -> tuple[dict[str, str], ...]:
    if case_set == "canonical":
        return CANONICAL_CASES
    if case_set == "generic":
        return GENERIC_CUSTOM_CASES
    if case_set == "all":
        return CANONICAL_CASES + GENERIC_CUSTOM_CASES
    raise ValueError(f"Unknown case set: {case_set}")


def _case_contract(case: dict[str, str]) -> str:
    return str(case.get("contract") or ("canonical_app_shape_v1" if case.get("shape") else "universal_app_contract_v1"))


def _shape_result(shape: str, prototype_path: Path, *, project_text: str = "", generic: bool = False) -> dict[str, Any]:
    index_html = (prototype_path / "index.html").read_text(encoding="utf-8") if (prototype_path / "index.html").exists() else ""
    app_js = (prototype_path / "app.js").read_text(encoding="utf-8") if (prototype_path / "app.js").exists() else ""
    readme_text = (prototype_path / "README.md").read_text(encoding="utf-8") if (prototype_path / "README.md").exists() else ""
    test_plan_text = (prototype_path / "TEST_PLAN.md").read_text(encoding="utf-8") if (prototype_path / "TEST_PLAN.md").exists() else ""
    files = {
        "index.html": index_html,
        "app.js": app_js,
        "README.md": readme_text,
        "TEST_PLAN.md": test_plan_text,
    }
    inferred_shape = ""
    canonical_shape_applied = False
    if generic or not shape:
        inferred_shape = infer_static_app_shape(project_text, files=files)
        canonical_shape_applied = bool(inferred_shape)
        checks = universal_app_contract_verification_checks(
            index_html=index_html,
            app_js=app_js,
            readme_text=readme_text,
            test_plan_text=test_plan_text,
            path=str(prototype_path / "index.html"),
        )
        if canonical_shape_applied:
            checks.append(
                {
                    "name": "universal app: no canonical shape is inferred",
                    "status": "fail",
                    "message": f"Generic/custom case was incorrectly inferred as canonical shape `{inferred_shape}`.",
                    "path": str(prototype_path / "index.html"),
                }
            )
    else:
        checks = static_app_shape_verification_checks(
            shape,
            index_html=index_html,
            app_js=app_js,
            readme_text=readme_text,
            path=str(prototype_path / "index.html"),
        )
    failures = [item for item in checks if str(item.get("status") or "") != "pass"]
    return {
        "ok": not failures,
        "shape": shape,
        "contract": "universal_app_contract_v1" if (generic or not shape) else "canonical_app_shape_v1",
        "inferred_canonical_shape": inferred_shape,
        "canonical_shape_applied": canonical_shape_applied,
        "checks": checks,
        "failures": failures,
    }


def _package_result(project: dict[str, Any], prototype: dict[str, Any]) -> dict[str, Any]:
    build_pack = sprintos.write_build_pack(project, prototype, "static_app")
    build_path = Path(str(build_pack.get("path") or ""))
    required = sprintos.build_pack_files_for_target("static_app")
    files = _file_existence(build_path, required)
    zip_name, zip_bytes = sprintos.build_build_pack_zip(build_pack)
    zip_safety = _zip_safety_result(zip_name, zip_bytes)
    smoke = sprintos.run_safe_generated_check([sys.executable, "tests/smoke_static.py"], build_path, timeout=15)
    verification = sprintos.verify_build_pack_artifact(project, build_pack)
    smoke_ok = bool(smoke.get("returncode") == 0 and not smoke.get("timed_out"))
    verification_ok = str(verification.get("status") or "") in {"passed", "passed_with_warnings"}
    return {
        "ok": bool(files["ok"] and zip_name and len(zip_bytes) > 1000 and zip_safety["ok"] and smoke_ok and verification_ok),
        "build_pack_id": build_pack.get("id"),
        "path": str(build_path),
        "preview_url": build_pack.get("preview_url"),
        "files": files,
        "zip": {
            "ok": bool(zip_name and len(zip_bytes) > 1000),
            "name": zip_name,
            "bytes": len(zip_bytes),
            "safety": zip_safety,
        },
        "smoke": {
            "ok": smoke_ok,
            "returncode": smoke.get("returncode"),
            "timed_out": smoke.get("timed_out"),
            "output_summary": _safe_output_summary(smoke.get("stderr") or smoke.get("stdout") or ""),
        },
        "verification": {
            "ok": verification_ok,
            "status": verification.get("status"),
            "blockers": verification.get("blockers") or [],
            "warnings": verification.get("warnings") or [],
        },
    }


def _write_custom_ai_prototype_package(project: dict[str, Any], case: dict[str, str]) -> dict[str, Any]:
    prototype_type = "ai_text_tool"
    created_at = sprintos.now_iso()
    prototype_id = sprintos.uuid.uuid4().hex
    ctx = sprintos.prototype_context_offline(project, prototype_type, prototype_id=prototype_id)
    ctx.update(
        {
            "title": case.get("display_name") or sprintos.title_from_idea(str(project.get("raw_idea") or "")),
            "prototype_type": prototype_type,
            "prototype_label": sprintos.PROTOTYPE_TYPES[prototype_type],
            "offline_template_shape": "",
        }
    )
    fallback_payload = sprintos.prototype_offline_app_file_generation_payload(project, prototype_type, prototype_id, ctx=ctx)
    fallback_payload = dict(fallback_payload)
    fallback_payload["app_name"] = str(case.get("display_name") or fallback_payload.get("app_name") or "Local Prototype")
    fallback_payload["app_type"] = "static_app"
    ai_route = sprintos.ai_generation_route_kwargs("app_file_generation", "ai")
    app_payload, provider_result = sprintos.generate_json_with_ai(
        task_name="app_file_generation",
        instructions=sprintos.app_file_generation_instructions(""),
        user_input=sprintos.app_file_generation_user_input(project, ctx, "static_app"),
        expected_schema_description=json.dumps(fallback_payload, indent=2),
        fallback_factory=fallback_payload,
        config=sprintos.app_generation_budget_config(ai_route["config"]),
        generation_mode=ai_route["generation_mode"],
        validator=lambda candidate: sprintos.validate_app_file_payload_for_shape(candidate, ""),
        route_used=ai_route["route_used"],
        route_id=ai_route["route_id"],
        unavailable_error=ai_route["unavailable_error"],
        unavailable_fallback_reason=ai_route["unavailable_fallback_reason"],
    )
    sprintos.record_ai_diagnostic(
        "app_file_generation",
        provider_result,
        metadata={
            "project_id": str(project.get("id") or ""),
            "prototype_id": prototype_id,
            "prototype_type": prototype_type,
            "provider_warnings": list(provider_result.warnings or []),
        },
    )
    if not provider_result.used_ai:
        reason = sprintos.activity_redact_text(provider_result.fallback_reason or provider_result.error or "AI app generation failed.", limit=360)
        raise RuntimeError(f"Generic/custom app generation did not create app files: {reason}")

    ctx = sprintos.apply_ai_metadata(ctx, "app_file_generation", provider_result)
    ctx["app_generation_fallback_mode"] = "report_only"
    ctx["app_generation_fallback_used"] = False
    primary_files = sprintos.prototype_files_from_app_payload(app_payload)
    package_slug = sprintos.slugify(str(project.get("title") or project.get("sprint", {}).get("title") or "prototype"), "prototype")
    base_name = f"{package_slug}-{sprintos.prototype_folder_timestamp(created_at)}"
    package_dir = sprintos.prototype_export_dir() / base_name
    counter = 2
    while package_dir.exists():
        package_dir = sprintos.prototype_export_dir() / f"{base_name}-{counter}"
        counter += 1
    package_dir.mkdir(parents=True, exist_ok=True)
    primary_files = sprintos.ensure_prototype_feedback_capture(ctx, primary_files)
    files = {
        "index.html": primary_files["index.html"],
        "style.css": primary_files["style.css"],
        "app.js": primary_files["app.js"],
        "README.md": primary_files["README.md"],
        "feedback-questions.md": sprintos.prototype_feedback_markdown(ctx),
        "feedback-import-instructions.md": sprintos.prototype_feedback_import_instructions(ctx),
        "TEST_PLAN.md": primary_files["TEST_PLAN.md"],
        "test-plan.md": primary_files["test-plan.md"],
        "codex-build-prompt.md": sprintos.prototype_codex_prompt(ctx),
    }
    metadata = sprintos.prototype_metadata(project, prototype_id, prototype_type, created_at, list(sprintos.PROTOTYPE_FILES), ai_source=ctx, app_payload=app_payload)
    files["prototype.json"] = json.dumps(metadata, indent=2)
    for name, content in files.items():
        (package_dir / name).write_text(content, encoding="utf-8")
    title = f"{str(app_payload.get('app_name') or ctx['title'])} - {ctx['prototype_label']}"
    with sprintos.db() as conn:
        conn.execute(
            """
            INSERT INTO prototypes (id, project_id, prototype_type, title, path, created_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                prototype_id,
                project["id"],
                prototype_type,
                title,
                str(package_dir),
                created_at,
                json.dumps(metadata),
            ),
        )
        conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (created_at, project["id"]))
        conn.commit()
    prototype = sprintos.get_prototype(prototype_id, include_prompt=True)
    if prototype is None:
        raise RuntimeError("Generic/custom prototype was not saved correctly.")
    return prototype


def _case_failure(case: dict[str, str], exc: Exception) -> dict[str, Any]:
    reason = f"{type(exc).__name__}: {sprintos.activity_redact_text(str(exc), limit=360)}"
    return {
        "name": case["name"],
        "display_name": case.get("display_name") or case["name"],
        "shape": case.get("shape") or "",
        "contract": _case_contract(case),
        "case_summary": case.get("case_summary") or "",
        "status": "fail",
        "ok": False,
        "ai": {"ok": False, "used_ai": False, "diagnostic": {}},
        "files": {"ok": False, "missing": list(ACCEPTANCE_REQUIRED_APP_FILES)},
        "preview": {"ok": False},
        "prototype_zip": {"ok": False},
        "package": {"ok": False},
        "safety": {"ok": False, "blockers": [reason], "warnings": []},
        "shape_checks": {"ok": False, "shape": case.get("shape") or "", "checks": [], "failures": [reason]},
        "failure_reasons": [reason],
    }


def _run_case(case: dict[str, str]) -> dict[str, Any]:
    project = _create_offline_project(case["raw_idea"], case["desired_output"])
    is_generic = _case_contract(case) == "universal_app_contract_v1"
    if is_generic:
        prototype = _write_custom_ai_prototype_package(project, case)
    else:
        prototype = sprintos.write_prototype_package(
            project,
            "landing_page",
            generation_mode="ai",
            fallback_mode="report_only",
        )
    prototype_path = Path(str(prototype.get("path") or ""))
    readiness = sprintos.check_deploy_readiness(prototype)
    prototype_zip_name, prototype_zip_bytes = sprintos.build_prototype_zip(prototype)
    prototype_zip_safety = _zip_safety_result(prototype_zip_name, prototype_zip_bytes)
    diagnostic = _diagnostic_for_project(str(project.get("id") or ""))
    files = _file_existence(prototype_path, list(ACCEPTANCE_REQUIRED_APP_FILES))
    preview_path = prototype_path / "index.html"
    preview = {
        "ok": preview_path.exists() and bool(str(prototype.get("preview_url") or "")),
        "url": prototype.get("preview_url"),
        "path": str(preview_path),
    }
    package = _package_result(project, prototype)
    shape_checks = _shape_result(case.get("shape") or "", prototype_path, project_text=str(case.get("raw_idea") or ""), generic=is_generic)
    safety_blockers = [sprintos.activity_redact_text(str(item), limit=360) for item in (readiness.get("blockers") or [])]
    safety_warnings = [sprintos.activity_redact_text(str(item), limit=360) for item in (readiness.get("warnings") or [])]
    safety = {
        "ok": not safety_blockers,
        "blockers": safety_blockers,
        "warnings": safety_warnings,
        "checked_files": readiness.get("checked_files") or [],
    }
    ai = {
        "ok": bool(diagnostic.get("used_ai") is True),
        "used_ai": bool(diagnostic.get("used_ai") is True),
        "diagnostic": diagnostic,
    }
    prototype_zip = {
        "ok": bool(prototype_zip_name and len(prototype_zip_bytes) > 1000 and prototype_zip_safety["ok"]),
        "name": prototype_zip_name,
        "bytes": len(prototype_zip_bytes),
        "safety": prototype_zip_safety,
    }
    failure_reasons: list[str] = []
    for label, result in (
        ("AI provider was not used", ai),
        ("Required app package files are missing", files),
        ("Preview path is missing", preview),
        ("Prototype ZIP is invalid", prototype_zip),
        ("Static package did not build", package),
        ("Safety checks failed", safety),
        ("Shape checks failed", shape_checks),
    ):
        if not result.get("ok"):
            if label == "Shape checks failed":
                messages = [str(item.get("message") or item) for item in shape_checks.get("failures") or []]
                failure_reasons.extend(messages or [label])
            elif label == "Safety checks failed":
                failure_reasons.extend(safety_blockers or [label])
            elif label == "Static package did not build":
                zip_blockers = ((package.get("zip") or {}).get("safety") or {}).get("blockers") or []
                failure_reasons.extend(package.get("verification", {}).get("blockers") or zip_blockers or [package.get("smoke", {}).get("output_summary") or label])
            elif label == "Prototype ZIP is invalid":
                failure_reasons.extend((prototype_zip_safety.get("blockers") or []) or [label])
            else:
                failure_reasons.append(label)
    ok = not failure_reasons
    return _redact(
        {
            "name": case["name"],
            "display_name": case.get("display_name") or case["name"],
            "shape": case.get("shape") or "",
            "contract": _case_contract(case),
            "case_summary": case.get("case_summary") or "",
            "status": "pass" if ok else "fail",
            "ok": ok,
            "project_id": project.get("id"),
            "prototype_id": prototype.get("id"),
            "prototype_path": str(prototype_path),
            "ai": ai,
            "files": files,
            "preview": preview,
            "prototype_zip": prototype_zip,
            "package": package,
            "safety": safety,
            "shape_checks": shape_checks,
            "failure_reasons": [sprintos.activity_redact_text(item, limit=360) for item in failure_reasons],
        }
    )


def _markdown_case(item: dict[str, Any]) -> list[str]:
    lines = [
        f"## {item.get('display_name') or item['name']}",
        "",
        f"- Case: `{item['name']}` / `{item.get('contract') or item.get('shape')}`",
        f"- Overall: {'PASS' if item.get('ok') else 'FAIL'}",
        f"- AI used: {'PASS' if (item.get('ai') or {}).get('used_ai') else 'FAIL'}",
        f"- Required files: {'PASS' if (item.get('files') or {}).get('ok') else 'FAIL'}",
        f"- Preview path: {'PASS' if (item.get('preview') or {}).get('ok') else 'FAIL'}",
        f"- Package build: {'PASS' if (item.get('package') or {}).get('ok') else 'FAIL'}",
        f"- Safety: {'PASS' if (item.get('safety') or {}).get('ok') else 'FAIL'}",
        f"- Verification contract: {'PASS' if (item.get('shape_checks') or {}).get('ok') else 'FAIL'}",
        "",
    ]
    if item.get("case_summary"):
        lines.insert(3, f"- Case summary: {item.get('case_summary')}")
    reasons = item.get("failure_reasons") or []
    if reasons:
        lines.extend(["### Failure Reasons", ""])
        lines.extend(f"- {reason}" for reason in reasons)
        lines.append("")
    return lines


def _write_reports(run_root: Path, payload: dict[str, Any]) -> None:
    report_json = run_root / "live-app-generation-acceptance.json"
    report_md = run_root / "live-app-generation-acceptance.md"
    redacted = _redact(payload)
    report_json.write_text(json.dumps(redacted, indent=2, sort_keys=True), encoding="utf-8")
    lines = [
        "# Live App Generation Acceptance",
        "",
        f"- Generated at: {redacted['generated_at']}",
        f"- Provider: {redacted['provider']}",
        f"- Model: {redacted['model']}",
        f"- Case set: {redacted.get('case_set') or 'canonical'}",
        f"- Overall: {'PASS' if redacted['ok'] else 'FAIL'}",
        f"- JSON report: `{report_json}`",
        f"- Artifact root: `{run_root}`",
        "",
    ]
    for item in redacted["cases"]:
        lines.extend(_markdown_case(item))
    lines.extend(
        [
            "## Report Schema",
            "",
            "- `ok`: overall boolean pass/fail.",
            "- `generated_at`: ISO timestamp for the acceptance run.",
            "- `provider` / `model`: resolved live provider configuration.",
            "- `run_root`: local export folder containing reports and generated artifacts.",
            "- `cases[]`: one result per selected canonical or generic/custom case.",
            "- `cases[].ai`: redacted provider diagnostic with `used_ai`.",
            "- `cases[].files`: required app package file existence result for `index.html`, `style.css`, `app.js`, `README.md`, and `TEST_PLAN.md`.",
            "- `cases[].preview`: local preview route and resolved index path.",
            "- `cases[].prototype_zip`: generated prototype ZIP metadata and ZIP safety result.",
            "- `cases[].package`: static Build Pack files, ZIP, ZIP safety, smoke, and verification result.",
            "- `cases[].safety`: local static safety/readiness blockers and warnings.",
            "- `cases[].shape_checks`: canonical shape or universal app contract verification checks and failures.",
            "- `cases[].failure_reasons`: actionable redacted reasons for failures.",
            "",
            "Reports intentionally omit API keys, `.env` contents, Authorization headers, raw prompts, raw provider payloads, raw provider responses, and full stack traces.",
            "",
        ]
    )
    report_md.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Opt-in live provider acceptance for SprintOS app_file_generation.")
    parser.add_argument("--confirm-live-provider", action="store_true", help="Required. Allows real provider calls for this script only.")
    parser.add_argument("--provider", choices=("openai", "deepseek"), default="", help="Provider to test. Defaults to SPRINTOS_AI_PROVIDER.")
    parser.add_argument("--model", default="", help="Optional model override for this acceptance run.")
    parser.add_argument(
        "--case-set",
        choices=("canonical", "generic", "all"),
        default="canonical",
        help="Acceptance cases to run. Defaults to canonical for backward compatibility.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.confirm_live_provider:
        print("Refusing to run live provider acceptance without --confirm-live-provider.")
        return 2
    if _running_from_test_environment():
        print("Refusing to run live provider acceptance from a test environment.")
        return 2

    load_local_env(ROOT)
    if args.provider:
        os.environ["SPRINTOS_AI_PROVIDER"] = args.provider
    if args.model:
        os.environ["SPRINTOS_MODEL"] = args.model
    os.environ["SPRINTOS_AI_ENABLED"] = "true"

    generated_at = sprintos.now_iso()
    run_root = ROOT / "exports" / "live_app_generation_acceptance" / sprintos.prototype_folder_timestamp(generated_at)
    run_root.mkdir(parents=True, exist_ok=True)
    config = load_ai_provider_config()
    if not ai_enabled(config):
        payload = _redact(
            {
                "ok": False,
                "generated_at": generated_at,
                "provider": config.provider,
                "model": config.model,
                "case_set": args.case_set,
                "run_root": str(run_root),
                "cases": [],
                "failure_reasons": ["Configured provider is not enabled or its API key is missing."],
            }
        )
        _write_reports(run_root, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 2

    _configure_runtime(run_root)
    sprintos.save_ai_route(
        "app_file_generation",
        "ai",
        config.provider,
        model=config.model,
        enabled=True,
        metadata={"source": "live_app_generation_acceptance"},
        record_activity=False,
    )

    cases = []
    for case in _case_sets(args.case_set):
        try:
            cases.append(_run_case(case))
        except Exception as exc:
            cases.append(_redact(_case_failure(case, exc)))

    failure_reasons = [
        f"{item.get('name')}: {reason}"
        for item in cases
        for reason in (item.get("failure_reasons") or [])
    ]
    payload = _redact(
        {
            "ok": not failure_reasons,
            "generated_at": generated_at,
            "provider": config.provider,
            "model": config.model,
            "case_set": args.case_set,
            "run_root": str(run_root),
            "cases": cases,
            "failure_reasons": failure_reasons,
        }
    )
    _write_reports(run_root, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
