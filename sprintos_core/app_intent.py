"""Deterministic Create App intent review helpers."""

from __future__ import annotations

import re
from typing import Any

from .verification_utils import has_budget_calculator_signal


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
    "objective",
    "objectives",
    "activity",
    "activities",
    "material",
    "materials",
    "homework",
    "lead",
    "leads",
    "client",
    "clients",
    "customer",
    "customers",
    "task",
    "tasks",
    "owner",
    "deadline",
    "service",
    "appointment",
    "appointments",
    "project",
    "vendor",
    "vendors",
    "workload",
    "readiness",
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
    "book",
    "booking",
    "checklist",
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
    "schedule",
    "breakdown",
    "recommendation",
    "score",
    "status",
    "pipeline",
    "progress",
    "overview",
)

_APP_TYPE_HINTS = (
    ("crm", "Mini CRM"),
    ("client", "Client Tracker"),
    ("lead", "Lead Tracker"),
    ("inventory", "Inventory Tracker"),
    ("content calendar", "Content Calendar"),
    ("calendar", "Calendar Planner"),
    ("habit", "Habit Tracker"),
    ("pricing", "Pricing Calculator"),
    ("roi", "ROI Calculator"),
    ("flashcard", "Study Card Builder"),
    ("study", "Study Card Builder"),
    ("decision", "Decision Matrix"),
    ("booking", "Booking Tracker"),
    ("checklist", "Checklist Tracker"),
    ("lesson", "Lesson Planner"),
    ("event", "Event Planner"),
    ("project", "Project Tracker"),
    ("planner", "Planner"),
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
    if has_budget_calculator_signal(lowered):
        return "Budget Calculator"
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
    if not re.search(r"\b(for|freelancer|student|teacher|barber|agency|owner|team|client|customer|user|creator|manager|operator)s?\b", lowered):
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


def _dedupe(items: list[str], limit: int = 6) -> list[str]:
    seen: set[str] = set()
    cleaned: list[str] = []
    for item in items:
        text = _clean_text(item, 120)
        key = text.lower()
        if text and key not in seen:
            cleaned.append(text)
            seen.add(key)
        if len(cleaned) >= limit:
            break
    return cleaned


def _combined_detail_text(prompt: str, answered_followups: list[dict[str, str]], assumptions: list[str]) -> str:
    parts = [prompt]
    parts.extend(item["answer"] for item in answered_followups)
    parts.extend(assumptions)
    return " ".join(parts)


def _target_user(prompt: str, app_type: str, answered_followups: list[dict[str, str]]) -> str:
    for item in answered_followups:
        if "target user" in item["question"].lower() or item["question"].lower().startswith("who "):
            return _clean_text(item["answer"], 140)
    match = re.search(r"\bfor\s+(?:a|an|the|my)?\s*([^.,;]+)", prompt, flags=re.I)
    if match:
        target = re.split(r"\b(to|that|with|where|who|which)\b", match.group(1), maxsplit=1, flags=re.I)[0]
        target = _clean_text(target, 120)
        if target and target.lower() not in {"my business", "business", "app"}:
            return target
    subject = app_type.lower()
    if "crm" in subject:
        return "Freelancer or small-business owner managing leads"
    if "client" in subject:
        return "Solo operator managing clients"
    if "inventory" in subject:
        return "Small-shop operator"
    if "calendar" in subject:
        return "Content creator or small team"
    if "habit" in subject:
        return "One person tracking daily habits"
    if "budget" in subject:
        return "Person planning a monthly budget"
    if "study" in subject:
        return "Student reviewing study notes"
    if "business" in prompt.lower():
        return "Small-business owner"
    return "One local prototype user"


def _domain_defaults(app_type: str, prompt: str) -> dict[str, list[str]]:
    text = f"{app_type} {prompt}".lower()
    if "crm" in text or "lead" in text:
        return {
            "records": ["Leads or clients"],
            "fields": ["Name", "Status", "Next follow-up date", "Value", "Notes"],
            "actions": ["Add lead", "Update status", "Log follow-up", "Review overdue follow-ups"],
            "outputs": ["Lead list", "Pipeline summary", "Overdue follow-up view"],
            "sections": ["Lead entry", "Pipeline dashboard", "Follow-up list"],
        }
    if "client" in text:
        return {
            "records": ["Clients"],
            "fields": ["Name", "Contact", "Status", "Next follow-up date", "Project value", "Notes"],
            "actions": ["Add client", "Update status", "Schedule follow-up", "Review active clients"],
            "outputs": ["Client list", "Status summary", "Overdue follow-up view"],
            "sections": ["Client entry", "Client dashboard", "Follow-up list"],
        }
    if "inventory" in text:
        return {
            "records": ["Inventory items"],
            "fields": ["Item name", "Quantity", "Category or location", "Reorder point", "Notes"],
            "actions": ["Add item", "Update quantity", "Flag low stock", "Review categories"],
            "outputs": ["Inventory list", "Low-stock alerts", "Category summary"],
            "sections": ["Item entry", "Inventory table", "Low-stock summary"],
        }
    if "calendar" in text or "content" in text:
        return {
            "records": ["Content items"],
            "fields": ["Title", "Channel", "Status", "Publish date", "Notes"],
            "actions": ["Add content item", "Update status", "Review upcoming posts"],
            "outputs": ["Weekly overview", "Status summary", "Upcoming content list"],
            "sections": ["Content entry", "Calendar overview", "Status board"],
        }
    if "habit" in text:
        return {
            "records": ["Habits"],
            "fields": ["Habit name", "Completion state", "Date", "Notes"],
            "actions": ["Add habit", "Mark completion", "Reset day"],
            "outputs": ["Habit list", "Daily progress summary"],
            "sections": ["Habit entry", "Today list", "Progress summary"],
        }
    if "budget calculator" in text or has_budget_calculator_signal(text):
        return {
            "records": ["Monthly budget inputs"],
            "fields": ["Income", "Expense category", "Expense amount", "Notes"],
            "actions": ["Enter income", "Enter expenses", "Calculate budget"],
            "outputs": ["Savings result", "Spending breakdown", "Recommendation"],
            "sections": ["Budget inputs", "Snapshot results", "Recommendation"],
        }
    if "pricing" in text or "roi" in text:
        return {
            "records": ["Pricing scenario"],
            "fields": ["Price", "Unit cost", "Customer count", "Investment"],
            "actions": ["Enter scenario", "Calculate ROI", "Compare recommendation"],
            "outputs": ["Revenue summary", "Margin breakdown", "Payback recommendation"],
            "sections": ["Scenario inputs", "ROI results", "Assumptions"],
        }
    if "study" in text or "flashcard" in text:
        return {
            "records": ["Study notes"],
            "fields": ["Notes", "Question", "Answer", "Card progress"],
            "actions": ["Paste notes", "Build flashcards", "Review cards"],
            "outputs": ["Flashcard list", "Review progress"],
            "sections": ["Notes input", "Card output", "Review controls"],
        }
    if "decision" in text:
        return {
            "records": ["Decision options and criteria"],
            "fields": ["Option", "Criterion", "Weight", "Score"],
            "actions": ["Enter options", "Enter criteria", "Compare options"],
            "outputs": ["Ranked list", "Recommendation", "Tradeoff notes"],
            "sections": ["Decision inputs", "Ranking", "Tradeoffs"],
        }
    return {
        "records": ["Local records"],
        "fields": ["Name", "Status", "Priority", "Date", "Notes"],
        "actions": ["Add record", "Update status", "Review next actions"],
        "outputs": ["Record list", "Compact dashboard summary", "Next action view"],
        "sections": ["Entry form", "Main list", "Summary panel"],
    }


def _extra_fields_from_text(text: str) -> list[str]:
    candidates = {
        "email": "Email",
        "phone": "Phone",
        "contact": "Contact",
        "owner": "Owner",
        "deadline": "Deadline",
        "due": "Due date",
        "priority": "Priority",
        "location": "Location",
        "supplier": "Supplier",
        "channel": "Channel",
        "publish date": "Publish date",
        "reorder": "Reorder point",
        "threshold": "Reorder threshold",
        "completion": "Completion state",
    }
    lowered = text.lower()
    return [label for marker, label in candidates.items() if marker in lowered]


def _extra_outputs_from_text(text: str) -> list[str]:
    candidates = {
        "dashboard": "Dashboard",
        "summary": "Summary",
        "status view": "Status view",
        "recommendation": "Recommendation",
        "report": "Report",
        "calendar": "Calendar view",
        "overview": "Overview",
    }
    lowered = text.lower()
    return [label for marker, label in candidates.items() if marker in lowered]


def _local_state_recommendation(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("local storage", "localstorage", "between refreshes", "save sample", "persist")):
        return "Use browser localStorage for sample records so entries survive refreshes."
    return "Use browser-local state only; localStorage is acceptable for sample records when it helps the core workflow."


def build_app_blueprint(
    raw_prompt: str,
    status: str,
    app_name: str,
    app_type: str,
    assumptions: list[str],
    answered_followups: list[dict[str, str]],
) -> dict[str, Any]:
    """Build a deterministic, local-only generation plan from intent review inputs."""
    prompt = _clean_text(raw_prompt, 600)
    detail_text = _combined_detail_text(prompt, answered_followups, assumptions)
    defaults = _domain_defaults(app_type, detail_text)
    assumption_items = list(assumptions)
    target_user = _target_user(detail_text, app_type, answered_followups)
    app_goal = _clean_text(f"Help {target_user} complete one local {app_type.lower()} workflow from input to useful output.", 180)
    primary_workflow = _clean_text(
        " -> ".join((defaults["actions"][0], defaults["actions"][1] if len(defaults["actions"]) > 1 else "Review result", defaults["outputs"][0])),
        180,
    )
    fields = _dedupe(defaults["fields"] + _extra_fields_from_text(detail_text), 8)
    records = _dedupe(defaults["records"], 4)
    actions = _dedupe(defaults["actions"], 6)
    outputs = _dedupe(defaults["outputs"] + _extra_outputs_from_text(detail_text), 6)
    sections = _dedupe(defaults["sections"], 5)
    followups_used = [{"question": item["question"], "answer": item["answer"]} for item in answered_followups]
    limitations = [
        "Local-first static prototype only.",
        "No backend, account system, deployment, billing, provider call, or cloud sync.",
        "Use deterministic browser logic and clearly label mocked or demo behavior.",
    ]
    safety_notes = [
        "Keep all app data in the browser or static files.",
        "Do not include API keys, provider calls, external scripts, or network requests.",
        "Generate exactly index.html, style.css, app.js, README.md, and TEST_PLAN.md.",
    ]
    codex_next_steps = [
        "Test the main input-action-output path locally.",
        "Improve one workflow detail based on tester feedback while keeping the app static and local-first.",
    ]
    brief_lines = [
        f"App Blueprint v1: Build {app_name} as a {app_type}.",
        f"Target user: {target_user}.",
        f"Goal: {app_goal}.",
        f"Primary workflow: {primary_workflow}.",
        f"Main records: {', '.join(records)}.",
        f"Key fields: {', '.join(fields)}.",
        f"Primary actions: {', '.join(actions)}.",
        f"Main outputs: {', '.join(outputs)}.",
        f"Screens or sections: {', '.join(sections)}.",
        f"Local state: {_local_state_recommendation(detail_text)}",
    ]
    if followups_used:
        brief_lines.append("Use answered follow-up details to make the app more specific than the original prompt.")
    if assumption_items:
        brief_lines.append("Explicit assumptions:")
        brief_lines.extend(f"- {item}" for item in assumption_items)
    brief_lines.append("Keep the scope to a small browser-previewable prototype with no external services.")
    return {
        "app_name": app_name,
        "app_type_guess": app_type,
        "target_user": target_user,
        "app_goal": app_goal,
        "primary_workflow": primary_workflow,
        "main_records": records,
        "key_fields": fields,
        "primary_actions": actions,
        "main_outputs": outputs,
        "screens_or_sections": sections,
        "local_state_recommendation": _local_state_recommendation(detail_text),
        "assumptions": list(assumption_items),
        "limitations": limitations,
        "follow_up_answers_used": followups_used,
        "safety_notes": safety_notes,
        "codex_next_steps": codex_next_steps,
        "generation_brief": "\n".join(brief_lines),
    }


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

    brief_assumptions = assumptions if status != READY_TO_GENERATE or generate_with_assumptions else []
    app_blueprint = build_app_blueprint(prompt, status, app_name, app_type, brief_assumptions, answered)
    return {
        "status": status,
        "app_name_guess": app_name,
        "app_type_guess": app_type,
        "confidence": round(confidence, 2),
        "missing_details": missing_details,
        "assumptions": assumptions,
        "follow_up_questions": questions[:5],
        "answered_followups": answered,
        "enriched_generation_brief": _brief(prompt, status, app_name, app_type, brief_assumptions, answered),
        "app_blueprint": app_blueprint,
        "can_generate_with_assumptions": True,
    }


def app_intent_report_summary(review: dict[str, Any]) -> dict[str, Any]:
    """Return a compact version safe for generated reports."""
    blueprint = review.get("app_blueprint") if isinstance(review.get("app_blueprint"), dict) else {}
    return {
        "status": str(review.get("status") or ""),
        "app_name_guess": str(review.get("app_name_guess") or ""),
        "app_type_guess": str(review.get("app_type_guess") or ""),
        "confidence": review.get("confidence") or 0,
        "missing_details": list(review.get("missing_details") or []),
        "follow_up_questions": list(review.get("follow_up_questions") or [])[:5],
        "can_generate_with_assumptions": bool(review.get("can_generate_with_assumptions")),
        "app_blueprint": {
            "app_goal": str(blueprint.get("app_goal") or ""),
            "target_user": str(blueprint.get("target_user") or ""),
            "main_records": list(blueprint.get("main_records") or [])[:4],
            "primary_actions": list(blueprint.get("primary_actions") or [])[:4],
            "main_outputs": list(blueprint.get("main_outputs") or [])[:4],
            "assumption_count": len(list(blueprint.get("assumptions") or [])),
        } if blueprint else {},
    }
