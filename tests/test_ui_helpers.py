import sprintos
from sprintos_core import ui_helpers
from tests.test_support import SprintOSTestCase


class UIHelperTests(SprintOSTestCase):
    def test_escape_html_escapes_script_and_quotes(self) -> None:
        escaped = ui_helpers.escape_html('<script>"x"&\'y\'</script>')
        self.assertEqual(escaped, "&lt;script&gt;&quot;x&quot;&amp;&#x27;y&#x27;&lt;/script&gt;")

    def test_badge_helper_renders_expected_class_and_text(self) -> None:
        html = ui_helpers.render_badge("Ready", class_name="pill")
        self.assertIn('class="pill"', html)
        self.assertIn("<strong>Ready</strong>", html)

    def test_section_header_helper_renders_section_title(self) -> None:
        html = ui_helpers.render_section_header("Execute", "Command Center first.")
        self.assertIn("Execute", html)
        self.assertIn("section-group-header", html)

    def test_project_section_helper_contains_expected_ids_and_classes(self) -> None:
        html = ui_helpers.render_project_section(
            "quality",
            "Technical Details",
            "Inspect deeper controls without surfacing them by default.",
            "<p>Body</p>",
            open=False,
            badge_text="Attention",
        )
        self.assertIn('id="section-quality"', html)
        self.assertIn("section-group is-collapsed", html)
        self.assertIn("data-role=\"section-toggle\"", html)
        self.assertIn("Attention", html)

    def test_copy_button_helper_renders_copyable_text_safely(self) -> None:
        html = ui_helpers.render_copy_button('copy "this" <value>', button_id="copy-one")
        self.assertIn('id="copy-one"', html)
        self.assertIn("data-copy-text=", html)
        self.assertIn("&quot;this&quot;", html)
        self.assertIn("&lt;value&gt;", html)

    def test_empty_state_helper_renders_fallback_text(self) -> None:
        html = ui_helpers.render_empty_state("No activity recorded yet.")
        self.assertIn("No activity recorded yet.", html)
        self.assertIn('class="muted"', html)

    def test_copyable_text_block_helper_escapes_preview_and_body(self) -> None:
        html = ui_helpers.render_copyable_text_block(
            element_id="prompt-one",
            title="Saved text",
            text='<b>unsafe</b> body',
            copy_action="copyPrompt",
            open_by_default=True,
        )
        self.assertIn("<details", html)
        self.assertIn('id="prompt-one"', html)
        self.assertIn("&lt;b&gt;unsafe&lt;/b&gt; body", html)
        self.assertIn("Copy", html)

    def test_main_page_bundle_still_renders_today_dashboard(self) -> None:
        self.assertIn("Today / Continue", sprintos.INDEX_HTML)
        self.assertIn("Create App", sprintos.INDEX_HTML)
        self.assertIn("Advanced / Plan Only", sprintos.INDEX_HTML)
        self.assertNotIn('<h3 style="margin:0">AI Status</h3>', sprintos.INDEX_HTML)
        self.assertIn("Start with one raw idea", sprintos.INDEX_HTML)
        self.assertIn("Create App preflight", sprintos.INDEX_HTML)
        self.assertIn("quickLaunchIntentReview", sprintos.INDEX_HTML)
        self.assertIn("reviewQuickLaunchIntent", sprintos.INDEX_HTML)
        self.assertIn("Generate With Assumptions", sprintos.INDEX_HTML)
        self.assertIn("AI app generation is ready.", sprintos.INDEX_HTML)
        self.assertIn("AI may fall back to the local template.", sprintos.INDEX_HTML)
        self.assertIn("Create your first app", sprintos.INDEX_HTML)
        self.assertIn("homeQuickLaunchIdea", sprintos.INDEX_HTML)
        self.assertIn("function renderHomeCanvas", sprintos.INDEX_HTML)
        self.assertIn("function renderHomeContinueHero", sprintos.INDEX_HTML)
        self.assertIn("Choose or create an app", sprintos.INDEX_HTML)
        self.assertIn("Select a project from the left or create a new app.", sprintos.INDEX_HTML)
        self.assertIn("Continue This App", sprintos.INDEX_HTML)
        self.assertIn("Open App Preview", sprintos.INDEX_HTML)
        self.assertIn("Your app draft is ready", sprintos.INDEX_HTML)
        self.assertIn("Download App", sprintos.INDEX_HTML)
        self.assertIn("Runnable local app package for previewing and sharing the current draft.", sprintos.INDEX_HTML)
        self.assertIn("Download Source Pack", sprintos.INDEX_HTML)
        self.assertIn("Editable source/Codex package for inspecting or continuing the app locally.", sprintos.INDEX_HTML)
        self.assertIn("Primary files", sprintos.INDEX_HTML)
        self.assertIn("offline template selected", sprintos.INDEX_HTML)

    def test_project_view_bundle_keeps_command_center_before_focus_and_timeline(self) -> None:
        self.assertIn("${commandCenterPanel}${focusSessionPanel}${activityTimelinePanel}", sprintos.INDEX_HTML)

    def test_project_view_bundle_still_renders_major_section_labels(self) -> None:
        for label in ("Execute", "Advanced Build Controls", "App Workspace", "Feedback", "Technical Details", "AI"):
            self.assertIn(label, sprintos.INDEX_HTML)
        for label in ("Do Next Step", "Check App Changes", "Test App", "Older Outputs", "Prepare App for Codex"):
            self.assertIn(label, sprintos.INDEX_HTML)

    def test_index_html_uses_extracted_ui_helper_bundle(self) -> None:
        self.assertNotIn("__SPRINTOS_UI_HELPERS__", sprintos.INDEX_HTML)
        self.assertIn("function renderProjectSection", sprintos.INDEX_HTML)
        self.assertIn("function renderCopyableTextBlock", sprintos.INDEX_HTML)
        self.assertIn("function renderDetailsBlock", sprintos.INDEX_HTML)
