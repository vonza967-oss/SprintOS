"""Deterministic artifact selection helpers."""

from __future__ import annotations

AI_KEYWORDS = ("ai ", " ai", "prompt", "text generation", "writing", "summariz", "assistant", "chatbot", "rewrite", "draft")
CALCULATOR_KEYWORDS = ("calculator", "score", "pricing", "budget", "estimate", "compare", "roi", "rank")
QUIZ_KEYWORDS = ("quiz", "recommender", "picker", "onboarding", "diagnostic", "assessment")
APP_KEYWORDS = ("app", "software", "tool", "saas")
TRANSFORM_KEYWORDS = ("generate", "organize", "plan", "convert", "improve", "summar", "write", "draft", "notes")
COMPLEXITY_KEYWORDS = (
    "marketplace",
    "multi-tenant",
    "multitenant",
    "social network",
    "enterprise",
    "real-time",
    "realtime",
    "workflow engine",
    "operating system",
    "agent platform",
    "crm",
    "erp",
)
LOCAL_APP_KEYWORDS = ("app", "software", "tool", "saas", "dashboard", "platform")


def has_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def auto_select_prototype_type(text: str) -> str:
    lowered = str(text or "").lower()
    if has_any_keyword(lowered, CALCULATOR_KEYWORDS):
        return "calculator"
    if has_any_keyword(lowered, QUIZ_KEYWORDS):
        return "quiz_funnel"
    if has_any_keyword(lowered, AI_KEYWORDS):
        return "ai_text_tool"
    if has_any_keyword(lowered, APP_KEYWORDS):
        return "ai_text_tool" if has_any_keyword(lowered, TRANSFORM_KEYWORDS) else "landing_page"
    return "landing_page"


def project_is_complex(text: str) -> bool:
    return has_any_keyword(str(text or "").lower(), COMPLEXITY_KEYWORDS)


def project_looks_like_local_app(text: str) -> bool:
    return has_any_keyword(str(text or "").lower(), LOCAL_APP_KEYWORDS)


def auto_select_build_target(text: str, prototype_type: str, pipeline_goal: str) -> str:
    if prototype_type == "ai_text_tool":
        return "ai_tool_stub"
    if pipeline_goal in {"validate_fast", "public_static_test"}:
        return "static_app"
    if project_is_complex(text):
        return "codex_repo_brief"
    if project_looks_like_local_app(text):
        return "python_stdlib_app"
    return "static_app"
