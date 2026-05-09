"""AI schema specs, prompt instructions, and validation helpers for SprintOS."""

from __future__ import annotations

import re
from typing import Any

from .text_utils import sanitize_filename


APP_FILE_GENERATION_ALLOWED_TYPES = {
    "static_app",
    "calculator",
    "quiz",
    "ai_text_tool",
    "landing_page",
}
APP_FILE_GENERATION_REQUIRED_FILES = (
    "index.html",
    "style.css",
    "app.js",
    "README.md",
    "TEST_PLAN.md",
)
APP_FILE_GENERATION_MAX_APP_NAME_WORDS = 5
APP_FILE_GENERATION_MAX_APP_NAME_CHARS = 48
APP_FILE_GENERATION_MAX_SHORT_DESCRIPTION_CHARS = 140
APP_FILE_GENERATION_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]+"),
    re.compile(r"(?i)\bAuthorization\s*:\s*Bearer\s+[A-Za-z0-9._-]+"),
    re.compile(r'(?i)\bOPENAI_API_KEY\b\s*[:=]\s*["\']?[^\s"\']+'),
    re.compile(r'(?i)\bDEEPSEEK_API_KEY\b\s*[:=]\s*["\']?[^\s"\']+'),
)
APP_FILE_GENERATION_PROVIDER_MARKERS = (
    "api.openai.com",
    "openai.com/v1",
    "api.deepseek.com",
    "/chat/completions",
    "/v1/responses",
    "openai_api_key",
    "deepseek_api_key",
)


JSON_SCHEMA_OBJECT_ADDITIONAL_PROPERTIES = False


AI_TASK_SCHEMAS: dict[str, dict[str, Any]] = {
    "sprint_generation": {
        "fields": {
            "title": {"kind": "str"},
            "summary": {"kind": "str"},
            "workflow": {"kind": "str"},
            "done_definition": {"kind": "str"},
            "next_tiny_action": {"kind": "str"},
            "plan_steps": {"kind": "list_str"},
            "artifacts": {
                "kind": "list_object",
                "fields": {
                    "title": {"kind": "str"},
                    "filename": {"kind": "filename", "default_suffix": ".md"},
                    "content": {"kind": "str"},
                },
            },
        }
    },
    "resume_plan": {
        "fields": {
            "recap": {"kind": "str"},
            "next_tiny_action": {"kind": "str"},
            "restart_15_min": {"kind": "list_str"},
            "restart_30_min": {"kind": "list_str"},
            "one_thing_not_to_do": {"kind": "str"},
            "done_definition": {"kind": "str"},
        }
    },
    "prototype_content": {
        "fields": {
            "headline": {"kind": "str"},
            "subheadline": {"kind": "str"},
            "problem": {"kind": "str"},
            "solution": {"kind": "str"},
            "feature_bullets": {"kind": "list_str"},
            "cta_text": {"kind": "str"},
            "tester_questions": {"kind": "list_str"},
        }
    },
    "codex_handoff": {
        "fields": {
            "objective": {"kind": "str"},
            "context": {"kind": "str"},
            "constraints": {"kind": "list_str"},
            "files_likely_touched": {"kind": "list_str"},
            "acceptance_criteria": {"kind": "list_str"},
            "verification_commands": {"kind": "list_str"},
            "review_checklist": {"kind": "list_str"},
            "non_goals": {"kind": "list_str"},
        }
    },
    "quick_launch_summary": {
        "fields": {
            "title": {"kind": "str"},
            "summary": {"kind": "str"},
            "share_message": {"kind": "str"},
            "suggested_first_codex_task": {"kind": "str"},
            "next_tiny_action": {"kind": "str"},
        }
    },
    "app_file_generation": {
        "fields": {
            "app_name": {"kind": "str"},
            "app_type": {"kind": "str"},
            "short_description": {"kind": "str"},
            "user_flow": {"kind": "list_str"},
            "files": {
                "kind": "list_object",
                "fields": {
                    "filename": {"kind": "str", "enum": APP_FILE_GENERATION_REQUIRED_FILES},
                    "content": {"kind": "str"},
                },
            },
            "run_instructions": {"kind": "str"},
            "test_instructions": {"kind": "str"},
            "codex_next_prompt": {"kind": "str"},
            "limitations": {"kind": "list_str"},
            "mocked_parts": {"kind": "list_str"},
        }
    },
}


PRODUCT_RULES = (
    "cut scope aggressively",
    "avoid vague next actions",
    "do not overbuild",
    "preserve local-first behavior",
    "produce PR-sized Codex tasks",
)


def _field_kind_label(name: str, spec: dict[str, Any]) -> str:
    kind = spec.get("kind")
    if kind == "str":
        return f'"{name}": string'
    if kind == "filename":
        return f'"{name}": string filename'
    if kind == "list_str":
        return f'"{name}": list[string]'
    if kind == "list_object":
        child_labels = ", ".join(_field_kind_label(child_name, child_spec) for child_name, child_spec in spec.get("fields", {}).items())
        return f'"{name}": list[object with {child_labels}]'
    return f'"{name}": value'


def task_required_fields(task_name: str) -> list[str]:
    schema = AI_TASK_SCHEMAS.get(task_name) or {}
    return list((schema.get("fields") or {}).keys())


def _json_schema_for_field(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    kind = spec.get("kind")
    if kind in {"str", "filename"}:
        field_schema: dict[str, Any] = {"type": "string"}
        if name == "app_type":
            field_schema["enum"] = sorted(APP_FILE_GENERATION_ALLOWED_TYPES)
        if spec.get("enum"):
            field_schema["enum"] = list(spec.get("enum") or [])
        return field_schema
    if kind == "list_str":
        return {"type": "array", "items": {"type": "string"}}
    if kind == "list_object":
        child_fields = spec.get("fields") or {}
        required = list(child_fields.keys())
        item_properties = {
            child_name: _json_schema_for_field(child_name, child_spec)
            for child_name, child_spec in child_fields.items()
        }
        return {
            "type": "array",
            "items": {
                "type": "object",
                "properties": item_properties,
                "required": required,
                "additionalProperties": JSON_SCHEMA_OBJECT_ADDITIONAL_PROPERTIES,
            },
        }
    return {"type": "string"}


def build_ai_task_json_schema(task_name: str) -> dict[str, Any]:
    schema = AI_TASK_SCHEMAS.get(task_name)
    if not schema:
        raise ValueError(f"Unknown AI task schema: {task_name}")
    fields = schema.get("fields") or {}
    return {
        "type": "object",
        "properties": {
            field_name: _json_schema_for_field(field_name, field_spec)
            for field_name, field_spec in fields.items()
        },
        "required": list(fields.keys()),
        "additionalProperties": JSON_SCHEMA_OBJECT_ADDITIONAL_PROPERTIES,
    }


def build_openai_text_format(task_name: str) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": task_name[:64],
        "description": f"Structured JSON output for SprintOS {task_name}.",
        "schema": build_ai_task_json_schema(task_name),
        "strict": True,
    }


def build_json_only_instructions(task_name: str, role_instruction: str = "") -> str:
    schema = AI_TASK_SCHEMAS[task_name]
    field_lines = "\n".join(f"- {_field_kind_label(name, spec)}" for name, spec in schema["fields"].items())
    rule_lines = "\n".join(f"- {rule}" for rule in PRODUCT_RULES)
    parts = []
    if role_instruction.strip():
        parts.append(role_instruction.strip())
    parts.append(f"Task name: {task_name}")
    parts.append("Return JSON only.")
    parts.append("Do not use markdown fences.")
    parts.append("Required fields:")
    parts.append(field_lines)
    if task_name == "app_file_generation":
        parts.append("Exact app_file_generation contract:")
        parts.append("- Top-level fields: app_name, app_type, short_description, user_flow, files, run_instructions, test_instructions, codex_next_prompt, limitations, mocked_parts.")
        parts.append("- app_type must be one of: static_app, calculator, quiz, ai_text_tool, landing_page.")
        parts.append("- files must contain exactly these filenames: index.html, style.css, app.js, README.md, TEST_PLAN.md.")
        parts.append("- Each file item must contain only filename and content.")
    parts.append("Product rules:")
    parts.append(rule_lines)
    return "\n".join(parts).strip()


def _validate_non_empty_string(value: Any) -> tuple[bool, str]:
    if not isinstance(value, str):
        return False, ""
    cleaned = value.strip()
    return bool(cleaned), cleaned


def _validate_list_of_strings(value: Any) -> tuple[bool, list[str]]:
    if not isinstance(value, list):
        return False, []
    cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return bool(cleaned), cleaned


def _validate_list_of_strings_allow_empty(value: Any) -> tuple[bool, list[str]]:
    if not isinstance(value, list):
        return False, []
    cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
    return True, cleaned


def _validate_list_of_objects(value: Any, field_specs: dict[str, Any]) -> tuple[bool, list[dict[str, Any]], list[str], list[str]]:
    if not isinstance(value, list) or not value:
        return False, [], [], []
    sanitized_items: list[dict[str, Any]] = []
    warnings: list[str] = []
    wrong_fields: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            wrong_fields.append(f"[{index}]")
            continue
        sanitized_item: dict[str, Any] = {}
        extras = sorted(key for key in item.keys() if key not in field_specs)
        if extras:
            warnings.append(f"Ignored extra fields in list item {index + 1}: {', '.join(extras)}")
        item_ok = True
        for child_name, child_spec in field_specs.items():
            child_value = item.get(child_name)
            if child_name not in item:
                wrong_fields.append(f"[{index}].{child_name}")
                item_ok = False
                continue
            if child_spec.get("kind") == "filename":
                ok, cleaned = _validate_non_empty_string(child_value)
                if not ok:
                    wrong_fields.append(f"[{index}].{child_name}")
                    item_ok = False
                    continue
                sanitized_item[child_name] = sanitize_filename(
                    cleaned,
                    default_stem="artifact",
                    default_suffix=str(child_spec.get("default_suffix") or ".md"),
                )
                continue
            ok, cleaned = _validate_non_empty_string(child_value)
            if not ok:
                wrong_fields.append(f"[{index}].{child_name}")
                item_ok = False
                continue
            sanitized_item[child_name] = cleaned
        if item_ok:
            sanitized_items.append(sanitized_item)
    return bool(sanitized_items) and not wrong_fields, sanitized_items, warnings, wrong_fields


def _validate_app_file_filename(value: Any) -> tuple[bool, str]:
    if not isinstance(value, str):
        return False, ""
    cleaned = value.strip()
    normalized = cleaned.replace("\\", "/")
    if not normalized or normalized.startswith("/") or normalized.startswith("./") or "../" in normalized or "/../" in normalized:
        return False, ""
    if "/" in normalized:
        return False, ""
    if normalized not in APP_FILE_GENERATION_REQUIRED_FILES:
        return False, ""
    return True, normalized


def _contains_external_url(text: str) -> bool:
    for match in re.finditer(r"https?://[^\s\"')>]+", text):
        url = match.group(0).lower()
        if "127.0.0.1" in url or "localhost" in url:
            continue
        return True
    return False


def _validate_app_file_generation_payload(payload: Any) -> dict[str, Any]:
    required_fields = (
        "app_name",
        "app_type",
        "short_description",
        "user_flow",
        "files",
        "run_instructions",
        "test_instructions",
        "codex_next_prompt",
        "limitations",
        "mocked_parts",
    )
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "missing_fields": list(required_fields),
            "wrong_type_fields": ["payload"],
            "warnings": [],
            "sanitized_payload": {},
            "validation_detail": app_file_generation_validation_detail(list(required_fields), ["payload"]),
        }

    missing_fields: list[str] = []
    wrong_type_fields: list[str] = []
    warnings: list[str] = []
    sanitized_payload: dict[str, Any] = {}

    extras = sorted(key for key in payload.keys() if key not in required_fields)
    if extras:
        warnings.append("Ignored extra fields: " + ", ".join(extras))

    for field_name in ("app_name", "short_description", "run_instructions", "test_instructions", "codex_next_prompt"):
        ok, cleaned = _validate_non_empty_string(payload.get(field_name))
        if field_name not in payload:
            missing_fields.append(field_name)
        elif not ok:
            wrong_type_fields.append(field_name)
        elif field_name == "app_name" and (
            len(cleaned) > APP_FILE_GENERATION_MAX_APP_NAME_CHARS
            or len([word for word in re.split(r"\s+", cleaned) if word]) > APP_FILE_GENERATION_MAX_APP_NAME_WORDS
        ):
            wrong_type_fields.append(field_name)
        elif field_name == "short_description" and len(cleaned) > APP_FILE_GENERATION_MAX_SHORT_DESCRIPTION_CHARS:
            wrong_type_fields.append(field_name)
        else:
            sanitized_payload[field_name] = cleaned

    if "app_type" not in payload:
        missing_fields.append("app_type")
    else:
        ok, cleaned = _validate_non_empty_string(payload.get("app_type"))
        if not ok or cleaned not in APP_FILE_GENERATION_ALLOWED_TYPES:
            wrong_type_fields.append("app_type")
        else:
            sanitized_payload["app_type"] = cleaned

    if "user_flow" not in payload:
        missing_fields.append("user_flow")
    else:
        ok, cleaned = _validate_list_of_strings(payload.get("user_flow"))
        if not ok:
            wrong_type_fields.append("user_flow")
        else:
            sanitized_payload["user_flow"] = cleaned

    for field_name in ("limitations", "mocked_parts"):
        if field_name not in payload:
            missing_fields.append(field_name)
        else:
            ok, cleaned = _validate_list_of_strings_allow_empty(payload.get(field_name))
            if not ok:
                wrong_type_fields.append(field_name)
            else:
                sanitized_payload[field_name] = cleaned

    files_by_name: dict[str, str] = {}
    sanitized_files: list[dict[str, str]] = []
    if "files" not in payload:
        missing_fields.append("files")
    elif not isinstance(payload.get("files"), list):
        wrong_type_fields.append("files")
    else:
        file_list = payload.get("files") or []
        if not file_list:
            wrong_type_fields.append("files")
        for index, item in enumerate(file_list):
            if not isinstance(item, dict):
                wrong_type_fields.append(f"files[{index}]")
                continue
            ok_filename, filename = _validate_app_file_filename(item.get("filename"))
            ok_content, content = _validate_non_empty_string(item.get("content"))
            if not ok_filename:
                wrong_type_fields.append(f"files[{index}].filename")
                continue
            if not ok_content:
                wrong_type_fields.append(f"files[{index}].content")
                continue
            if filename in files_by_name:
                wrong_type_fields.append(f"files[{index}].filename")
                continue
            files_by_name[filename] = content
            sanitized_files.append({"filename": filename, "content": content})
        if not wrong_type_fields:
            missing_required = [name for name in APP_FILE_GENERATION_REQUIRED_FILES if name not in files_by_name]
            if missing_required:
                missing_fields.extend(f"files:{name}" for name in missing_required)
            sanitized_payload["files"] = sanitized_files

    browser_sources = " ".join(files_by_name.get(name, "") for name in ("index.html", "style.css", "app.js"))
    lowered_sources = browser_sources.lower()
    if files_by_name:
        if files_by_name.get("app.js", "").strip() == "":
            wrong_type_fields.append("files:app.js")
        index_html = files_by_name.get("index.html", "")
        if index_html and ('href="style.css"' not in index_html and "href='style.css'" not in index_html):
            wrong_type_fields.append("files:index.html:style.css")
        if index_html and ('src="app.js"' not in index_html and "src='app.js'" not in index_html):
            wrong_type_fields.append("files:index.html:app.js")
        if any(marker in lowered_sources for marker in ("fetch(", "xmlhttprequest", "sendbeacon")):
            wrong_type_fields.append("files:browser_network_calls")
        if any(marker in lowered_sources for marker in APP_FILE_GENERATION_PROVIDER_MARKERS):
            wrong_type_fields.append("files:browser_provider_calls")
        if _contains_external_url(files_by_name.get("index.html", "")) or _contains_external_url(files_by_name.get("style.css", "")) or _contains_external_url(files_by_name.get("app.js", "")):
            wrong_type_fields.append("files:external_urls")
        if any(pattern.search(browser_sources) for pattern in APP_FILE_GENERATION_SECRET_PATTERNS):
            wrong_type_fields.append("files:secret_pattern")

    return {
        "ok": not missing_fields and not wrong_type_fields,
        "missing_fields": missing_fields,
        "wrong_type_fields": wrong_type_fields,
        "warnings": warnings,
        "sanitized_payload": sanitized_payload,
        "validation_detail": app_file_generation_validation_detail(missing_fields, wrong_type_fields),
    }


def app_file_generation_validation_detail(missing_fields: list[str], wrong_type_fields: list[str]) -> dict[str, Any]:
    missing = [str(item or "") for item in missing_fields if str(item or "").strip()]
    wrong = [str(item or "") for item in wrong_type_fields if str(item or "").strip()]
    missing_required_files = [item.split(":", 1)[1] for item in missing if item.startswith("files:")]
    missing_top_level_fields = [item for item in missing if not item.startswith("files:")]
    invalid_filenames = [item for item in wrong if item.startswith("files[") and item.endswith(".filename")]
    app_shape_failures = [
        item.replace("files:shape_contract:", "")
        for item in wrong
        if item.startswith("files:shape_contract:")
    ]
    app_safety_failures = [
        item
        for item in wrong
        if item
        in {
            "files:browser_network_calls",
            "files:browser_provider_calls",
            "files:external_urls",
            "files:secret_pattern",
        }
    ]
    app_file_failures = [
        item
        for item in wrong
        if item.startswith("files:")
        and item not in app_safety_failures
        and not item.startswith("files:shape_contract:")
    ]
    invalid_app_type = "app_type" in wrong
    if app_safety_failures:
        failure_code = "app_safety_validation_failed"
    elif app_shape_failures:
        failure_code = "app_shape_validation_failed"
    elif invalid_filenames:
        failure_code = "invalid_generated_filename"
    elif missing_required_files:
        failure_code = "missing_required_files"
    elif app_file_failures:
        failure_code = "app_file_validation_failed"
    else:
        failure_code = "schema_validation_failed"
    return {
        "failure_code": failure_code,
        "missing_top_level_fields": missing_top_level_fields,
        "missing_required_files": missing_required_files,
        "invalid_filenames": invalid_filenames,
        "invalid_app_type": invalid_app_type,
        "app_shape_failures": app_shape_failures,
        "app_safety_failures": app_safety_failures,
        "app_file_failures": app_file_failures,
        "wrong_type_fields": wrong,
    }


def validate_ai_payload(task_name: str, payload: Any) -> dict[str, Any]:
    schema = AI_TASK_SCHEMAS.get(task_name)
    if not schema:
        raise ValueError(f"Unknown AI task schema: {task_name}")
    if task_name == "app_file_generation":
        return _validate_app_file_generation_payload(payload)
    required = schema["fields"]
    missing_fields: list[str] = []
    wrong_type_fields: list[str] = []
    warnings: list[str] = []
    sanitized_payload: dict[str, Any] = {}
    if not isinstance(payload, dict):
        return {
            "ok": False,
            "missing_fields": list(required.keys()),
            "wrong_type_fields": ["payload"],
            "warnings": [],
            "sanitized_payload": {},
        }

    extras = sorted(key for key in payload.keys() if key not in required)
    if extras:
        warnings.append("Ignored extra fields: " + ", ".join(extras))

    for field_name, spec in required.items():
        if field_name not in payload:
            missing_fields.append(field_name)
            continue
        value = payload.get(field_name)
        kind = spec.get("kind")
        if kind == "str":
            ok, cleaned = _validate_non_empty_string(value)
            if not ok:
                wrong_type_fields.append(field_name)
                continue
            sanitized_payload[field_name] = cleaned
            continue
        if kind == "filename":
            ok, cleaned = _validate_non_empty_string(value)
            if not ok:
                wrong_type_fields.append(field_name)
                continue
            sanitized_payload[field_name] = sanitize_filename(
                cleaned,
                default_stem="artifact",
                default_suffix=str(spec.get("default_suffix") or ".md"),
            )
            continue
        if kind == "list_str":
            ok, cleaned = _validate_list_of_strings(value)
            if not ok:
                wrong_type_fields.append(field_name)
                continue
            sanitized_payload[field_name] = cleaned
            continue
        if kind == "list_object":
            ok, cleaned, child_warnings, child_wrong = _validate_list_of_objects(value, spec.get("fields") or {})
            warnings.extend(child_warnings)
            if not ok:
                wrong_type_fields.append(field_name)
                wrong_type_fields.extend(f"{field_name}{item}" for item in child_wrong)
                continue
            sanitized_payload[field_name] = cleaned
            continue
        wrong_type_fields.append(field_name)

    return {
        "ok": not missing_fields and not wrong_type_fields,
        "missing_fields": missing_fields,
        "wrong_type_fields": wrong_type_fields,
        "warnings": warnings,
        "sanitized_payload": sanitized_payload,
    }
