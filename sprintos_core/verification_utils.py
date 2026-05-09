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
    "decision_matrix": "decision matrix",
    "flashcard_helper": "flashcard helper",
    "pricing_roi_calculator": "pricing ROI calculator",
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


def _html_tags(html_text: str, tag_name: str) -> List[str]:
    return [match.group(0) for match in re.finditer(rf"<\s*{re.escape(tag_name)}\b[^>]*>", html_text, flags=re.I)]


def _html_tag_attr(tag: str, attr_name: str) -> str:
    match = re.search(rf"\b{re.escape(attr_name)}\s*=\s*['\"]([^'\"]+)['\"]", tag, flags=re.I)
    return match.group(1) if match else ""


def _html_control_ids(html_text: str) -> List[str]:
    ids: List[str] = []
    for tag in _html_tags(html_text, "input"):
        input_type = _html_tag_attr(tag, "type").lower()
        if input_type in {"hidden", "button", "submit", "reset"}:
            continue
        element_id = _html_tag_id(tag)
        if element_id:
            ids.append(element_id)
    for tag_name in ("textarea", "select"):
        for tag in _html_tags(html_text, tag_name):
            element_id = _html_tag_id(tag)
            if element_id:
                ids.append(element_id)
    return ids


def _html_action_ids(html_text: str) -> List[str]:
    ids: List[str] = []
    for tag in _html_tags(html_text, "button"):
        element_id = _html_tag_id(tag)
        if element_id:
            ids.append(element_id)
    for tag in _html_tags(html_text, "input"):
        input_type = _html_tag_attr(tag, "type").lower()
        if input_type in {"button", "submit"}:
            element_id = _html_tag_id(tag)
            if element_id:
                ids.append(element_id)
    return ids


def _html_output_ids(html_text: str) -> List[str]:
    output_terms = (
        "output",
        "result",
        "summary",
        "recommendation",
        "breakdown",
        "ranking",
        "score",
        "status",
        "message",
        "preview",
        "cards",
        "report",
        "list",
        "timeline",
    )
    ids: List[str] = []
    for match in re.finditer(r"<\s*[\w:-]+\b[^>]*>", html_text, flags=re.I):
        tag = match.group(0)
        element_id = _html_tag_id(tag)
        if not element_id:
            continue
        marker = _html_tag_attr(tag, "data-template-marker")
        class_name = _html_tag_attr(tag, "class")
        combined = _lower_join(element_id, marker, class_name)
        if _has_any(combined, output_terms):
            ids.append(element_id)
    return ids


def _html_visible_title(index_html: str) -> str:
    h1_match = re.search(r"<\s*h1\b[^>]*>(.*?)</\s*h1\s*>", index_html, flags=re.I | re.S)
    if h1_match:
        return re.sub(r"<[^>]+>", " ", h1_match.group(1)).strip()
    title_match = re.search(r"<\s*title\b[^>]*>(.*?)</\s*title\s*>", index_html, flags=re.I | re.S)
    if title_match:
        return re.sub(r"<[^>]+>", " ", title_match.group(1)).strip()
    return ""


def _significant_title_words(title: str) -> List[str]:
    stop_words = {"the", "and", "for", "with", "app", "local", "demo", "prototype", "tool"}
    words = [word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", title)]
    return [word for word in words if word not in stop_words]


def _js_has_generic_event_handler(app_js: str) -> bool:
    return bool(re.search(r"\.\s*addEventListener\(\s*['\"](?:click|submit|change|input)['\"]", app_js) or re.search(r"\.\s*on(?:click|submit|change|input)\b", app_js))


def _js_reads_any_input_value(app_js: str, input_ids: Iterable[str]) -> bool:
    return any(_js_reads_element_value(app_js, element_id) for element_id in input_ids)


def _js_updates_any_output(app_js: str, output_ids: Iterable[str]) -> bool:
    return any(_js_updates_element(app_js, element_id, ("textContent", "innerHTML", "value")) for element_id in output_ids)


def _contains_placeholder_only_js(app_js: str) -> bool:
    lowered = app_js.lower()
    return any(marker in lowered for marker in ("coming soon", "todo", "placeholder", "lorem ipsum"))


def _has_local_first_note(*texts: str) -> bool:
    combined = _lower_join(*texts)
    local_signal = _has_any(combined, ("local", "offline", "browser-only", "static", "demo", "prototype"))
    limitation_signal = _has_any(combined, ("no external", "does not call", "no network", "no backend", "no cloud", "mock", "limitation"))
    return local_signal and limitation_signal


def universal_app_contract_verification_checks(
    *,
    index_html: str,
    app_js: str = "",
    readme_text: str = "",
    test_plan_text: str = "",
    path: str = "",
) -> List[Dict[str, Any]]:
    """Generic quality checks for non-canonical static prototype apps."""

    label = "universal app"
    input_ids = _html_control_ids(index_html)
    action_ids = _html_action_ids(index_html)
    output_ids = _html_output_ids(index_html)
    has_interactive_ui = bool(input_ids or action_ids)
    title = _html_visible_title(index_html)
    title_words = _significant_title_words(title)
    network_blockers = external_network_markers("index.html", index_html) + external_network_markers("style/app.js", app_js)
    provider_markers = (
        "api." + "op" + "enai.com",
        "op" + "enai.com/v1",
        "api." + "deep" + "seek.com",
        "/chat/completions",
        "/v1/responses",
        "op" + "enai_api_key",
        "deep" + "seek_api_key",
    )
    has_provider_marker = _has_any(_lower_join(index_html, app_js), provider_markers)

    def check(name: str, ok: bool, pass_message: str, fail_message: str, status: str = "fail") -> Dict[str, Any]:
        return {
            "name": f"{label}: {name}",
            "status": "pass" if ok else status,
            "message": pass_message if ok else fail_message,
            "path": path or None,
        }

    has_title = bool(title.strip()) and bool(re.search(r"<\s*h1\b", index_html, flags=re.I))
    has_purpose = _has_any(index_html, ("purpose", "use this", "helps", "for ", "so you can", "designed for", "built for"))
    has_sections = len(re.findall(r"<\s*(?:section|article|h2|h3|li)\b", index_html, flags=re.I)) >= 2
    reads_input = (not input_ids) or _js_reads_any_input_value(app_js, input_ids)
    action_wired = (not action_ids) or any(_js_handles_action(app_js, index_html, element_id) for element_id in action_ids) or _js_has_generic_event_handler(app_js)
    has_output_surface = (not has_interactive_ui) or bool(output_ids)
    updates_output = (not output_ids or not has_interactive_ui) or _js_updates_any_output(app_js, output_ids)
    has_empty_state = (not has_interactive_ui) or _has_any(_lower_join(index_html, app_js), ("empty", "no ", "not yet", "enter", "add ", "start", "nothing", "ready"))
    has_local_note = _has_local_first_note(index_html, readme_text, test_plan_text)
    readme_lower = readme_text.lower()
    test_plan_lower = test_plan_text.lower()
    readme_mentions_title = not title_words or any(word in readme_lower for word in title_words[:3])
    test_plan_mentions_title = not title_words or any(word in test_plan_lower for word in title_words[:3])
    readme_practical = (
        readme_mentions_title
        and _has_any(readme_lower, ("purpose", "what it does", "overview", "helps"))
        and _has_any(readme_lower, ("how to run", "run `", "open index.html", "http.server"))
        and _has_any(readme_lower, ("test", "manual", "how to use"))
        and _has_any(readme_lower, ("limit", "limitation", "local", "demo", "prototype"))
        and _has_any(readme_lower, ("codex", "next step", "next steps"))
    )
    test_plan_practical = (
        test_plan_mentions_title
        and _has_any(test_plan_lower, ("happy path", "main path", "basic flow"))
        and _has_any(test_plan_lower, ("edge", "empty", "invalid", "missing", "blank"))
        and _has_any(test_plan_lower, ("local", "offline", "network", "external", "safety"))
    )
    no_network = not network_blockers and not has_provider_marker

    return [
        check("title and purpose are visible", has_title and has_purpose, "The app has a visible title and purpose.", "Add a visible h1 title and purpose/use-case copy."),
        check("meaningful sections exist", has_sections, "The app has meaningful sections or screens.", "Add meaningful sections, screens, or content groups."),
        check("input value is read when inputs exist", reads_input, "The app reads at least one input value when inputs exist.", "app.js must read at least one visible input value."),
        check("primary action is wired when actions exist", action_wired, "The app wires the primary action.", "app.js must handle the primary button or form action."),
        check("output surface exists for interactive flow", has_output_surface, "The app has an output surface for the interactive flow.", "Interactive apps need a visible output/result area."),
        check("output surface updates", updates_output, "The app updates a visible output area.", "app.js must update a visible output/result area."),
        check("placeholder-only behavior is avoided", not _contains_placeholder_only_js(app_js), "The app avoids placeholder-only behavior.", "Replace placeholder-only app.js behavior with local deterministic logic."),
        check("useful empty state exists", has_empty_state, "The app has a useful empty or start state.", "Interactive apps need a useful empty/start state."),
        check("local demo limitation note exists", has_local_note, "The app explains local/demo limitations.", "Add a local/demo limitation note and make clear no external service is required."),
        check("README is practical and app-specific", readme_practical, "README includes purpose, run steps, tests, limitations, and Codex next steps.", "README must include purpose, how to run, manual test steps, limitations, and Codex next steps."),
        check("TEST_PLAN is practical and app-specific", test_plan_practical, "TEST_PLAN includes happy path, edge cases, and safety/local-first checks.", "TEST_PLAN must include happy path, edge cases, and safety/local-first checks."),
        check("no browser network or provider calls", no_network, "No browser network or provider calls were found.", "Remove browser network calls, provider endpoints, API calls, and key references."),
    ]


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

    if _has_any(
        signal,
        (
            "roi-price",
            "roi calculator",
            "pricing calculator",
            "pricing roi",
            "return on investment",
            "unit economics",
            "break-even",
            "payback",
        ),
    ):
        return "pricing_roi_calculator"
    if _has_any(signal, ("decision-options", "decision-criteria", "compare-options", "decision-ranking", "decision matrix")):
        return "decision_matrix"
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
    if _has_any(
        project_signal,
        (
            "pricing calculator",
            "roi calculator",
            "return on investment",
            "unit economics",
            "margin calculator",
            "revenue calculator",
            "break-even",
            "break even",
            "payback",
            "price my product",
            "estimate mrr",
            "calculate profitability",
            "profitability calculator",
        ),
    ):
        return "pricing_roi_calculator"
    if _has_any(project_signal, ("decision matrix", "compare options", "choose between", "tradeoff", "tradeoffs", "criteria")):
        return "decision_matrix"
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

    if shape == "decision_matrix":
        has_options = _html_has_id(index_html, "decision-options") and _html_id_has_data_marker(index_html, "decision-options", "main-input")
        reads_options = _js_reads_element_value(app_js, "decision-options")
        has_criteria = _html_has_id(index_html, "decision-criteria")
        reads_criteria = _js_reads_element_value(app_js, "decision-criteria")
        has_compare_action = _html_has_id(index_html, "compare-options") and _html_id_has_data_marker(index_html, "compare-options", "primary-action")
        has_event_handler = _js_handles_action(app_js, index_html, "compare-options")
        has_ranking = _html_has_id(index_html, "decision-ranking") and _html_has_data_marker(index_html, "result-output")
        has_ranking_update = _js_updates_element(app_js, "decision-ranking", ("textContent", "innerHTML"))
        has_recommendation = _html_has_id(index_html, "decision-recommendation") and _html_id_has_data_marker(index_html, "decision-recommendation", "recommendation")
        has_recommendation_update = _js_updates_element(app_js, "decision-recommendation")
        has_tradeoffs = _html_has_id(index_html, "decision-tradeoffs") and _html_id_has_data_marker(index_html, "decision-tradeoffs", "tradeoffs")
        has_tradeoffs_update = _js_updates_element(app_js, "decision-tradeoffs", ("textContent", "innerHTML"))
        has_ranking_logic = _has_any(app_js, ("sort(", ".sort", "scoreoption", "ranked=")) and _has_any(app_js, ("score", "criteria"))
        has_empty_state = _has_any(combined, ("empty", "add at least", "enter at least", "not enough", "paste options"))
        has_local_note = _has_any(combined, ("ranks options locally", "simple deterministic rules", "does not call live ai", "external services inside the browser"))
        return [
            check("options input marker exists", has_options, "Decision matrix has the canonical options input.", "Decision matrix needs `decision-options` marked as the main input."),
            check("options input is read", reads_options, "Decision matrix reads options before comparing.", "Decision matrix needs app.js to read the `decision-options` value."),
            check("criteria input exists", has_criteria, "Decision matrix has the canonical criteria input.", "Decision matrix needs a `decision-criteria` input surface."),
            check("criteria input is read", reads_criteria, "Decision matrix reads criteria before comparing.", "Decision matrix needs app.js to read the `decision-criteria` value."),
            check("compare action marker exists", has_compare_action, "Decision matrix has the canonical Compare Options action.", "Decision matrix needs the `compare-options` button marked as the primary action."),
            check("compare action is wired", has_event_handler, "Decision matrix wires the Compare Options action in app.js.", "Decision matrix needs app.js to handle the `compare-options` action."),
            check("ranking output exists", has_ranking, "Decision matrix has the ranking output.", "Decision matrix needs a `decision-ranking` output in the result area."),
            check("ranking output updates", has_ranking_update, "Decision matrix updates the ranking output.", "Decision matrix needs app.js to update `decision-ranking`."),
            check("recommendation output exists", has_recommendation, "Decision matrix has the recommendation output.", "Decision matrix needs a `decision-recommendation` output."),
            check("recommendation output updates", has_recommendation_update, "Decision matrix updates the recommendation output.", "Decision matrix needs app.js to update `decision-recommendation`."),
            check("tradeoffs output exists", has_tradeoffs, "Decision matrix has the tradeoffs output.", "Decision matrix needs a `decision-tradeoffs` output."),
            check("tradeoffs output updates", has_tradeoffs_update, "Decision matrix updates the tradeoffs output.", "Decision matrix needs app.js to update `decision-tradeoffs`."),
            check("ranking logic exists", has_ranking_logic, "Decision matrix includes deterministic ranking logic.", "Decision matrix needs concrete local ranking logic, not placeholder text."),
            check("empty state exists", has_empty_state, "Decision matrix handles empty or weak input.", "Decision matrix should explain what to enter when options or criteria are missing.", status="warn"),
            check("local limitation note exists", has_local_note, "Decision matrix explains local deterministic limits.", "Decision matrix should explain that ranking is local and deterministic.", status="warn"),
        ]

    if shape == "pricing_roi_calculator":
        number_tags = _html_number_input_tags(index_html)
        has_price = any("roi-price" in tag for tag in number_tags)
        has_cost = any("roi-cost" in tag for tag in number_tags)
        has_customers = any("roi-customers" in tag for tag in number_tags)
        reads_price = _js_reads_element_value(app_js, "roi-price")
        reads_cost = _js_reads_element_value(app_js, "roi-cost")
        reads_customers = _js_reads_element_value(app_js, "roi-customers")
        has_action = _html_has_id(index_html, "roi-run") and _html_id_has_data_marker(index_html, "roi-run", "primary-action")
        has_event_handler = _js_handles_action(app_js, index_html, "roi-run")
        has_summary = _html_has_id(index_html, "roi-summary") and _html_has_data_marker(index_html, "result-output")
        has_summary_update = _js_updates_element(app_js, "roi-summary", ("textContent", "innerHTML"))
        has_breakdown = _html_has_id(index_html, "roi-breakdown") and _html_id_has_data_marker(index_html, "roi-breakdown", "roi-breakdown")
        has_breakdown_update = _js_updates_element(app_js, "roi-breakdown", ("textContent", "innerHTML"))
        has_recommendation = _html_has_id(index_html, "roi-recommendation") and _html_id_has_data_marker(index_html, "roi-recommendation", "recommendation")
        has_recommendation_update = _js_updates_element(app_js, "roi-recommendation")
        metric_terms = (
            "monthlyrevenue",
            "revenue",
            "totalcost",
            "grossprofit",
            "profit",
            "margin",
            "breakeven",
            "break-even",
            "payback",
            "roi",
            "returnoninvestment",
        )
        metric_count = sum(1 for marker in metric_terms if marker in app_js.replace("_", "").replace("-", "").lower())
        has_metric_logic = metric_count >= 2 and _has_any(app_js, ("*", "/", "-", "+")) and not _has_any(app_js.lower(), ("coming soon", "todo"))
        has_invalid_handling = _has_any(combined, ("invalid", "negative", "blank", "empty", "treated as 0", "enter a non-negative", "0 for math"))
        has_local_note = _has_any(combined, ("estimates pricing and roi locally", "simple deterministic calculations", "does not call live ai", "external services inside the browser"))
        return [
            check("price cost customer inputs exist", has_price and has_cost and has_customers, "Pricing ROI calculator has numeric price, cost, and customer inputs.", "Pricing ROI calculator needs numeric `roi-price`, `roi-cost`, and `roi-customers` inputs."),
            check("price input is read", reads_price, "Pricing ROI calculator reads price before calculating.", "Pricing ROI calculator needs app.js to read the `roi-price` value."),
            check("cost input is read", reads_cost, "Pricing ROI calculator reads cost before calculating.", "Pricing ROI calculator needs app.js to read the `roi-cost` value."),
            check("customers input is read", reads_customers, "Pricing ROI calculator reads customers before calculating.", "Pricing ROI calculator needs app.js to read the `roi-customers` value."),
            check("calculate action marker exists", has_action, "Pricing ROI calculator has the canonical ROI action.", "Pricing ROI calculator needs the `roi-run` button marked as the primary action."),
            check("calculate action is wired", has_event_handler, "Pricing ROI calculator wires the ROI action in app.js.", "Pricing ROI calculator needs app.js to handle the `roi-run` action."),
            check("summary output exists", has_summary, "Pricing ROI calculator has the summary output.", "Pricing ROI calculator needs a `roi-summary` output in the result area."),
            check("summary output updates", has_summary_update, "Pricing ROI calculator updates the summary output.", "Pricing ROI calculator needs app.js to update `roi-summary`."),
            check("breakdown output exists", has_breakdown, "Pricing ROI calculator has the breakdown output.", "Pricing ROI calculator needs a `roi-breakdown` output."),
            check("breakdown output updates", has_breakdown_update, "Pricing ROI calculator updates the breakdown output.", "Pricing ROI calculator needs app.js to update `roi-breakdown`."),
            check("recommendation output exists", has_recommendation, "Pricing ROI calculator has the recommendation output.", "Pricing ROI calculator needs a `roi-recommendation` output."),
            check("recommendation output updates", has_recommendation_update, "Pricing ROI calculator updates the recommendation output.", "Pricing ROI calculator needs app.js to update `roi-recommendation`."),
            check("business metric logic exists", has_metric_logic, "Pricing ROI calculator includes deterministic business metric logic.", "Pricing ROI calculator needs concrete revenue, cost, margin, break-even, payback, or ROI calculations, not placeholder text."),
            check("invalid input handling exists", has_invalid_handling, "Pricing ROI calculator handles blank, invalid, or negative input.", "Pricing ROI calculator should explain how blank, invalid, or negative inputs are handled.", status="warn"),
            check("local limitation note exists", has_local_note, "Pricing ROI calculator explains local deterministic limits.", "Pricing ROI calculator should explain that estimates are local deterministic calculations.", status="warn"),
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
