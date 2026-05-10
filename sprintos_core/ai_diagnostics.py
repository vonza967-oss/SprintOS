"""Redacted AI diagnostics helpers for SprintOS."""

from __future__ import annotations

import json
import re
from typing import Any


KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]+")
AUTH_PATTERN = re.compile(r"Authorization:\s*Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE)


def redact_text(value: Any) -> str:
    text = str(value or "")
    text = AUTH_PATTERN.sub("Authorization: Bearer [redacted]", text)
    text = KEY_PATTERN.sub("[redacted]", text)
    return text[:500]


def sanitize_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).strip().lower()
            if lowered in {
                "authorization",
                "api_key",
                "openai_api_key",
                "deepseek_api_key",
                "prompt",
                "instructions",
                "response",
                "raw_prompt",
                "raw_response",
            }:
                continue
            clean[str(key)] = sanitize_metadata(item)
        return clean
    if isinstance(value, list):
        return [sanitize_metadata(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return redact_text(value)


def metadata_json(value: Any) -> str:
    return json.dumps(sanitize_metadata(value), indent=2, sort_keys=True)


def diagnostic_export_markdown(items: list[dict[str, Any]], heading: str) -> str:
    lines = [f"# {heading}", ""]
    if not items:
        lines.extend(["No sanitized AI diagnostics available.", ""])
        return "\n".join(lines)
    for item in items:
        lines.extend(
            [
                f"## {item.get('created_at') or ''} — {item.get('task_name') or 'unknown task'}",
                f"- Mode requested: {item.get('generation_mode_requested') or 'auto'}",
                f"- Used AI: {bool(item.get('used_ai'))}",
                f"- Route used: {bool(item.get('route_used'))}",
                f"- Provider: {item.get('provider') or 'offline'}",
                f"- Resolved provider: {item.get('resolved_provider') or item.get('provider') or 'offline'}",
                f"- Model: {item.get('model') or 'n/a'}",
                f"- Resolved model: {item.get('resolved_model') or item.get('model') or 'n/a'}",
                f"- OK: {bool(item.get('ok'))}",
                f"- Fallback reason: {item.get('fallback_reason') or 'none'}",
                f"- Error summary: {item.get('error_summary') or 'none'}",
                f"- Duration ms: {item.get('duration_ms') or 0}",
                f"- Input chars: {item.get('input_size_chars') or 0}",
                f"- Output chars: {item.get('output_size_chars') or 0}",
                f"- Estimated input tokens: {item.get('estimated_input_tokens') or 0}",
                f"- Estimated output tokens: {item.get('estimated_output_tokens') or 0}",
                f"- Estimated cost usd: {item.get('estimated_cost_usd') if item.get('estimated_cost_usd') is not None else 'n/a'}",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"
