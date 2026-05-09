"""Verification-oriented pure helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

from .constants import VAGUE_NEXT_ACTION_PREFIXES

SAFE_APP_ROUTE_PREFIXES = (
    "/api/",
    "/prototype/",
    "/deploy_pack/",
    "/build_pack/",
    "/pipeline/",
    "/quick_launch/",
    "/verification/",
)


def metadata_has_unsafe_path(value: Any) -> bool:
    if isinstance(value, dict):
        return any(metadata_has_unsafe_path(item) for item in value.values())
    if isinstance(value, list):
        return any(metadata_has_unsafe_path(item) for item in value)
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    normalized = text.replace("\\", "/")
    if normalized == ".." or "../" in normalized:
        return True
    if re.match(r"^[A-Za-z]:/", normalized):
        return True
    if any(normalized.startswith(prefix) for prefix in SAFE_APP_ROUTE_PREFIXES):
        return False
    return normalized.startswith("/")


def external_network_markers(file_name: str, text: str) -> List[str]:
    blockers: List[str] = []
    if "fetch(" in text:
        blockers.append(f"{file_name} contains fetch(), which breaks the boring static-only requirement.")
    if "XMLHttpRequest" in text:
        blockers.append(f"{file_name} contains XMLHttpRequest, which implies a network dependency.")
    if "sendBeacon" in text:
        blockers.append(f"{file_name} contains sendBeacon, which implies analytics/network calls.")
    for match in re.finditer(r"https?://[^\s\"')>]+", text):
        url = match.group(0).lower()
        if "127.0.0.1" in url or "localhost" in url:
            continue
        blockers.append(f"{file_name} references external URL {match.group(0)}.")
    return blockers


def is_vague_next_action(text: str, prefixes: Iterable[str] = VAGUE_NEXT_ACTION_PREFIXES) -> bool:
    cleaned = " ".join(str(text or "").split()).strip().lower()
    if not cleaned:
        return True
    return any(cleaned.startswith(prefix) for prefix in prefixes)


APP_SPECIFIC_VERIFY_SHAPES = {
    "business_idea_scorer": "business idea scorer",
    "budget_calculator": "budget calculator",
    "flashcard_helper": "flashcard helper",
    "quiz_recommender": "quiz recommender",
    "waitlist_page": "landing page",
}


def _lower_join(*values: Any) -> str:
    return " ".join(str(value or "") for value in values).lower()


def _has_any(text: str, markers: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in markers)


def _html_has_tag(html_text: str, tag_name: str) -> bool:
    return bool(re.search(rf"<\s*{re.escape(tag_name)}\b", html_text, flags=re.I))


def _html_has_id(html_text: str, element_id: str) -> bool:
    return bool(re.search(rf"\bid\s*=\s*['\"]{re.escape(element_id)}['\"]", html_text, flags=re.I))


def _html_has_data_marker(html_text: str, marker: str) -> bool:
    return bool(re.search(rf"\bdata-template-marker\s*=\s*['\"]{re.escape(marker)}['\"]", html_text, flags=re.I))


def _html_id_has_data_marker(html_text: str, element_id: str, marker: str) -> bool:
    for match in re.finditer(r"<\s*[\w:-]+\b[^>]*>", html_text, flags=re.I):
        tag = match.group(0)
        if _html_has_id(tag, element_id) and _html_has_data_marker(tag, marker):
            return True
    return False


def _html_number_input_count(html_text: str) -> int:
    count = 0
    for match in re.finditer(r"<\s*input\b[^>]*>", html_text, flags=re.I):
        tag = match.group(0)
        if re.search(r"\btype\s*=\s*['\"]?number\b", tag, flags=re.I):
            count += 1
    return count


def _html_number_input_tags(html_text: str) -> List[str]:
    tags: List[str] = []
    for match in re.finditer(r"<\s*input\b[^>]*>", html_text, flags=re.I):
        tag = match.group(0).lower()
        if re.search(r"\btype\s*=\s*['\"]?number\b", tag, flags=re.I):
            tags.append(tag)
    return tags


def _js_string_pattern(value: str) -> str:
    return rf"['\"]{re.escape(value)}['\"]"


def _js_get_element_pattern(element_id: str) -> str:
    return rf"getElementById\(\s*{_js_string_pattern(element_id)}\s*\)"


def _js_query_selector_pattern(element_id: str) -> str:
    return rf"querySelector\(\s*['\"]#{re.escape(element_id)}['\"]\s*\)"


def _js_element_lookup_pattern(element_id: str) -> str:
    return rf"(?:{_js_get_element_pattern(element_id)}|{_js_query_selector_pattern(element_id)})"


def _js_element_variable_names(app_js: str, element_id: str) -> List[str]:
    pattern = rf"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*document\.{_js_element_lookup_pattern(element_id)}"
    return [match.group(1) for match in re.finditer(pattern, app_js)]


def _js_reads_element_value(app_js: str, element_id: str) -> bool:
    direct = rf"document\.{_js_element_lookup_pattern(element_id)}\s*\.\s*value\b"
    if re.search(direct, app_js):
        return True
    for variable in _js_element_variable_names(app_js, element_id):
        if re.search(rf"\b{re.escape(variable)}\s*\.\s*value\b", app_js):
            return True
    generic_dom_value_read = r"document\.(?:getElementById|querySelector)\(\s*[A-Za-z_$][\w$]*\s*\)\s*\.\s*value\b"
    return bool(re.search(_js_string_pattern(element_id), app_js) and re.search(generic_dom_value_read, app_js))


def _js_updates_element(app_js: str, element_id: str, properties: Iterable[str] = ("textContent", "innerHTML")) -> bool:
    property_pattern = "|".join(re.escape(prop) for prop in properties)
    direct = rf"document\.{_js_element_lookup_pattern(element_id)}\s*\.\s*(?:{property_pattern})\s*="
    if re.search(direct, app_js):
        return True
    direct_mutator = rf"document\.{_js_element_lookup_pattern(element_id)}\s*\.\s*(?:appendChild|replaceChildren|insertAdjacentHTML)\s*\("
    if re.search(direct_mutator, app_js):
        return True
    for variable in _js_element_variable_names(app_js, element_id):
        if re.search(rf"\b{re.escape(variable)}\s*\.\s*(?:{property_pattern})\s*=", app_js):
            return True
        if re.search(rf"\b{re.escape(variable)}\s*\.\s*(?:appendChild|replaceChildren|insertAdjacentHTML)\s*\(", app_js):
            return True
    generic_dom_update = rf"document\.(?:getElementById|querySelector)\(\s*[A-Za-z_$][\w$]*\s*\)\s*\.\s*(?:{property_pattern})\s*="
    if re.search(_js_string_pattern(element_id), app_js) and re.search(generic_dom_update, app_js):
        return True
    return False


def _js_has_event_handler(app_js: str, element_id: str) -> bool:
    direct = rf"document\.{_js_element_lookup_pattern(element_id)}\s*\.\s*(?:addEventListener|onclick|onsubmit|onchange)\b"
    if re.search(direct, app_js):
        return True
    for variable in _js_element_variable_names(app_js, element_id):
        if re.search(rf"\b{re.escape(variable)}\s*\.\s*(?:addEventListener|onclick|onsubmit|onchange)\b", app_js):
            return True
    return False


def _html_id_inside_form(html_text: str, element_id: str) -> bool:
    for match in re.finditer(r"<\s*form\b[^>]*>.*?</\s*form\s*>", html_text, flags=re.I | re.S):
        if _html_has_id(match.group(0), element_id):
            return True
    return False


def _js_has_form_submit_handler(app_js: str) -> bool:
    return bool(re.search(r"\.\s*addEventListener\(\s*['\"]submit['\"]", app_js) or re.search(r"\.\s*onsubmit\b", app_js))


def _js_handles_action(app_js: str, index_html: str, element_id: str) -> bool:
    return _js_has_event_handler(app_js, element_id) or (_html_id_inside_form(index_html, element_id) and _js_has_form_submit_handler(app_js))


def _html_tag_id(tag: str) -> str:
    match = re.search(r"\bid\s*=\s*['\"]([^'\"]+)['\"]", tag, flags=re.I)
    return match.group(1) if match else ""


def infer_static_app_shape(
    project_text: str,
    prototype_type: str = "",
    metadata: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, str]] = None,
) -> str:
    metadata = metadata or {}
    files = files or {}
    declared_shape = str(metadata.get("offline_template_shape") or "").strip()
    if declared_shape in APP_SPECIFIC_VERIFY_SHAPES:
        return declared_shape

    metadata_text = _lower_join(
        metadata.get("app_name"),
        metadata.get("app_type"),
        metadata.get("short_description"),
        " ".join(str(item) for item in metadata.get("user_flow") or []),
        " ".join(str(item) for item in metadata.get("limitations") or []),
        " ".join(str(item) for item in metadata.get("mocked_parts") or []),
    )
    html_text = files.get("index.html") or files.get("src/index.html") or ""
    js_text = files.get("app.js") or files.get("src/app.js") or ""
    readme_text = files.get("README.md") or ""
    signal = _lower_join(project_text, prototype_type, metadata_text, html_text, js_text, readme_text)

    if _has_any(signal, ("budget-income", "budget calculator", "budget snapshot")):
        return "budget_calculator"
    if _has_any(signal, ("notes-input", "build-cards", "card-output", "flashcard helper", "study card builder")):
        return "flashcard_helper"
    if _has_any(signal, ("idea-input", "score-idea", "business idea scorer", "business idea scorecard")):
        return "business_idea_scorer"
    if _has_any(signal, ("quiz-recommendation", "show recommendation", "quiz recommender")):
        return "quiz_recommender"
    if _has_any(signal, ("waitlist-submit", "waitlist-result", "join waitlist", "waitlist launch page")):
        return "waitlist_page"

    project_signal = _lower_join(project_text, metadata_text)
    if _has_any(project_signal, ("budget", "expense", "expenses", "income", "savings", "spending")):
        return "budget_calculator"
    if _has_any(project_signal, ("flashcard", "flash card", "study notes", "exam", "memorize", "revision")):
        return "flashcard_helper"
    if _has_any(project_signal, ("business idea", "startup idea", "idea scorer", "idea scoring", "score my idea", "validate idea")):
        return "business_idea_scorer"
    if _has_any(project_signal, ("quiz", "recommender", "recommendation", "picker", "finder", "matching", "assessment")):
        return "quiz_recommender"
    if _has_any(project_signal, ("waitlist", "landing page", "homepage", "marketing page", "signup", "sign up", "early access")):
        return "waitlist_page"
    return ""


def static_app_shape_verification_checks(
    shape: str,
    *,
    index_html: str,
    app_js: str = "",
    readme_text: str = "",
    path: str = "",
) -> List[Dict[str, Any]]:
    label = APP_SPECIFIC_VERIFY_SHAPES.get(shape)
    if not label:
        return []

    html_lower = index_html.lower()
    combined_ui = _lower_join(index_html, app_js)
    combined = _lower_join(index_html, app_js, readme_text)

    def check(name: str, ok: bool, pass_message: str, fail_message: str, status: str = "fail") -> Dict[str, Any]:
        return {
            "name": f"{label}: {name}",
            "status": "pass" if ok else status,
            "message": pass_message if ok else fail_message,
            "path": path or None,
        }

    if shape == "business_idea_scorer":
        has_input = _html_has_id(index_html, "idea-input") and _html_id_has_data_marker(index_html, "idea-input", "main-input")
        reads_input = _js_reads_element_value(app_js, "idea-input")
        has_action = _html_has_id(index_html, "score-idea") and _html_id_has_data_marker(index_html, "score-idea", "primary-action")
        has_event_handler = _js_handles_action(app_js, index_html, "score-idea")
        has_score_surface = _html_has_id(index_html, "idea-score") and _html_has_data_marker(index_html, "result-output")
        has_score_update = _js_updates_element(app_js, "idea-score")
        has_risk_terms = _html_has_id(index_html, "idea-risks") and _html_id_has_data_marker(index_html, "idea-risks", "risk_breakdown")
        has_risk_update = _js_updates_element(app_js, "idea-risks", ("textContent", "innerHTML"))
        has_smallest_test = _html_has_id(index_html, "idea-smallest-test") and _html_id_has_data_marker(index_html, "idea-smallest-test", "smallest-testable-version")
        has_smallest_update = _js_updates_element(app_js, "idea-smallest-test")
        has_next_action = _html_has_id(index_html, "idea-next-action") and _html_id_has_data_marker(index_html, "idea-next-action", "next-action")
        has_next_update = _js_updates_element(app_js, "idea-next-action")
        return [
            check("idea input marker exists", has_input, "Business idea scorer has the canonical idea input.", "Business idea scorer needs the `idea-input` field marked as the main input."),
            check("idea input is read", reads_input, "Business idea scorer reads the idea before scoring.", "Business idea scorer needs app.js to read the `idea-input` value before scoring."),
            check("score action marker exists", has_action, "Business idea scorer has the canonical Score Idea action.", "Business idea scorer needs the `score-idea` button marked as the primary action."),
            check("score action is wired", has_event_handler, "Business idea scorer wires the Score Idea action in app.js.", "Business idea scorer needs app.js to handle the `score-idea` action."),
            check("score output exists", has_score_surface, "Business idea scorer has the canonical score output.", "Business idea scorer needs an `idea-score` output inside the result area."),
            check("score output updates", has_score_update, "Business idea scorer updates the score output.", "Business idea scorer needs app.js to update `idea-score`."),
            check("risk output exists", has_risk_terms, "Business idea scorer has the canonical risk output.", "Business idea scorer needs an `idea-risks` output marked as the risk breakdown."),
            check("risk output updates", has_risk_update, "Business idea scorer updates the risk output.", "Business idea scorer needs app.js to update `idea-risks`."),
            check("smallest test output exists", has_smallest_test, "Business idea scorer has the smallest testable version output.", "Business idea scorer needs an `idea-smallest-test` output."),
            check("smallest test output updates", has_smallest_update, "Business idea scorer updates the smallest testable version.", "Business idea scorer needs app.js to update `idea-smallest-test`."),
            check("next action output exists", has_next_action, "Business idea scorer has the next action output.", "Business idea scorer needs an `idea-next-action` output."),
            check("next action output updates", has_next_update, "Business idea scorer updates the next action.", "Business idea scorer needs app.js to update `idea-next-action`."),
        ]

    if shape == "budget_calculator":
        number_tags = _html_number_input_tags(index_html)
        has_numeric_income = any("budget-income" in tag and "main-input" in tag for tag in number_tags)
        has_numeric_expense = any(_has_any(tag, ("expense", "housing", "rent", "food", "transport", "other")) for tag in number_tags)
        has_numeric_inputs = _html_number_input_count(index_html) >= 2 and has_numeric_income and has_numeric_expense
        expense_ids = [
            element_id
            for element_id in (_html_tag_id(tag) for tag in number_tags)
            if element_id and element_id != "budget-income" and _has_any(element_id, ("expense", "housing", "rent", "food", "transport", "other"))
        ]
        reads_income = _js_reads_element_value(app_js, "budget-income")
        reads_expense = any(_js_reads_element_value(app_js, element_id) for element_id in expense_ids)
        has_calculate_action = _html_has_id(index_html, "budget-run") and _html_id_has_data_marker(index_html, "budget-run", "primary-action")
        has_event_handler = _js_handles_action(app_js, index_html, "budget-run")
        has_savings_output = _html_has_id(index_html, "budget-savings") and _html_has_data_marker(index_html, "result-output")
        has_savings_update = _js_updates_element(app_js, "budget-savings")
        has_breakdown_terms = _html_has_id(index_html, "budget-breakdown") and _html_id_has_data_marker(index_html, "budget-breakdown", "spending-breakdown")
        has_breakdown_update = _js_updates_element(app_js, "budget-breakdown")
        has_recommendation = _html_has_id(index_html, "budget-recommendation") and _html_id_has_data_marker(index_html, "budget-recommendation", "recommendation")
        has_recommendation_update = _js_updates_element(app_js, "budget-recommendation")
        return [
            check("income and expense input markers exist", has_numeric_inputs, "Budget calculator has canonical numeric income and expense inputs.", "Budget calculator needs `budget-income` and expense input markers."),
            check("income input is read", reads_income, "Budget calculator reads monthly income before calculating.", "Budget calculator needs app.js to read the `budget-income` value before calculating."),
            check("expense input is read", reads_expense, "Budget calculator reads at least one expense before calculating.", "Budget calculator needs app.js to read at least one expense input before calculating."),
            check("calculate action marker exists", has_calculate_action, "Budget calculator has the canonical calculate action.", "Budget calculator needs the `budget-run` button marked as the primary action."),
            check("calculate action is wired", has_event_handler, "Budget calculator wires the calculate action in app.js.", "Budget calculator needs app.js to handle the `budget-run` calculation action."),
            check("savings output exists", has_savings_output, "Budget calculator has the monthly savings output.", "Budget calculator needs a `budget-savings` output in the result area."),
            check("savings output updates", has_savings_update, "Budget calculator updates monthly savings.", "Budget calculator needs app.js to update `budget-savings`."),
            check("breakdown output exists", has_breakdown_terms, "Budget calculator has the spending breakdown output.", "Budget calculator needs a `budget-breakdown` output."),
            check("breakdown output updates", has_breakdown_update, "Budget calculator updates the spending breakdown.", "Budget calculator needs app.js to update `budget-breakdown`."),
            check("recommendation output exists", has_recommendation, "Budget calculator has the recommendation output.", "Budget calculator needs a `budget-recommendation` output."),
            check("recommendation output updates", has_recommendation_update, "Budget calculator updates the recommendation.", "Budget calculator needs app.js to update `budget-recommendation`."),
        ]

    if shape == "flashcard_helper":
        has_textarea = _html_has_id(index_html, "notes-input") and _html_id_has_data_marker(index_html, "notes-input", "main-input")
        reads_notes = _js_reads_element_value(app_js, "notes-input")
        has_generate_action = _html_has_id(index_html, "build-cards") and _html_id_has_data_marker(index_html, "build-cards", "primary-action")
        has_event_handler = _js_handles_action(app_js, index_html, "build-cards")
        has_card_output_marker = _html_has_id(index_html, "card-output") and _html_id_has_data_marker(index_html, "card-output", "flashcard-cards")
        has_card_update = _js_updates_element(app_js, "card-output", ("textContent", "innerHTML"))
        has_card_rendering = has_card_update and _has_any(app_js, ("flashcard-card", "qa-card", "question", "answer", "card.question", "card.answer"))
        has_local_note = _has_any(combined, ("does not call ai", "not live ai", "mocked", "deterministic local text", "local sentence", "local flashcard rules"))
        return [
            check("notes input marker exists", has_textarea, "Flashcard helper has the canonical study notes input.", "Flashcard helper needs the `notes-input` textarea marked as the main input."),
            check("notes input is read", reads_notes, "Flashcard helper reads study notes before building cards.", "Flashcard helper needs app.js to read the `notes-input` value before building cards."),
            check("build action marker exists", has_generate_action, "Flashcard helper has the canonical Build Flashcards action.", "Flashcard helper needs the `build-cards` button marked as the primary action."),
            check("build action is wired", has_event_handler, "Flashcard helper wires the Build Flashcards action in app.js.", "Flashcard helper needs app.js to handle the `build-cards` action."),
            check("card output exists", has_card_output_marker, "Flashcard helper has the card output surface.", "Flashcard helper needs a `card-output` area marked for flashcard cards."),
            check("card output updates", has_card_update, "Flashcard helper updates the card output surface.", "Flashcard helper needs app.js to update `card-output`."),
            check("flashcard content renders", has_card_rendering, "Flashcard helper renders question/answer cards.", "Flashcard helper needs app.js to render question/answer card content into `card-output`."),
            check("mocked/local limitation note exists", has_local_note, "Flashcard helper explains the local or mocked limitation.", "Flashcard helper should explain that card generation is local/mocked, not live AI.", status="warn"),
        ]

    if shape == "quiz_recommender":
        has_answer_inputs = _has_any(html_lower, ("<select", "type=\"radio", "type='radio", "option")) or _has_any(app_js, ("question", "options"))
        has_recommend_action = _has_any(combined_ui, ("show recommendation", "recommendation", "recommend")) and (_html_has_tag(index_html, "button") or _has_any(app_js, ("addeventlistener", ".onclick")))
        has_result_surface = _has_any(combined_ui, ("quiz-recommendation", "quiz-result", "recommendation")) and _has_any(html_lower, ("result", "recommendation"))
        has_local_logic = _has_any(combined, ("deterministic", "local score", "local recommendation", "no external", "no ai"))
        return [
            check("answer inputs exist", has_answer_inputs, "Quiz recommender has answer inputs.", "Quiz recommender needs selectable answers."),
            check("recommendation action exists", has_recommend_action, "Quiz recommender has a recommendation action.", "Quiz recommender needs a clear recommendation action."),
            check("recommendation result surface exists", has_result_surface, "Quiz recommender has a recommendation result surface.", "Quiz recommender needs a visible recommendation result surface."),
            check("local deterministic logic note exists", has_local_logic, "Quiz recommender explains local deterministic logic.", "Quiz recommender should explain the recommendation is local/deterministic.", status="warn"),
        ]

    if shape == "waitlist_page":
        has_cta = _has_any(combined_ui, ("join waitlist", "early access", "signup", "sign up", "waitlist"))
        has_contact_input = _has_any(html_lower, ("email", "waitlist-email")) and _html_has_tag(index_html, "input")
        has_submit_action = _has_any(combined_ui, ("waitlist-submit", "join waitlist", "submit")) and (_html_has_tag(index_html, "button") or _has_any(app_js, ("addeventlistener", ".onclick")))
        has_confirmation = _has_any(combined_ui, ("waitlist-result", "confirmation", "thanks", "local-only", "mock signup"))
        return [
            check("landing CTA exists", has_cta, "Landing page has a clear CTA.", "Landing page needs a clear waitlist or signup CTA."),
            check("contact input exists", has_contact_input, "Landing page has contact input.", "Landing page needs an email/contact input."),
            check("CTA action exists", has_submit_action, "Landing page has a CTA action.", "Landing page needs a visible CTA action."),
            check("local confirmation state exists", has_confirmation, "Landing page has a local confirmation state.", "Landing page needs a visible local-only confirmation state."),
        ]

    return []
