from __future__ import annotations

import copy
import json
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Optional

from .ai_costs import estimate_ai_cost, estimate_tokens_from_chars
from .ai_schemas import AI_TASK_SCHEMAS, build_openai_text_format, validate_ai_payload


SUPPORTED_PROVIDERS = {"offline", "openai", "deepseek"}
DEFAULT_OPENAI_MODEL = "gpt-4.1-mini"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-flash"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
GENERATION_MODES = {"auto", "offline", "ai"}


@dataclass(frozen=True)
class AIProviderConfig:
    provider: str
    enabled: bool
    model: str
    base_url: str
    timeout_seconds: int
    max_output_tokens: int
    api_key_present: bool


@dataclass(frozen=True)
class AIProviderResult:
    ok: bool
    text: str
    parsed_json: Any
    error: str
    provider: str
    model: str
    used_ai: bool
    generation_mode_requested: str = "auto"
    fallback_reason: str = ""
    duration_ms: int = 0
    input_size_chars: int = 0
    output_size_chars: int = 0
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    estimated_cost_usd: float | None = None
    warnings: tuple[str, ...] = ()
    task_name: str = ""
    route_used: bool = False
    route_id: str = ""
    validation_details: dict[str, Any] = field(default_factory=dict)


def _env_truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _env_int(value: Any, default: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (AttributeError, TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _provider_api_key_name(provider: str) -> str:
    if provider == "openai":
        return "OPENAI_API_KEY"
    if provider == "deepseek":
        return "DEEPSEEK_API_KEY"
    return ""


def _default_model(provider: str) -> str:
    if provider == "deepseek":
        return DEFAULT_DEEPSEEK_MODEL
    if provider == "openai":
        return DEFAULT_OPENAI_MODEL
    return "offline"


def default_model_for_provider(provider: str) -> str:
    return _default_model(provider)


def _default_base_url(provider: str) -> str:
    if provider == "deepseek":
        return DEFAULT_DEEPSEEK_BASE_URL
    return ""


def _provider_api_key_present(provider: str, source: dict[str, str] | os._Environ[str]) -> bool:
    key_name = _provider_api_key_name(provider)
    if not key_name:
        return False
    return bool(str(source.get(key_name, "") or "").strip())


def build_ai_provider_config(
    provider: str,
    *,
    env: Optional[dict[str, str]] = None,
    model: str = "",
    enabled: Optional[bool] = None,
) -> AIProviderConfig:
    source = env if env is not None else os.environ
    normalized_provider = str(provider or "offline").strip().lower()
    normalized_provider = normalized_provider if normalized_provider in SUPPORTED_PROVIDERS else "offline"
    resolved_enabled = _env_truthy(source.get("SPRINTOS_AI_ENABLED", "false")) if enabled is None else bool(enabled)
    resolved_model = str(model or "").strip() or _default_model(normalized_provider)
    base_url = _default_base_url(normalized_provider)
    if normalized_provider == "deepseek":
        base_url = str(source.get("DEEPSEEK_BASE_URL", DEFAULT_DEEPSEEK_BASE_URL) or DEFAULT_DEEPSEEK_BASE_URL).strip() or DEFAULT_DEEPSEEK_BASE_URL
    timeout_seconds = _env_int(source.get("SPRINTOS_AI_TIMEOUT_SECONDS", 20), 20)
    max_output_tokens = _env_int(source.get("SPRINTOS_AI_MAX_OUTPUT_TOKENS", 2000), 2000)
    return AIProviderConfig(
        provider=normalized_provider,
        enabled=resolved_enabled,
        model=resolved_model,
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        max_output_tokens=max_output_tokens,
        api_key_present=_provider_api_key_present(normalized_provider, source),
    )


def load_ai_provider_config(env: Optional[dict[str, str]] = None) -> AIProviderConfig:
    source = env if env is not None else os.environ
    requested_provider = str(source.get("SPRINTOS_AI_PROVIDER", "offline") or "offline").strip().lower()
    configured_model = str(source.get("SPRINTOS_MODEL", "") or "").strip()
    return build_ai_provider_config(
        requested_provider,
        env=source,
        model=configured_model,
    )


def ai_enabled(config: AIProviderConfig) -> bool:
    return config.provider in {"openai", "deepseek"} and config.enabled and config.api_key_present


def mode_label(config: AIProviderConfig) -> str:
    if config.provider == "offline":
        return "Offline template mode"
    if config.provider == "openai" and not config.enabled:
        return "OpenAI configured but disabled"
    if config.provider == "openai" and not config.api_key_present:
        return "OpenAI enabled but key missing"
    if config.provider == "openai":
        return "OpenAI enabled and key present"
    if config.provider == "deepseek" and not config.enabled:
        return "DeepSeek configured but disabled"
    if config.provider == "deepseek" and not config.api_key_present:
        return "DeepSeek enabled but key missing"
    if config.provider == "deepseek":
        return "DeepSeek enabled and key present"
    return "Unknown provider"


def parse_response_text(response_json: Any) -> str:
    if isinstance(response_json, dict):
        output_text = response_json.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text.strip()

        collected: list[str] = []
        for item in response_json.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                content_type = str(content.get("type") or "").strip().lower()
                text_value = content.get("text")
                if content_type == "output_text":
                    if isinstance(text_value, str) and text_value.strip():
                        collected.append(text_value.strip())
                    elif isinstance(text_value, dict):
                        value = text_value.get("value")
                        if isinstance(value, str) and value.strip():
                            collected.append(value.strip())
                elif isinstance(text_value, str) and text_value.strip():
                    collected.append(text_value.strip())
            if collected:
                continue

        if collected:
            return "\n".join(collected).strip()

        for key in ("text", "content", "response_text"):
            value = response_json.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _redact_error(text: str, api_key: str = "") -> str:
    clean = str(text or "").replace(api_key, "[redacted]") if api_key else str(text or "")
    return clean[:500]


def _try_parse_json(text: str) -> Any:
    stripped = str(text or "").strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def normalize_generation_mode(value: Any) -> str:
    mode = str(value or "auto").strip().lower() or "auto"
    return mode if mode in GENERATION_MODES else "auto"


def _provider_unavailable_reason(config: AIProviderConfig, generation_mode: str) -> str:
    if generation_mode == "offline":
        return "Generation mode forced offline."
    if config.provider == "offline":
        return "AI provider is set to offline."
    if config.provider == "openai" and not config.enabled:
        return "AI provider is disabled."
    if config.provider == "openai" and not config.api_key_present:
        return "OPENAI_API_KEY is missing."
    if config.provider == "deepseek" and not config.enabled:
        return "DeepSeek provider is disabled."
    if config.provider == "deepseek" and not config.api_key_present:
        return "DEEPSEEK_API_KEY is missing."
    return "AI provider is unavailable."


def provider_unavailable_reason(config: AIProviderConfig, generation_mode: str) -> str:
    return _provider_unavailable_reason(config, generation_mode)


def _provider_unavailable_fallback_reason(config: AIProviderConfig, generation_mode: str) -> str:
    if generation_mode == "offline":
        return "offline_mode"
    if config.provider == "openai":
        if not config.enabled:
            return "openai_disabled"
        if not config.api_key_present:
            return "missing_openai_key"
        return "openai_unavailable"
    if config.provider == "deepseek":
        if not config.enabled:
            return "deepseek_disabled"
        if not config.api_key_present:
            return "missing_deepseek_key"
        return "deepseek_unavailable"
    return "offline_provider"


def provider_unavailable_fallback_reason(config: AIProviderConfig, generation_mode: str) -> str:
    return _provider_unavailable_fallback_reason(config, generation_mode)


def _annotate_result(
    result: AIProviderResult,
    *,
    generation_mode_requested: str,
    fallback_reason: Optional[str] = None,
    duration_ms: Optional[int] = None,
    input_size_chars: Optional[int] = None,
    output_size_chars: Optional[int] = None,
    estimated_input_tokens: Optional[int] = None,
    estimated_output_tokens: Optional[int] = None,
    estimated_cost_usd: Optional[float] = None,
    warnings: Optional[list[str] | tuple[str, ...]] = None,
    task_name: str = "",
    route_used: Optional[bool] = None,
    route_id: Optional[str] = None,
    validation_details: Optional[dict[str, Any]] = None,
) -> AIProviderResult:
    return replace(
        result,
        generation_mode_requested=generation_mode_requested,
        fallback_reason=result.fallback_reason if fallback_reason is None else fallback_reason,
        duration_ms=result.duration_ms if duration_ms is None else duration_ms,
        input_size_chars=result.input_size_chars if input_size_chars is None else input_size_chars,
        output_size_chars=result.output_size_chars if output_size_chars is None else output_size_chars,
        estimated_input_tokens=result.estimated_input_tokens if estimated_input_tokens is None else estimated_input_tokens,
        estimated_output_tokens=result.estimated_output_tokens if estimated_output_tokens is None else estimated_output_tokens,
        estimated_cost_usd=result.estimated_cost_usd if estimated_cost_usd is None else estimated_cost_usd,
        warnings=result.warnings if warnings is None else tuple(warnings),
        task_name=result.task_name or task_name,
        route_used=result.route_used if route_used is None else route_used,
        route_id=result.route_id if route_id is None else route_id,
        validation_details=result.validation_details if validation_details is None else dict(validation_details),
    )


def _transport_request(
    request: urllib.request.Request,
    *,
    timeout: int,
    transport: Optional[Callable[..., Any]] = None,
    ssl_context: Optional[ssl.SSLContext] = None,
) -> str:
    opener = transport or urllib.request.urlopen
    if transport is None:
        response = opener(request, timeout=timeout, context=ssl_context)
    else:
        response = opener(request, timeout=timeout)
    with response as http_response:
        return http_response.read().decode("utf-8")


def parse_deepseek_chat_text(response_json: Any) -> str:
    if not isinstance(response_json, dict):
        return ""
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if not isinstance(item, dict):
                continue
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                parts.append(text_value.strip())
        return "\n".join(parts).strip()
    return ""


def _openai_structured_failure(response_json: Any) -> tuple[str, str]:
    if not isinstance(response_json, dict):
        return "", ""
    status = str(response_json.get("status") or "").strip().lower()
    if status == "incomplete":
        details = response_json.get("incomplete_details")
        reason = ""
        if isinstance(details, dict):
            reason = str(details.get("reason") or "").strip()
        if reason == "max_output_tokens":
            return "OpenAI response was incomplete because it reached the max output token limit.", "openai_length"
        return "OpenAI response was incomplete before a complete JSON payload was available.", "openai_incomplete"
    for item in response_json.get("output", []) or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []) or []:
            if not isinstance(content, dict):
                continue
            content_type = str(content.get("type") or "").strip().lower()
            if content_type == "refusal" or content.get("refusal"):
                return "OpenAI returned a refusal instead of app JSON.", "openai_refusal"
    return "", ""


def _deepseek_structured_failure(response_json: Any) -> tuple[str, str]:
    if not isinstance(response_json, dict):
        return "", ""
    choices = response_json.get("choices")
    if not isinstance(choices, list) or not choices:
        return "", ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return "", ""
    finish_reason = str(first_choice.get("finish_reason") or "").strip().lower()
    if finish_reason == "length":
        return "DeepSeek response reached the max token limit before a complete JSON payload was available.", "deepseek_length"
    message = first_choice.get("message")
    if isinstance(message, dict) and message.get("refusal"):
        return "DeepSeek returned a refusal instead of app JSON.", "deepseek_refusal"
    return "", ""


def call_openai_responses(
    *,
    input_text: str,
    instructions: str,
    config: Optional[AIProviderConfig] = None,
    text_format: Optional[dict[str, Any]] = None,
    transport: Optional[Callable[..., Any]] = None,
    ssl_context: Optional[ssl.SSLContext] = None,
) -> AIProviderResult:
    config = config or load_ai_provider_config()
    provider = config.provider
    model = config.model
    api_key = str(os.environ.get("OPENAI_API_KEY", "") or "").strip()
    if not ai_enabled(config):
        if provider != "openai":
            error = "AI provider is set to offline."
        elif not config.enabled:
            error = "AI provider is disabled."
        else:
            error = "OPENAI_API_KEY is missing."
        return AIProviderResult(
            False,
            "",
            None,
            error,
            provider,
            model,
            False,
            fallback_reason=_provider_unavailable_fallback_reason(config, "auto"),
        )

    payload: dict[str, Any] = {
        "model": model,
        "input": input_text,
        "instructions": instructions,
        "max_output_tokens": config.max_output_tokens,
    }
    if text_format:
        payload["text"] = {"format": text_format}

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        body = _transport_request(
            request,
            timeout=config.timeout_seconds,
            transport=transport,
            ssl_context=ssl_context,
        )
        response_json = json.loads(body)
        structured_error, structured_fallback = _openai_structured_failure(response_json)
        if structured_error:
            return AIProviderResult(
                False,
                "",
                None,
                structured_error,
                provider,
                model,
                False,
                fallback_reason=structured_fallback,
            )
        text = parse_response_text(response_json)
        if not text:
            return AIProviderResult(
                False,
                "",
                None,
                "OpenAI response did not contain output text.",
                provider,
                model,
                False,
                fallback_reason="openai_invalid_response",
            )
        return AIProviderResult(True, text, _try_parse_json(text), "", provider, model, True)
    except urllib.error.HTTPError as exc:
        detail = _redact_error(exc.read().decode("utf-8", errors="replace"), api_key)
        return AIProviderResult(
            False,
            "",
            None,
            f"OpenAI HTTP error {exc.code}: {detail}",
            provider,
            model,
            False,
            fallback_reason="openai_http_error",
        )
    except urllib.error.URLError as exc:
        error_text = _redact_error(f"OpenAI request failed: {exc.reason}", api_key)
        fallback_reason = "openai_timeout" if "timed out" in error_text.lower() else "openai_request_error"
        return AIProviderResult(False, "", None, error_text, provider, model, False, fallback_reason=fallback_reason)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        error_text = _redact_error(f"OpenAI request failed: {exc}", api_key)
        fallback_reason = "openai_timeout" if "timed out" in error_text.lower() else "openai_request_error"
        return AIProviderResult(False, "", None, error_text, provider, model, False, fallback_reason=fallback_reason)


def call_deepseek_chat_completions(
    *,
    input_text: str,
    instructions: str,
    config: Optional[AIProviderConfig] = None,
    response_format: Optional[dict[str, Any]] = None,
    transport: Optional[Callable[..., Any]] = None,
    ssl_context: Optional[ssl.SSLContext] = None,
) -> AIProviderResult:
    config = config or load_ai_provider_config()
    provider = config.provider
    model = config.model
    api_key = str(os.environ.get("DEEPSEEK_API_KEY", "") or "").strip()
    if not ai_enabled(config):
        error = _provider_unavailable_reason(config, "auto")
        return AIProviderResult(
            False,
            "",
            None,
            error,
            provider,
            model,
            False,
            fallback_reason=_provider_unavailable_fallback_reason(config, "auto"),
        )

    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": instructions},
            {"role": "user", "content": input_text},
        ],
        "max_tokens": config.max_output_tokens,
        "temperature": 0.2,
        "stream": False,
    }
    if response_format:
        payload["response_format"] = response_format

    base_url = (config.base_url or DEFAULT_DEEPSEEK_BASE_URL).rstrip("/")
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        body = _transport_request(
            request,
            timeout=config.timeout_seconds,
            transport=transport,
            ssl_context=ssl_context,
        )
        response_json = json.loads(body)
        structured_error, structured_fallback = _deepseek_structured_failure(response_json)
        if structured_error:
            return AIProviderResult(
                False,
                "",
                None,
                structured_error,
                provider,
                model,
                False,
                fallback_reason=structured_fallback,
            )
        text = parse_deepseek_chat_text(response_json)
        if not text:
            return AIProviderResult(
                False,
                "",
                None,
                "DeepSeek response did not contain message content.",
                provider,
                model,
                False,
                fallback_reason="deepseek_invalid_json",
            )
        return AIProviderResult(True, text, _try_parse_json(text), "", provider, model, True)
    except urllib.error.HTTPError as exc:
        detail = _redact_error(exc.read().decode("utf-8", errors="replace"), api_key)
        return AIProviderResult(
            False,
            "",
            None,
            f"DeepSeek HTTP error {exc.code}: {detail}",
            provider,
            model,
            False,
            fallback_reason="deepseek_http_error",
        )
    except urllib.error.URLError as exc:
        error_text = _redact_error(f"DeepSeek request failed: {exc.reason}", api_key)
        fallback_reason = "deepseek_timeout" if "timed out" in error_text.lower() else "deepseek_request_error"
        return AIProviderResult(False, "", None, error_text, provider, model, False, fallback_reason=fallback_reason)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        error_text = _redact_error(f"DeepSeek request failed: {exc}", api_key)
        fallback_reason = "deepseek_timeout" if "timed out" in error_text.lower() else "deepseek_request_error"
        return AIProviderResult(False, "", None, error_text, provider, model, False, fallback_reason=fallback_reason)


def _clone_fallback(value: Any) -> Any:
    if callable(value):
        value = value()
    return copy.deepcopy(value)


def _shape_required_fields(fallback_data: Any) -> set[str]:
    if isinstance(fallback_data, dict):
        return {key for key in fallback_data.keys() if not str(key).startswith("_")}
    return set()


def _missing_required_fields(candidate: Any, fallback_data: Any) -> list[str]:
    if isinstance(fallback_data, dict):
        if not isinstance(candidate, dict):
            return sorted(_shape_required_fields(fallback_data))
        return sorted(field for field in _shape_required_fields(fallback_data) if field not in candidate)
    return []


def _openai_text_format_for_task(task_name: str) -> dict[str, Any]:
    if task_name in AI_TASK_SCHEMAS:
        return build_openai_text_format(task_name)
    return {"type": "json_object"}


def _invalid_json_fallback_code(provider: str) -> str:
    if provider == "deepseek":
        return "deepseek_invalid_json"
    if provider == "openai":
        return "openai_invalid_json"
    return "ai_invalid_json"


def _schema_fallback_code(provider: str, task_name: str, validation_result: dict[str, Any]) -> str:
    if task_name == "app_file_generation":
        validation_detail = validation_result.get("validation_detail") or {}
        failure_code = str(validation_detail.get("failure_code") or "").strip()
        if failure_code:
            return failure_code
    if provider == "deepseek":
        return "deepseek_schema_invalid"
    if provider == "openai":
        return "openai_schema_invalid"
    return "ai_schema_invalid"


def _is_retryable_app_provider_failure(result: AIProviderResult) -> bool:
    fallback_reason = str(result.fallback_reason or "").strip().lower()
    error_text = str(result.error or "").strip().lower()
    if fallback_reason.endswith("_timeout") or fallback_reason.endswith("_request_error"):
        return True
    if fallback_reason.endswith("_invalid_response"):
        return True
    if fallback_reason in {"openai_invalid_json", "deepseek_invalid_json", "ai_invalid_json"}:
        return True
    if fallback_reason.endswith("_http_error"):
        transient_markers = (" 408", " 409", " 429", " 500", " 502", " 503", " 504", "rate limit", "temporar", "timeout")
        return any(marker in error_text for marker in transient_markers)
    return False


def _app_validation_retry_reason(validation_result: dict[str, Any]) -> str:
    if not validation_result or validation_result.get("ok"):
        return ""
    missing_fields = [str(item or "") for item in (validation_result.get("missing_fields") or [])]
    wrong_type_fields = [str(item or "") for item in (validation_result.get("wrong_type_fields") or [])]
    if not missing_fields and not wrong_type_fields:
        return ""
    non_retryable_markers = (
        "browser_network_calls",
        "browser_provider_calls",
        "external_urls",
        "secret_pattern",
    )
    if any(any(marker in field for marker in non_retryable_markers) for field in wrong_type_fields):
        return ""
    if any(field.endswith(".filename") or field == "filename" for field in wrong_type_fields):
        return ""
    if any(field.startswith("files:shape_contract:") for field in wrong_type_fields):
        return "app_shape"
    return "json_shape"


def _app_file_generation_retry_instructions(instructions: str, retry_reason: str, validation_result: Optional[dict[str, Any]] = None) -> str:
    reason_label = {
        "provider_transient": "the provider did not return a usable response",
        "invalid_json": "the response was not parseable JSON",
        "json_shape": "the JSON shape did not match the app_file_generation contract",
        "app_shape": "the app files missed required canonical app surfaces",
    }.get(retry_reason, "the first app_file_generation attempt could not be accepted")
    missing_surfaces = []
    if validation_result:
        validation_detail = validation_result.get("validation_detail") or {}
        missing_surfaces = [str(item or "").strip() for item in (validation_detail.get("app_shape_failures") or []) if str(item or "").strip()]
    missing_surface_note = ""
    if missing_surfaces:
        compact = ", ".join(missing_surfaces[:12])
        missing_surface_note = f"\n        - Fix these missing required surfaces: {compact}."
        if any("budget_calculator" in item or "budget_calculator" in item.replace(" ", "_") for item in missing_surfaces):
            missing_surface_note += (
                "\n        - For budget_calculator repairs, app.js must explicitly read the income and expense DOM values before calculating, "
                "for example document.getElementById('budget-income').value and document.getElementById('budget-food').value, "
                "then update budget-savings, budget-breakdown, and budget-recommendation."
            )
        if any("flashcard_helper" in item or "flashcard_helper" in item.replace(" ", "_") for item in missing_surfaces):
            missing_surface_note += (
                "\n        - For flashcard_helper repairs, index.html must visibly include this exact limitation note near the flashcard UI: "
                "\"This prototype builds study cards locally from your notes. It does not call live AI or external services inside the browser.\" "
                "Do not rely on README.md or TEST_PLAN.md alone."
            )
    repair_note = f"""

        Retry repair for app_file_generation:
        - Retry because {reason_label}.
        - Return exactly one valid JSON object and nothing else.
        - Match the app_file_generation schema exactly.
        - Include exactly these files: index.html, style.css, app.js, README.md, TEST_PLAN.md.
        - Ensure index.html links style.css and app.js.
        - Ensure app.js contains real local browser interaction behavior.
        {missing_surface_note}
        - Do not include external URLs, network calls, provider calls, API keys, markdown fences, or placeholder-only files.
        """
    return (str(instructions or "").strip() + "\n" + repair_note.strip()).strip()


def generate_json_with_ai(
    *,
    task_name: str,
    instructions: str,
    user_input: str,
    expected_schema_description: str,
    fallback_factory: Any,
    config: Optional[AIProviderConfig] = None,
    provider_callable: Optional[Callable[..., AIProviderResult]] = None,
    generation_mode: str = "auto",
    validator: Optional[Callable[[Any], dict[str, Any]]] = None,
    route_used: bool = False,
    route_id: str = "",
    unavailable_error: str = "",
    unavailable_fallback_reason: str = "",
) -> tuple[Any, AIProviderResult]:
    config = config or load_ai_provider_config()
    requested_mode = normalize_generation_mode(generation_mode)
    fallback_data = _clone_fallback(fallback_factory)
    input_size_chars = len(str(instructions or "")) + len(str(user_input or "")) + len(str(expected_schema_description or ""))
    estimated_input_tokens = estimate_tokens_from_chars(input_size_chars)

    def _estimate_cost(provider_name: str, model_name: str, output_chars: int) -> tuple[int, float | None]:
        estimated_output_tokens = estimate_tokens_from_chars(output_chars)
        estimate = estimate_ai_cost(provider_name, model_name, estimated_input_tokens, estimated_output_tokens)
        return estimated_output_tokens, estimate.get("estimated_cost_usd")

    if requested_mode == "offline" or not ai_enabled(config):
        reason = unavailable_error or _provider_unavailable_reason(config, requested_mode)
        fallback_reason = unavailable_fallback_reason or _provider_unavailable_fallback_reason(config, requested_mode)
        estimated_output_tokens, estimated_cost_usd = _estimate_cost(config.provider, config.model, 0)
        return fallback_data, AIProviderResult(
            False,
            "",
            None,
            reason,
            config.provider,
            config.model,
            False,
            generation_mode_requested=requested_mode,
            fallback_reason=fallback_reason,
            input_size_chars=input_size_chars,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_cost_usd=estimated_cost_usd,
            task_name=task_name,
            route_used=route_used,
            route_id=route_id,
        )

    provider = provider_callable or (call_deepseek_chat_completions if config.provider == "deepseek" else call_openai_responses)
    retry_warnings: list[str] = []
    attempt = 0
    next_retry_reason = ""
    next_retry_validation_result: dict[str, Any] | None = None

    def _call_provider_once(instructions_text: str) -> AIProviderResult:
        started = time.monotonic()
        provider_kwargs: dict[str, Any] = {
            "input_text": user_input,
            "instructions": instructions_text.strip(),
            "config": config,
        }
        if config.provider == "deepseek":
            provider_kwargs["response_format"] = {"type": "json_object"}
        else:
            provider_kwargs["text_format"] = _openai_text_format_for_task(task_name)
        result = provider(**provider_kwargs)
        duration_ms = int((time.monotonic() - started) * 1000)
        result = _annotate_result(
            result,
            generation_mode_requested=requested_mode,
            duration_ms=duration_ms,
            input_size_chars=input_size_chars,
            output_size_chars=len(str(result.text or "")),
            estimated_input_tokens=estimated_input_tokens,
            task_name=task_name,
            route_used=route_used,
            route_id=route_id,
        )
        estimated_output_tokens, estimated_cost_usd = _estimate_cost(
            result.provider or config.provider,
            result.model or config.model,
            len(str(result.text or "")),
        )
        return _annotate_result(
            result,
            generation_mode_requested=requested_mode,
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=estimated_output_tokens,
            estimated_cost_usd=estimated_cost_usd,
            task_name=task_name,
            route_used=route_used,
            route_id=route_id,
        )

    def _merge_warnings(*groups: Any) -> tuple[str, ...]:
        merged: list[str] = []
        for group in groups:
            for warning in group or []:
                text = str(warning or "").strip()
                if text and text not in merged:
                    merged.append(text)
        return tuple(merged)

    while True:
        attempt += 1
        instructions_for_attempt = instructions
        if next_retry_reason:
            retry_warnings.append(f"app_file_generation_retry:{next_retry_reason}")
            instructions_for_attempt = _app_file_generation_retry_instructions(instructions, next_retry_reason, next_retry_validation_result)
        provider_result = _call_provider_once(instructions_for_attempt)

        if not provider_result.ok:
            if task_name == "app_file_generation" and attempt == 1 and _is_retryable_app_provider_failure(provider_result):
                next_retry_reason = "provider_transient"
                continue
            return fallback_data, _annotate_result(
                provider_result,
                generation_mode_requested=requested_mode,
                fallback_reason=provider_result.fallback_reason or provider_result.error,
                warnings=_merge_warnings(provider_result.warnings, retry_warnings),
                task_name=task_name,
                route_used=route_used,
                route_id=route_id,
            )

        parsed_json = provider_result.parsed_json
        if parsed_json is None:
            parsed_json = _try_parse_json(provider_result.text)
        if parsed_json is None:
            if task_name == "app_file_generation" and attempt == 1:
                next_retry_reason = "invalid_json"
                continue
            fallback_reason = _invalid_json_fallback_code(provider_result.provider)
            return fallback_data, AIProviderResult(
                False,
                provider_result.text,
                None,
                "AI output was not valid JSON.",
                provider_result.provider,
                provider_result.model,
                False,
                generation_mode_requested=requested_mode,
                fallback_reason=fallback_reason,
                duration_ms=provider_result.duration_ms,
                input_size_chars=input_size_chars,
                output_size_chars=len(str(provider_result.text or "")),
                estimated_input_tokens=estimated_input_tokens,
                estimated_output_tokens=provider_result.estimated_output_tokens,
                estimated_cost_usd=provider_result.estimated_cost_usd,
                warnings=_merge_warnings(provider_result.warnings, retry_warnings),
                task_name=task_name,
                route_used=route_used,
                route_id=route_id,
            )

        validation_result = validator(parsed_json) if validator else None
        if validation_result is None:
            if task_name in AI_TASK_SCHEMAS:
                validation_result = validate_ai_payload(task_name, parsed_json)
            else:
                missing_fields = _missing_required_fields(parsed_json, fallback_data)
                validation_result = {
                    "ok": not missing_fields,
                    "missing_fields": missing_fields,
                    "wrong_type_fields": [],
                    "warnings": [],
                    "sanitized_payload": parsed_json,
                }
        retry_reason = _app_validation_retry_reason(validation_result) if task_name == "app_file_generation" else ""
        if not validation_result.get("ok") and attempt == 1 and retry_reason:
            next_retry_reason = retry_reason
            next_retry_validation_result = validation_result
            continue
        if not validation_result.get("ok"):
            reasons: list[str] = []
            missing_fields = validation_result.get("missing_fields") or []
            wrong_type_fields = validation_result.get("wrong_type_fields") or []
            validation_detail = validation_result.get("validation_detail") or {}
            if missing_fields:
                reasons.append("missing required fields: " + ", ".join(missing_fields))
            if wrong_type_fields:
                reasons.append("wrong field types: " + ", ".join(wrong_type_fields))
            if validation_detail.get("failure_code"):
                reasons.append("validation code: " + str(validation_detail.get("failure_code")))
            fallback_reason = "AI output failed schema validation."
            if reasons:
                fallback_reason = "AI output failed schema validation: " + "; ".join(reasons)
            fallback_code = _schema_fallback_code(provider_result.provider, task_name, validation_result)
            return fallback_data, AIProviderResult(
                False,
                provider_result.text,
                parsed_json,
                fallback_reason,
                provider_result.provider,
                provider_result.model,
                False,
                generation_mode_requested=requested_mode,
                fallback_reason=fallback_code,
                duration_ms=provider_result.duration_ms,
                input_size_chars=input_size_chars,
                output_size_chars=len(str(provider_result.text or "")),
                estimated_input_tokens=estimated_input_tokens,
                estimated_output_tokens=provider_result.estimated_output_tokens,
                estimated_cost_usd=provider_result.estimated_cost_usd,
                warnings=_merge_warnings(validation_result.get("warnings"), retry_warnings),
                task_name=task_name,
                route_used=route_used,
                route_id=route_id,
                validation_details=validation_detail,
            )

        sanitized_payload = validation_result.get("sanitized_payload")
        if sanitized_payload is None:
            sanitized_payload = parsed_json
        return sanitized_payload, AIProviderResult(
            True,
            provider_result.text,
            sanitized_payload,
            "",
            provider_result.provider,
            provider_result.model,
            True,
            generation_mode_requested=requested_mode,
            duration_ms=provider_result.duration_ms,
            input_size_chars=input_size_chars,
            output_size_chars=len(str(provider_result.text or "")),
            estimated_input_tokens=estimated_input_tokens,
            estimated_output_tokens=provider_result.estimated_output_tokens,
            estimated_cost_usd=provider_result.estimated_cost_usd,
            warnings=_merge_warnings(validation_result.get("warnings"), retry_warnings),
            task_name=task_name,
            route_used=route_used,
            route_id=route_id,
        )


def fake_provider_result(
    *,
    text: str = "",
    parsed_json: Any = None,
    error: str = "",
    ok: bool = True,
    provider: str = "openai",
    model: str = DEFAULT_OPENAI_MODEL,
    used_ai: bool = True,
    generation_mode_requested: str = "auto",
    fallback_reason: str = "",
    duration_ms: int = 0,
    input_size_chars: int = 0,
    output_size_chars: int = 0,
    estimated_input_tokens: int = 0,
    estimated_output_tokens: int = 0,
    estimated_cost_usd: float | None = None,
    warnings: tuple[str, ...] = (),
    task_name: str = "",
    validation_details: Optional[dict[str, Any]] = None,
) -> AIProviderResult:
    return AIProviderResult(
        ok=ok,
        text=text,
        parsed_json=parsed_json,
        error=error,
        provider=provider,
        model=model,
        used_ai=used_ai,
        generation_mode_requested=generation_mode_requested,
        fallback_reason=fallback_reason,
        duration_ms=duration_ms,
        input_size_chars=input_size_chars,
        output_size_chars=output_size_chars or len(str(text or "")),
        estimated_input_tokens=estimated_input_tokens,
        estimated_output_tokens=estimated_output_tokens,
        estimated_cost_usd=estimated_cost_usd,
        warnings=warnings,
        task_name=task_name,
        validation_details=dict(validation_details or {}),
    )
