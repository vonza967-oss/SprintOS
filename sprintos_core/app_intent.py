"""Deterministic Create App intent review helpers."""

from __future__ import annotations

import re
from typing import Any


READY_TO_GENERATE = "ready_to_generate"
NEEDS_CLARIFICATION = "needs_clarification"
GENERATE_WITH_ASSUMPTIONS_AVAILABLE = "generate_with_assumptions_available"

_FORBIDDEN_QUESTION_TOPICS = (
    "deployment",
    "deploy",
    "billing",
    "payment",
    "auth",
    "authentication",
    "login",
    "cloud",
    "sync",
    "github",
    "production",
    "infrastructure",
)

_FIELD_WORDS = (
    "field",
    "fields",
    "status",
    "date",
    "notes",
    "note",
    "lead",
    "leads",
    "client",
    "clients",
    "customer",
    "customers",
    "task",
    "tasks",
    "inventory",
    "quantity",
    "category",
    "income",
    "expense",
    "budget",
    "price",
    "cost",
    "calendar",
    "content",
    "follow-up",
    "follow up",
)

_WORKFLOW_WORDS = (
    "track",
    "manage",
    "calculate",
    "compare",
    "score",
    "plan",
    "schedule",
    "organize",
    "prioritize",
    "follow-up",
    "follow up",
    "remind",
    "enter",
    "add",
    "update",
)

_OUTPUT_WORDS = (
    "dashboard",
    "summary",
    "report",
    "list",
    "calendar",
    "breakdown",
    "recommendation",
    "score",
    "status",
    "pipeline",
)

_APP_TYPE_HINTS = (
    ("crm", "Mini CRM"),
    ("client", "Client Tracker"),
    ("lead", "Lead Tracker"),
    ("inventory", "Inventory Tracker"),
    ("content calendar", "Content Calendar"),
    ("calendar", "Calendar Planner"),
    ("habit", "Habit Tracker"),
    ("budget", "Budget Calculator"),
    ("expense", "Budget Calculator"),
    ("pricing", "Pricing Calculator"),
    ("roi", "ROI Calculator"),
    ("flashcard", "Study Card Builder"),
    ("study", "Study Card Builder"),
    ("decision", "Decision Matrix"),
    ("tracker", "Tracker"),
    ("dashboard", "Dashboard"),
)


def _clean_text(value: str, limit: int = 280) -> str:
    text = re.sub(r"`+", "", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip(" ,;:") if text else ""


def _title_guess(prompt: str, fallback: str = "Local App") -> str:
    text = _clean_text(prompt, 80)
    text = re.sub(r"^(build|create|make|generate)\s+(me\s+)?(a|an|the)?\s*", "", text, flags=re.I)
    text = re.sub(r"\b(local|browser|app|application|tool|for|my|a|an|the)\b", " ", text, flags=re.I)
    text = re.sub(r"[^A-Za-z0-9\s-]", " ", text)
    words = [word for word in text.split() if len(word) > 1][:4]
    if not words:
        return fallback
    return " ".join(word[:1].upper() + word[1:] for word in words)


def _app_type_guess(prompt: str) -> str:
    lowered = prompt.lower()
    for marker, label in _APP_TYPE_HINTS:
        if marker in lowered:
            return label
    if "business" in lowered:
        return "Business Workflow App"
    return "Local Static App"


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _extract_missing_details(lowered: str) -> list[str]:
    missing: list[str] = []
    if not re.search(r"\b(for|freelancer|student|owner|team|client|customer|user|creator|manager|operator)s?\b", lowered):
        missing.append("target user")
    if not _has_any(lowered, _FIELD_WORDS):
        missing.append("records or fields to track")
    if not _has_any(lowered, _WORKFLOW_WORDS):
        missing.append("primary workflow or action")
    if not _has_any(lowered, _OUTPUT_WORDS):
        missing.append("desired output or dashboard")
    return missing


def _question_set(app_type: str, missing_details: list[str], medium_specific: bool) -> list[str]:
    subject = app_type.lower()
    if "crm" in subject:
        record_label = "Which lead or client fields should the CRM track, such as name, status, next follow-up date, value, and notes?"
        workflow_label = "What is the main CRM action: add a lead, update status, log a follow-up, or review overdue follow-ups?"
    elif "client" in subject:
        record_label = "Which client fields matter first: name, contact, status, next follow-up date, project, value, and notes?"
        workflow_label = "What should happen most often: add a client, update status, schedule follow-up, or review active clients?"
    elif "inventory" in subject:
        record_label = "Which inventory fields should be tracked first: item, quantity, location, reorder point, supplier, and notes?"
        workflow_label = "What is the main inventory action: add stock, update quantity, flag low stock, or review categories?"
    elif "calendar" in subject:
        record_label = "Which content fields should the calendar track: title, channel, status, publish date, owner, and notes?"
        workflow_label = "What is the main calendar action: add an item, move status, filter by week, or review upcoming posts?"
    else:
        record_label = "What records or fields should the app track first?"
        workflow_label = "What is the primary action the user should take in the app?"

    questions = [
        "Who is the target user for the first local prototype?",
        record_label,
        workflow_label,
        "What should the main output show: a list, dashboard summary, status view, recommendation, or export-ready note?",
        "Should the prototype save sample entries in local browser storage between refreshes?",
    ]
    if medium_specific:
        return questions[1:5]
    if not missing_details:
        return []
    return questions[:5]


def _assumptions(app_type: str, prompt: str) -> list[str]:
    subject = app_type.lower()
    if "crm" in subject:
        return [
            "Build a local mini CRM for one user.",
            "Track lead or client name, status, next follow-up date, and notes.",
            "Show a simple dashboard for active leads and overdue follow-ups.",
            "Use local browser storage when useful and keep all data local.",
        ]
    if "client" in subject:
        return [
            "Build a simple local client tracker for one user.",
            "Track client name, status, next follow-up date, project/value, and notes.",
            "Show active clients, overdue follow-ups, and a compact status summary.",
            "Use local browser storage when useful and keep all data local.",
        ]
    if "inventory" in subject:
        return [
            "Build a local inventory tracker for one operator.",
            "Track item name, quantity, category/location, reorder point, and notes.",
            "Highlight low-stock items and show a category summary.",
            "Use local browser storage when useful and keep all data local.",
        ]
    if "calendar" in subject:
        return [
            "Build a local content calendar for one creator or small team.",
            "Track title, channel, status, publish date, and notes.",
            "Show upcoming items and a status summary.",
            "Use local browser storage when useful and keep all data local.",
        ]
    if "business" in prompt.lower():
        return [
            "Build a simple local business workflow tracker for one owner.",
            "Track records with name, status, priority, next action, date, and notes.",
            "Show a dashboard summary and the next items needing attention.",
            "Use local browser storage when useful and keep all data local.",
        ]
    return [
        f"Build a small local {app_type.lower()} for one user.",
        "Track the most important record name, status, date, and notes.",
        "Show a useful list plus a compact summary dashboard.",
        "Use local browser storage when useful and keep all data local.",
    ]


def _answered_followups(answered_followups: Any) -> list[dict[str, str]]:
    if not isinstance(answered_followups, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in answered_followups[:5]:
        if not isinstance(item, dict):
            continue
        question = _clean_text(str(item.get("question") or ""), 220)
        answer = _clean_text(str(item.get("answer") or ""), 360)
        if question and answer:
            cleaned.append({"question": question, "answer": answer})
    return cleaned


def _brief(
    prompt: str,
    status: str,
    app_name: str,
    app_type: str,
    assumptions: list[str],
    answered_followups: list[dict[str, str]],
) -> str:
    lines = [
        f"Create a local browser app for this request: {prompt}",
        f"Intent status: {status}.",
        f"App name guess: {app_name}.",
        f"App type guess: {app_type}.",
    ]
    if assumptions:
        lines.append("Safe assumptions if details are missing:")
        lines.extend(f"- {item}" for item in assumptions)
    if answered_followups:
        lines.append("Answered follow-up details:")
        lines.extend(f"- {item['question']} Answer: {item['answer']}" for item in answered_followups)
    lines.append("Keep the prototype local-first, static, browser-previewable, and focused on one useful workflow.")
    return "\n".join(lines)


def review_app_intent(raw_prompt: str, answered_followups: Any = None, generate_with_assumptions: bool = False) -> dict[str, Any]:
    prompt = _clean_text(raw_prompt, 600)
    lowered = prompt.lower()
    words = re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", lowered)
    word_count = len(words)
    app_type = _app_type_guess(prompt)
    app_name = _title_guess(prompt, fallback=app_type)
    missing_details = _extract_missing_details(lowered)
    has_domain = app_type not in {"Local Static App", "Business Workflow App"} or "business" in lowered
    field_hits = sum(1 for marker in _FIELD_WORDS if marker in lowered)
    workflow_hits = sum(1 for marker in _WORKFLOW_WORDS if marker in lowered)
    output_hits = sum(1 for marker in _OUTPUT_WORDS if marker in lowered)
    specific_list = "," in prompt or " and " in lowered
    very_generic = word_count <= 8 or re.fullmatch(r"(build|create|make)?\s*(me\s*)?(an?\s*)?app(\s+for\s+my\s+business)?\.?", lowered or "") is not None

    score = 0
    score += 2 if has_domain else 0
    score += min(field_hits, 3)
    score += min(workflow_hits, 2)
    score += 1 if output_hits else 0
    score += 1 if specific_list else 0
    score += 1 if word_count >= 12 else 0

    answered = _answered_followups(answered_followups)
    if answered:
        score += min(len(answered), 3)
        for item in answered:
            answer = item["answer"].lower()
            if _has_any(answer, _FIELD_WORDS):
                score += 1
            if _has_any(answer, _WORKFLOW_WORDS):
                score += 1
            if _has_any(answer, _OUTPUT_WORDS):
                score += 1

    if score >= 6 and not very_generic:
        status = READY_TO_GENERATE
    elif has_domain and score >= 3:
        status = GENERATE_WITH_ASSUMPTIONS_AVAILABLE
    else:
        status = NEEDS_CLARIFICATION
    if answered and score >= 5:
        status = READY_TO_GENERATE
    if generate_with_assumptions and status == NEEDS_CLARIFICATION:
        status = GENERATE_WITH_ASSUMPTIONS_AVAILABLE

    medium_specific = status == GENERATE_WITH_ASSUMPTIONS_AVAILABLE
    questions = _question_set(app_type, missing_details, medium_specific)
    if status == READY_TO_GENERATE and not answered:
        questions = []
    questions = [question for question in questions if not any(topic in question.lower() for topic in _FORBIDDEN_QUESTION_TOPICS)][:5]
    if status != READY_TO_GENERATE and len(questions) < 3:
        for fallback in _question_set(app_type, ["target user"], False):
            if fallback not in questions and not any(topic in fallback.lower() for topic in _FORBIDDEN_QUESTION_TOPICS):
                questions.append(fallback)
            if len(questions) >= 3:
                break

    assumptions = _assumptions(app_type, prompt)
    confidence = min(0.95, max(0.2, 0.28 + (score * 0.09)))
    if status == NEEDS_CLARIFICATION:
        confidence = min(confidence, 0.56)
    elif status == GENERATE_WITH_ASSUMPTIONS_AVAILABLE:
        confidence = min(max(confidence, 0.52), 0.74)

    return {
        "status": status,
        "app_name_guess": app_name,
        "app_type_guess": app_type,
        "confidence": round(confidence, 2),
        "missing_details": missing_details,
        "assumptions": assumptions,
        "follow_up_questions": questions[:5],
        "answered_followups": answered,
        "enriched_generation_brief": _brief(prompt, status, app_name, app_type, assumptions if status != READY_TO_GENERATE or generate_with_assumptions else [], answered),
        "can_generate_with_assumptions": True,
    }


def app_intent_report_summary(review: dict[str, Any]) -> dict[str, Any]:
    """Return a compact version safe for generated reports."""
    return {
        "status": str(review.get("status") or ""),
        "app_name_guess": str(review.get("app_name_guess") or ""),
        "app_type_guess": str(review.get("app_type_guess") or ""),
        "confidence": review.get("confidence") or 0,
        "missing_details": list(review.get("missing_details") or []),
        "follow_up_questions": list(review.get("follow_up_questions") or [])[:5],
        "can_generate_with_assumptions": bool(review.get("can_generate_with_assumptions")),
    }
