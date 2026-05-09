import io
import json
import os
import urllib.error
import zipfile
from pathlib import Path
from typing import Any
from unittest import mock

import scripts.health as health
import sprintos
from sprintos_core.ai_costs import estimate_ai_cost, estimate_tokens_from_chars
from sprintos_core.ai_provider import (
    AIProviderResult,
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENAI_MODEL,
    ai_enabled,
    call_deepseek_chat_completions,
    call_openai_responses,
    fake_provider_result,
    generate_json_with_ai,
    load_ai_provider_config,
    parse_deepseek_chat_text,
    parse_response_text,
)
from sprintos_core.ai_schemas import build_ai_task_json_schema, build_json_only_instructions, build_openai_text_format, validate_ai_payload
from sprintos_core.env_utils import load_local_env
from sprintos_core.json_utils import read_json_file, safe_json_loads
from sprintos_core.path_utils import safe_flat_file_path, safe_relative_file_path
from sprintos_core.report_utils import create_report_dir
from sprintos_core.verification_utils import external_network_markers, static_app_shape_verification_checks
from sprintos_core.zip_utils import build_zip_from_pairs
from tests.test_support import SprintOSTestCase


class AIProviderTests(SprintOSTestCase):
    def app_file_fixture(self, name: str) -> dict:
        path = Path(__file__).parent / "fixtures" / "app_file_generation" / name
        return json.loads(path.read_text(encoding="utf-8"))

    def app_file_contents(self, payload: dict) -> dict[str, str]:
        return {
            str(item.get("filename") or ""): str(item.get("content") or "")
            for item in payload.get("files") or []
            if isinstance(item, dict)
        }

    def app_file_generation_payload(self) -> dict:
        return {
            "app_name": "Idea Scoreboard",
            "app_type": "static_app",
            "short_description": "Score a rough idea locally.",
            "user_flow": ["Paste an idea.", "Click Score Idea.", "Review the local score."],
            "files": [
                {
                    "filename": "index.html",
                    "content": '<!doctype html><html><head><link rel="stylesheet" href="style.css" /></head><body><main data-app-shape="business_idea_scorer"><textarea id="idea-input" data-template-marker="main-input"></textarea><button id="score-idea" data-template-marker="primary-action">Score Idea</button><section id="result" class="result" data-template-marker="result-output"><div id="idea-score">0</div><ul id="idea-risks" data-template-marker="risk_breakdown"><li>No score yet.</li></ul><div id="idea-smallest-test" data-template-marker="smallest-testable-version">No score yet.</div><div id="idea-next-action" data-template-marker="next-action">No score yet.</div></section></main><script src="app.js"></script></body></html>',
                },
                {"filename": "style.css", "content": "body{font-family:sans-serif;}"},
                {"filename": "app.js", "content": "function scoreIdea(){const idea=document.getElementById('idea-input').value.trim();const score=idea.length>20?'7':'4';document.getElementById('idea-score').textContent=score;document.getElementById('idea-risks').innerHTML='<li>Demand risk: medium</li><li>Execution risk: high</li>';document.getElementById('idea-smallest-test').textContent='Smallest testable version: interview 3 users.';document.getElementById('idea-next-action').textContent='Next action: book one validation call.';}document.getElementById('score-idea').addEventListener('click', scoreIdea);"},
                {"filename": "README.md", "content": "# Idea Scoreboard\n\nRun locally."},
                {"filename": "TEST_PLAN.md", "content": "# Test Plan\n\n- Open the app."},
            ],
            "run_instructions": "Run a local static server.",
            "test_instructions": "Open the app and click the button.",
            "codex_next_prompt": "Improve one small local feature.",
            "limitations": ["Prototype only."],
            "mocked_parts": ["Scoring is deterministic."],
        }

    def test_app_file_generation_openai_schema_is_shallow_strict_compatible(self) -> None:
        schema = build_ai_task_json_schema("app_file_generation")
        text_format = build_openai_text_format("app_file_generation")
        unsupported = {"oneOf", "anyOf", "allOf", "not", "patternProperties", "dependencies", "if", "then", "else"}

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                self.assertFalse(unsupported.intersection(value.keys()))
                if value.get("type") == "object":
                    self.assertIn("additionalProperties", value)
                    self.assertFalse(value["additionalProperties"])
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)

        walk(schema)
        self.assertEqual(text_format["type"], "json_schema")
        self.assertTrue(text_format["strict"])
        self.assertEqual(sorted(schema["properties"]["app_type"]["enum"]), ["ai_text_tool", "calculator", "landing_page", "quiz", "static_app"])
        self.assertEqual(schema["properties"]["files"]["items"]["properties"]["filename"]["enum"], ["index.html", "style.css", "app.js", "README.md", "TEST_PLAN.md"])

    def test_openai_request_uses_text_format_json_schema(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-openai-schema-request-test"
        config = load_ai_provider_config(
            {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": "sk-openai-schema-request-test"}
        )
        captured: dict[str, Any] = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"output_text": "{\"status\":\"ok\"}"}).encode("utf-8")

        def transport(request, timeout):
            captured.update(json.loads(request.data.decode("utf-8")))
            return FakeResponse()

        result = call_openai_responses(
            input_text="Return JSON.",
            instructions="Return JSON only.",
            config=config,
            text_format=build_openai_text_format("app_file_generation"),
            transport=transport,
        )

        self.assertTrue(result.ok)
        self.assertEqual(captured["text"]["format"]["type"], "json_schema")
        self.assertTrue(captured["text"]["format"]["strict"])
        self.assertEqual(captured["text"]["format"]["name"], "app_file_generation")

    def test_valid_app_file_generation_fixtures_pass_schema_validation(self) -> None:
        cases = {
            "business_idea_scorer.json": "business_idea_scorer",
            "budget_calculator.json": "budget_calculator",
            "flashcard_helper.json": "flashcard_helper",
        }
        for filename, shape in cases.items():
            with self.subTest(filename=filename):
                payload = self.app_file_fixture(filename)
                result = sprintos.validate_app_file_payload_for_shape(payload, shape)
                self.assertTrue(result["ok"], result)

    def test_budget_calculator_fixture_reads_income_and_expense_values(self) -> None:
        payload = self.app_file_fixture("budget_calculator.json")
        files = self.app_file_contents(payload)

        checks = static_app_shape_verification_checks(
            "budget_calculator",
            index_html=files["index.html"],
            app_js=files["app.js"],
            readme_text=files["README.md"],
        )

        self.assertFalse([item for item in checks if item["status"] == "fail"])
        self.assertIn("document.getElementById('budget-income').value", files["app.js"])
        self.assertRegex(files["app.js"], r"document\.getElementById\('budget-(rent|food|housing|transport|other)'\)\.value")

    def test_flashcard_helper_fixture_has_visible_local_ai_limitation_note(self) -> None:
        payload = self.app_file_fixture("flashcard_helper.json")
        files = self.app_file_contents(payload)
        limitation = "This prototype builds study cards locally from your notes. It does not call live AI or external services inside the browser."

        checks = static_app_shape_verification_checks(
            "flashcard_helper",
            index_html=files["index.html"],
            app_js=files["app.js"],
            readme_text=files["README.md"],
        )

        self.assertIn(limitation, files["index.html"])
        self.assertIn(limitation, files["README.md"])
        self.assertFalse([item for item in checks if item["status"] != "pass"], checks)

    def test_budget_calculator_with_right_ids_but_no_value_reads_fails_shape_validation(self) -> None:
        payload = self.app_file_fixture("budget_calculator.json")
        payload["files"][2]["content"] = (
            "function calculateBudget(){"
            "const income=3000;const food=450;const savings=income-food;"
            "document.getElementById('budget-savings').textContent=String(savings);"
            "document.getElementById('budget-breakdown').textContent='Expenses: '+food;"
            "document.getElementById('budget-recommendation').textContent='Set aside the surplus.';"
            "}"
            "document.getElementById('budget-run').addEventListener('click',calculateBudget);"
        )

        provider = self.assert_app_generation_failure_code(payload, "app_shape_validation_failed", shape="budget_calculator")
        failures = provider.validation_details["app_shape_failures"]

        self.assertTrue(any("income_input_is_read" in item for item in failures))
        self.assertTrue(any("expense_input_is_read" in item for item in failures))

    def test_budget_calculator_that_reads_values_but_skips_recommendation_update_fails(self) -> None:
        payload = self.app_file_fixture("budget_calculator.json")
        payload["files"][2]["content"] = (
            "function calculateBudget(){"
            "const income=Number(document.getElementById('budget-income').value)||0;"
            "const food=Number(document.getElementById('budget-food').value)||0;"
            "const savings=income-food;"
            "document.getElementById('budget-savings').textContent=String(savings);"
            "document.getElementById('budget-breakdown').textContent='Food: '+food;"
            "}"
            "document.getElementById('budget-run').addEventListener('click',calculateBudget);"
        )

        provider = self.assert_app_generation_failure_code(payload, "app_shape_validation_failed", shape="budget_calculator")

        self.assertTrue(
            any("recommendation_output_updates" in item for item in provider.validation_details["app_shape_failures"])
        )

    def test_mocked_ai_budget_output_uses_improved_generation_contract(self) -> None:
        payload = self.app_file_fixture("budget_calculator.json")
        calls: list[dict[str, Any]] = []

        def provider(**kwargs):
            calls.append(kwargs)
            return fake_provider_result(
                text=json.dumps(payload),
                parsed_json=payload,
                ok=True,
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                task_name="app_file_generation",
            )

        data, provider_result = generate_json_with_ai(
            task_name="app_file_generation",
            instructions=sprintos.app_file_generation_instructions("budget_calculator"),
            user_input="Generate a useful local Budget Snapshot app.",
            expected_schema_description="app file generation schema",
            fallback_factory=self.app_file_generation_payload(),
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": "sk-openai-budget-contract"}
            ),
            provider_callable=provider,
            validator=lambda candidate: sprintos.validate_app_file_payload_for_shape(candidate, "budget_calculator"),
        )
        files = self.app_file_contents(data)

        self.assertTrue(provider_result.used_ai)
        self.assertEqual(len(calls), 1)
        self.assertIn('document.getElementById("budget-income").value', calls[0]["instructions"])
        self.assertIn("handle blank/invalid numbers as 0", calls[0]["instructions"])
        self.assertIn("document.getElementById('budget-income').value", files["app.js"])
        self.assertIn("document.getElementById('budget-food').value", files["app.js"])
        self.assertNotIn("fetch(", files["app.js"])
        self.assertNotIn("XMLHttpRequest", files["app.js"])
        self.assertNotIn("sendBeacon", files["app.js"])

    def test_valid_openai_structured_output_passes_app_validation(self) -> None:
        payload = self.app_file_fixture("business_idea_scorer.json")
        data, provider = generate_json_with_ai(
            task_name="app_file_generation",
            instructions=sprintos.app_file_generation_instructions("business_idea_scorer"),
            user_input="Generate a local scorer.",
            expected_schema_description="app file generation schema",
            fallback_factory=self.app_file_generation_payload(),
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": "sk-openai-valid-structured"}
            ),
            provider_callable=lambda **_: fake_provider_result(text=json.dumps(payload), parsed_json=payload, ok=True, provider="openai"),
            validator=lambda candidate: sprintos.validate_app_file_payload_for_shape(candidate, "business_idea_scorer"),
        )

        self.assertTrue(provider.used_ai)
        self.assertEqual(data["app_name"], "Idea Scoreboard")

    def test_valid_deepseek_json_output_passes_app_validation(self) -> None:
        payload = self.app_file_fixture("flashcard_helper.json")
        data, provider = generate_json_with_ai(
            task_name="app_file_generation",
            instructions=sprintos.app_file_generation_instructions("flashcard_helper"),
            user_input="Generate a local flashcard helper.",
            expected_schema_description="app file generation schema",
            fallback_factory=self.app_file_generation_payload(),
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "deepseek", "SPRINTOS_AI_ENABLED": "true", "DEEPSEEK_API_KEY": "sk-deepseek-valid-json"}
            ),
            provider_callable=lambda **_: fake_provider_result(text=json.dumps(payload), parsed_json=payload, ok=True, provider="deepseek", model=DEFAULT_DEEPSEEK_MODEL),
            validator=lambda candidate: sprintos.validate_app_file_payload_for_shape(candidate, "flashcard_helper"),
        )

        self.assertTrue(provider.used_ai)
        self.assertEqual(data["app_name"], "Study Card Builder")

    def assert_app_generation_failure_code(self, payload: dict, expected_code: str, *, shape: str = "business_idea_scorer") -> AIProviderResult:
        _, provider = generate_json_with_ai(
            task_name="app_file_generation",
            instructions=sprintos.app_file_generation_instructions(shape),
            user_input="Generate a local app.",
            expected_schema_description="app file generation schema",
            fallback_factory=self.app_file_generation_payload(),
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": "sk-openai-validation-detail"}
            ),
            provider_callable=lambda **_: fake_provider_result(text=json.dumps(payload), parsed_json=payload, ok=True, provider="openai"),
            validator=lambda candidate: sprintos.validate_app_file_payload_for_shape(candidate, shape),
        )
        self.assertFalse(provider.used_ai)
        self.assertEqual(provider.fallback_reason, expected_code)
        self.assertEqual(provider.validation_details.get("failure_code"), expected_code)
        self.assertNotIn("sk-openai-validation-detail", json.dumps(provider.validation_details))
        return provider

    def test_app_schema_failure_missing_app_name_has_safe_detail(self) -> None:
        payload = self.app_file_fixture("business_idea_scorer.json")
        payload.pop("app_name")
        provider = self.assert_app_generation_failure_code(payload, "schema_validation_failed")
        self.assertIn("app_name", provider.validation_details["missing_top_level_fields"])

    def test_app_schema_failure_missing_files_has_safe_detail(self) -> None:
        payload = self.app_file_fixture("business_idea_scorer.json")
        payload["files"] = [item for item in payload["files"] if item["filename"] != "app.js"]
        provider = self.assert_app_generation_failure_code(payload, "missing_required_files")
        self.assertIn("app.js", provider.validation_details["missing_required_files"])

    def test_app_schema_failure_invalid_filename_has_safe_detail(self) -> None:
        payload = self.app_file_fixture("business_idea_scorer.json")
        payload["files"][0]["filename"] = "src/index.html"
        provider = self.assert_app_generation_failure_code(payload, "invalid_generated_filename")
        self.assertIn("files[0].filename", provider.validation_details["invalid_filenames"])

    def test_app_schema_failure_missing_test_plan_has_safe_detail(self) -> None:
        payload = self.app_file_fixture("business_idea_scorer.json")
        payload["files"] = [item for item in payload["files"] if item["filename"] != "TEST_PLAN.md"]
        provider = self.assert_app_generation_failure_code(payload, "missing_required_files")
        self.assertIn("TEST_PLAN.md", provider.validation_details["missing_required_files"])

    def test_app_shape_failure_has_safe_detail(self) -> None:
        payload = self.app_file_fixture("business_idea_scorer.json")
        payload["files"][0]["content"] = payload["files"][0]["content"].replace("idea-score", "idea-score-missing")
        provider = self.assert_app_generation_failure_code(payload, "app_shape_validation_failed")
        self.assertTrue(provider.validation_details["app_shape_failures"])

    def test_business_idea_scorer_missing_risk_breakdown_fails_shape_validation(self) -> None:
        payload = self.app_file_fixture("business_idea_scorer.json")
        payload["files"][0]["content"] = payload["files"][0]["content"].replace("data-template-marker=\"risk_breakdown\"", "")

        provider = self.assert_app_generation_failure_code(payload, "app_shape_validation_failed")

        self.assertTrue(any("risk_output_exists" in item for item in provider.validation_details["app_shape_failures"]))

    def test_business_idea_scorer_missing_next_action_fails_shape_validation(self) -> None:
        payload = self.app_file_fixture("business_idea_scorer.json")
        payload["files"][0]["content"] = payload["files"][0]["content"].replace("id=\"idea-next-action\"", "id=\"idea-next-step\"")
        payload["files"][2]["content"] = payload["files"][2]["content"].replace("idea-next-action", "idea-next-step")

        provider = self.assert_app_generation_failure_code(payload, "app_shape_validation_failed")

        self.assertTrue(any("next_action_output_exists" in item for item in provider.validation_details["app_shape_failures"]))

    def test_budget_calculator_missing_numeric_inputs_fails_shape_validation(self) -> None:
        payload = self.app_file_fixture("budget_calculator.json")
        payload["files"][0]["content"] = payload["files"][0]["content"].replace("type=\"number\"", "type=\"text\"")

        provider = self.assert_app_generation_failure_code(payload, "app_shape_validation_failed", shape="budget_calculator")

        self.assertTrue(any("income_and_expense_input_markers_exist" in item for item in provider.validation_details["app_shape_failures"]))

    def test_budget_calculator_missing_recommendation_fails_shape_validation(self) -> None:
        payload = self.app_file_fixture("budget_calculator.json")
        payload["files"][0]["content"] = payload["files"][0]["content"].replace("data-template-marker=\"recommendation\"", "")

        provider = self.assert_app_generation_failure_code(payload, "app_shape_validation_failed", shape="budget_calculator")

        self.assertTrue(any("recommendation_output_exists" in item for item in provider.validation_details["app_shape_failures"]))

    def test_budget_calculator_missing_result_surfaces_fails_shape_validation(self) -> None:
        payload = self.app_file_fixture("budget_calculator.json")
        for old, new in (
            ("budget-savings", "budget-leftover"),
            ("budget-breakdown", "budget-lines"),
            ("budget-recommendation", "budget-advice"),
        ):
            payload["files"][0]["content"] = payload["files"][0]["content"].replace(old, new)
            payload["files"][2]["content"] = payload["files"][2]["content"].replace(old, new)

        provider = self.assert_app_generation_failure_code(payload, "app_shape_validation_failed", shape="budget_calculator")
        failures = provider.validation_details["app_shape_failures"]

        self.assertTrue(any("savings_output_exists" in item for item in failures))
        self.assertTrue(any("breakdown_output_exists" in item for item in failures))
        self.assertTrue(any("recommendation_output_exists" in item for item in failures))

    def test_app_safety_failure_has_safe_detail(self) -> None:
        payload = self.app_file_fixture("business_idea_scorer.json")
        payload["files"][2]["content"] += "\nfetch('https://example.com/data')\n"
        provider = self.assert_app_generation_failure_code(payload, "app_safety_validation_failed")
        self.assertIn("files:browser_network_calls", provider.validation_details["app_safety_failures"])

    def test_report_only_schema_failure_does_not_create_offline_app_files(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-report-only-active-test"
        os.environ["SPRINTOS_APP_GENERATION_FALLBACK_MODE"] = "report_only"
        payload = self.app_file_generation_payload()
        payload["files"] = [item for item in payload["files"] if item["filename"] != "TEST_PLAN.md"]

        with mock.patch(
            "sprintos_core.ai_provider.call_openai_responses",
            return_value=fake_provider_result(
                text=json.dumps(payload),
                parsed_json=payload,
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                task_name="app_file_generation",
            ),
        ):
            quick_launch = self.generate_quick_launch(
                raw_idea="Build a business idea scoring app that feels like a real local tool.",
                generation_mode="ai",
            )

        project = sprintos.get_project(quick_launch["project_id"])
        report_dir = Path(quick_launch["failure_report_path"])
        summary = json.loads((report_dir / "failure-summary.json").read_text(encoding="utf-8"))
        app_state = project["app_state_summary"]

        self.assertTrue(quick_launch["ai_generation_failed"])
        self.assertIsNone(project["latest_prototype"])
        self.assertFalse(list((sprintos.EXPORT_DIR / "prototypes").glob("*")))
        self.assertEqual(summary["failure_category"], "missing_required_files")
        self.assertIn("TEST_PLAN.md", summary["validation_details"]["missing_required_files"])
        self.assertIn("No app was created", app_state["app_generation_status"]["summary"])
        self.assertNotIn("Using local template", app_state["app_generation_status"]["summary"])
        self.assertFalse(app_state["what_exists"]["preview_available"])
        encoded = "\n".join(path.read_text(encoding="utf-8") for path in report_dir.iterdir())
        self.assertNotIn("sk-openai-report-only-active-test", encoded)

    def test_report_only_app_shape_failure_has_specific_safe_next_action(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-report-only-shape-test"
        os.environ["SPRINTOS_APP_GENERATION_FALLBACK_MODE"] = "report_only"
        payload = self.app_file_fixture("business_idea_scorer.json")
        payload["files"][0]["content"] = payload["files"][0]["content"].replace("id=\"idea-next-action\"", "id=\"idea-next-step\"")
        payload["files"][2]["content"] = payload["files"][2]["content"].replace("idea-next-action", "idea-next-step")

        with mock.patch(
            "sprintos_core.ai_provider.call_openai_responses",
            return_value=fake_provider_result(
                text=json.dumps(payload),
                parsed_json=payload,
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                task_name="app_file_generation",
            ),
        ):
            quick_launch = self.generate_quick_launch(
                raw_idea="Build a business idea scoring app that evaluates startup ideas.",
                generation_mode="ai",
            )

        project = sprintos.get_project(quick_launch["project_id"])
        report_dir = Path(quick_launch["failure_report_path"])
        summary = json.loads((report_dir / "failure-summary.json").read_text(encoding="utf-8"))
        report_text = (report_dir / "app-generation-failure.md").read_text(encoding="utf-8")
        expected_action = "The AI output missed required app surfaces. Retry Create App. If this repeats, use local template fallback or simplify the prompt."

        self.assertTrue(quick_launch["ai_generation_failed"])
        self.assertIsNone(project["latest_prototype"])
        self.assertEqual(summary["failure_category"], "app_shape_validation_failed")
        self.assertEqual(summary["suggested_next_action"], expected_action)
        self.assertIn("next_action_output_exists", json.dumps(summary["validation_details"]))
        self.assertIn(expected_action, report_text)
        self.assertNotIn("sk-openai-report-only-shape-test", report_text)

    def test_template_fallback_mode_still_generates_offline_app(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-template-fallback-test"
        os.environ["SPRINTOS_APP_GENERATION_FALLBACK_MODE"] = "template"

        with mock.patch(
            "sprintos_core.ai_provider.call_openai_responses",
            return_value=fake_provider_result(
                ok=False,
                error="OpenAI request failed: timed out",
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                used_ai=False,
                fallback_reason="openai_timeout",
                task_name="app_file_generation",
            ),
        ):
            quick_launch = self.generate_quick_launch(
                raw_idea="Build a business idea scoring app that feels like a real local tool.",
                generation_mode="ai",
            )

        project = sprintos.get_project(quick_launch["project_id"])
        self.assertFalse(quick_launch.get("ai_generation_failed"))
        self.assertIsNotNone(project["latest_prototype"])
        self.assertTrue(Path(project["latest_prototype"]["path"], "index.html").exists())
        self.assertIn("Using local template", project["app_state_summary"]["app_generation_status"]["summary"])

    def test_env_loader_loads_simple_key_values_without_overriding_existing_env(self) -> None:
        env_key = "sk" + "-test-from-env"
        env_path = self.root / ".env"
        env_path.write_text(
            f"# comment\nSPRINTOS_AI_PROVIDER=openai\nSPRINTOS_AI_ENABLED=true\nOPENAI_API_KEY={env_key}\n\nSPRINTOS_MODEL=gpt-4.1-mini\n",
            encoding="utf-8",
        )
        os.environ["SPRINTOS_AI_PROVIDER"] = "offline"
        stdout = io.StringIO()

        with mock.patch("sys.stdout", stdout):
            loaded = load_local_env(self.root)

        self.assertEqual(loaded, env_path)
        self.assertEqual(os.environ["SPRINTOS_AI_PROVIDER"], "offline")
        self.assertEqual(os.environ["SPRINTOS_AI_ENABLED"], "false")
        self.assertEqual(os.environ["OPENAI_API_KEY"], "")
        self.assertEqual(stdout.getvalue(), "")

    def test_env_loader_uses_last_duplicate_dotenv_value_without_overriding_process_env(self) -> None:
        env_path = self.root / ".env"
        env_key = "sk" + "-test-from-env"
        env_path.write_text(
            "\n".join(
                [
                    "SPRINTOS_AI_PROVIDER=openai",
                    "SPRINTOS_AI_PROVIDER=deepseek",
                    "SPRINTOS_AI_ENABLED=true",
                    "SPRINTOS_AI_TIMEOUT_SECONDS=90",
                    "SPRINTOS_AI_MAX_OUTPUT_TOKENS=6000",
                    f"DEEPSEEK_API_KEY={env_key}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        for key in (
            "SPRINTOS_AI_PROVIDER",
            "SPRINTOS_AI_ENABLED",
            "SPRINTOS_MODEL",
            "SPRINTOS_AI_TIMEOUT_SECONDS",
            "SPRINTOS_AI_MAX_OUTPUT_TOKENS",
            "DEEPSEEK_API_KEY",
        ):
            os.environ.pop(key, None)

        self.assertEqual(load_local_env(self.root), env_path)
        payload = sprintos.ai_status_payload()

        self.assertEqual(payload["provider"], "deepseek")
        self.assertTrue(payload["enabled"])
        self.assertTrue(payload["api_key_present"])
        self.assertEqual(payload["app_generation_timeout_seconds"], 90)
        self.assertEqual(payload["app_generation_max_output_tokens"], 6000)

    def test_config_defaults_to_offline_disabled(self) -> None:
        config = load_ai_provider_config({})
        self.assertEqual(config.provider, "offline")
        self.assertFalse(config.enabled)
        self.assertFalse(config.api_key_present)
        self.assertEqual(config.model, "offline")
        self.assertEqual(config.base_url, "")
        self.assertFalse(ai_enabled(config))

    def test_config_supports_openai_provider(self) -> None:
        api_key = "sk" + "-test-present"
        config = load_ai_provider_config(
            {
                "SPRINTOS_AI_PROVIDER": "openai",
                "SPRINTOS_AI_ENABLED": "true",
                "OPENAI_API_KEY": api_key,
                "SPRINTOS_MODEL": "gpt-4.1-mini",
            }
        )
        self.assertEqual(config.provider, "openai")
        self.assertTrue(config.enabled)
        self.assertTrue(config.api_key_present)
        self.assertEqual(config.base_url, "")
        self.assertTrue(ai_enabled(config))

    def test_config_supports_deepseek_provider(self) -> None:
        api_key = "sk" + "-deepseek-present"
        config = load_ai_provider_config(
            {
                "SPRINTOS_AI_PROVIDER": "deepseek",
                "SPRINTOS_AI_ENABLED": "true",
                "DEEPSEEK_API_KEY": api_key,
            }
        )
        self.assertEqual(config.provider, "deepseek")
        self.assertTrue(config.enabled)
        self.assertTrue(config.api_key_present)
        self.assertEqual(config.model, DEFAULT_DEEPSEEK_MODEL)
        self.assertEqual(config.base_url, DEFAULT_DEEPSEEK_BASE_URL)
        self.assertTrue(ai_enabled(config))

    def test_deepseek_requires_deepseek_key_not_openai_key(self) -> None:
        config = load_ai_provider_config(
            {
                "SPRINTOS_AI_PROVIDER": "deepseek",
                "SPRINTOS_AI_ENABLED": "true",
                "OPENAI_API_KEY": "sk-openai-only",
            }
        )
        self.assertEqual(config.provider, "deepseek")
        self.assertFalse(config.api_key_present)
        self.assertFalse(ai_enabled(config))

    def test_openai_requires_openai_key_not_deepseek_key(self) -> None:
        config = load_ai_provider_config(
            {
                "SPRINTOS_AI_PROVIDER": "openai",
                "SPRINTOS_AI_ENABLED": "true",
                "DEEPSEEK_API_KEY": "sk-deepseek-only",
            }
        )
        self.assertEqual(config.provider, "openai")
        self.assertFalse(config.api_key_present)
        self.assertFalse(ai_enabled(config))

    def test_deepseek_defaults_model_and_base_url_when_unset(self) -> None:
        config = load_ai_provider_config(
            {
                "SPRINTOS_AI_PROVIDER": "deepseek",
                "SPRINTOS_AI_ENABLED": "false",
            }
        )
        self.assertEqual(config.model, DEFAULT_DEEPSEEK_MODEL)
        self.assertEqual(config.base_url, DEFAULT_DEEPSEEK_BASE_URL)

    def test_unknown_provider_falls_back_safely(self) -> None:
        api_key = "sk" + "-test"
        config = load_ai_provider_config({"SPRINTOS_AI_PROVIDER": "weird", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": api_key})
        self.assertEqual(config.provider, "offline")
        self.assertFalse(ai_enabled(config))

    def test_parse_response_text_extracts_output_text(self) -> None:
        payload = {
            "output": [
                {
                    "content": [
                        {"type": "output_text", "text": '{"status":"ok"}'},
                    ]
                }
            ]
        }
        self.assertEqual(parse_response_text(payload), '{"status":"ok"}')

    def test_parse_response_text_handles_malformed_payload(self) -> None:
        self.assertEqual(parse_response_text({"output": [{"content": [None, {"type": "x"}]}]}), "")
        self.assertEqual(parse_response_text([]), "")

    def test_parse_deepseek_chat_text_extracts_message_content(self) -> None:
        payload = {"choices": [{"message": {"content": '{"status":"ok"}'}}]}
        self.assertEqual(parse_deepseek_chat_text(payload), '{"status":"ok"}')

    def test_parse_deepseek_chat_text_handles_missing_choices(self) -> None:
        self.assertEqual(parse_deepseek_chat_text({"choices": []}), "")
        self.assertEqual(parse_deepseek_chat_text({"choices": [{"message": {}}]}), "")
        self.assertEqual(parse_deepseek_chat_text([]), "")

    def test_call_deepseek_chat_completions_returns_valid_parsed_json_from_mocked_response(self) -> None:
        os.environ["DEEPSEEK_API_KEY"] = "sk-deepseek-live"
        config = load_ai_provider_config(
            {
                "SPRINTOS_AI_PROVIDER": "deepseek",
                "SPRINTOS_AI_ENABLED": "true",
                "DEEPSEEK_API_KEY": "sk-deepseek-live",
            }
        )

        class FakeResponse:
            def __init__(self, body: str) -> None:
                self.body = body.encode("utf-8")

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return self.body

        def transport(request, timeout):
            self.assertEqual(timeout, config.timeout_seconds)
            self.assertEqual(request.full_url, DEFAULT_DEEPSEEK_BASE_URL + "/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer " + "sk-deepseek-live")
            payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual(payload["model"], DEFAULT_DEEPSEEK_MODEL)
            self.assertEqual(payload["response_format"], {"type": "json_object"})
            return FakeResponse(json.dumps({"choices": [{"message": {"content": '{"status":"ok"}'}}]}))

        result = call_deepseek_chat_completions(
            input_text='Return {"status":"ok"}',
            instructions="Return JSON only.",
            config=config,
            response_format={"type": "json_object"},
            transport=transport,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.parsed_json, {"status": "ok"})
        self.assertEqual(result.provider, "deepseek")

    def test_openai_app_file_generation_request_uses_strict_json_schema_text_format(self) -> None:
        api_key = "sk-openai-live-test"
        os.environ["OPENAI_API_KEY"] = api_key
        config = load_ai_provider_config(
            {
                "SPRINTOS_AI_PROVIDER": "openai",
                "SPRINTOS_AI_ENABLED": "true",
                "OPENAI_API_KEY": api_key,
                "SPRINTOS_MODEL": "gpt-5.4-mini",
            }
        )
        payload = self.app_file_generation_payload()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return json.dumps({"output": [{"content": [{"type": "output_text", "text": json.dumps(payload)}]}]}).encode("utf-8")

        def transport(request, timeout):
            self.assertEqual(timeout, config.timeout_seconds)
            self.assertEqual(request.full_url, "https://api.openai.com/v1/responses")
            self.assertEqual(request.headers["Authorization"], "Bearer " + api_key)
            request_payload = json.loads(request.data.decode("utf-8"))
            self.assertEqual(request_payload["model"], "gpt-5.4-mini")
            self.assertEqual(request_payload["input"], "Generate a local app.")
            self.assertEqual(request_payload["instructions"], "Return JSON only.")
            self.assertEqual(request_payload["max_output_tokens"], config.max_output_tokens)
            text_format = request_payload["text"]["format"]
            self.assertEqual(text_format["type"], "json_schema")
            self.assertNotEqual(text_format["type"], "text")
            self.assertTrue(text_format["strict"])
            self.assertEqual(text_format["name"], "app_file_generation")
            self.assertEqual(text_format["schema"]["required"], list(build_ai_task_json_schema("app_file_generation")["required"]))
            self.assertIn("files", text_format["schema"]["properties"])
            self.assertEqual(text_format["schema"]["properties"]["files"]["items"]["required"], ["filename", "content"])
            return FakeResponse()

        result = call_openai_responses(
            input_text="Generate a local app.",
            instructions="Return JSON only.",
            config=config,
            text_format={
                "type": "json_schema",
                "name": "app_file_generation",
                "schema": build_ai_task_json_schema("app_file_generation"),
                "strict": True,
            },
            transport=transport,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.parsed_json["app_name"], "Idea Scoreboard")

    def test_generate_json_with_ai_sends_openai_app_file_generation_schema(self) -> None:
        api_key = "sk-openai-schema-test"
        captured: dict[str, Any] = {}
        payload = self.app_file_generation_payload()

        def provider(**kwargs):
            captured.update(kwargs)
            return fake_provider_result(
                text=json.dumps(payload),
                parsed_json=payload,
                ok=True,
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                task_name="app_file_generation",
            )

        data, provider_result = generate_json_with_ai(
            task_name="app_file_generation",
            instructions="Task name: app_file_generation\nReturn JSON only.",
            user_input="Generate a local app.",
            expected_schema_description="app file generation schema",
            fallback_factory=self.app_file_generation_payload(),
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": api_key}
            ),
            provider_callable=provider,
        )

        text_format = captured["text_format"]
        self.assertEqual(text_format["type"], "json_schema")
        self.assertTrue(text_format["strict"])
        self.assertEqual(text_format["schema"]["required"], list(build_ai_task_json_schema("app_file_generation")["required"]))
        self.assertEqual(data["app_name"], "Idea Scoreboard")
        self.assertTrue(provider_result.used_ai)

    def test_generate_json_with_ai_returns_fallback_when_disabled(self) -> None:
        data, provider = generate_json_with_ai(
            task_name="disabled_case",
            instructions="Return JSON.",
            user_input="ignored",
            expected_schema_description='{"title":"value"}',
            fallback_factory={"title": "offline"},
            config=load_ai_provider_config({"SPRINTOS_AI_PROVIDER": "offline"}),
        )
        self.assertEqual(data["title"], "offline")
        self.assertFalse(provider.used_ai)

    def test_generate_json_with_ai_returns_fallback_on_malformed_json(self) -> None:
        api_key = "sk" + "-test"
        data, provider = generate_json_with_ai(
            task_name="bad_json",
            instructions="Return JSON.",
            user_input="ignored",
            expected_schema_description='{"title":"value"}',
            fallback_factory={"title": "offline"},
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": api_key}
            ),
            provider_callable=lambda **_: fake_provider_result(text="not-json", parsed_json=None, ok=True),
        )
        self.assertEqual(data["title"], "offline")
        self.assertIn("valid JSON", provider.error)
        self.assertEqual(provider.fallback_reason, "openai_invalid_json")
        self.assertFalse(provider.used_ai)

    def test_generate_json_with_ai_returns_fallback_when_required_fields_are_missing(self) -> None:
        api_key = "sk" + "-test"
        data, provider = generate_json_with_ai(
            task_name="missing_fields",
            instructions="Return JSON.",
            user_input="ignored",
            expected_schema_description='{"title":"value","summary":"value"}',
            fallback_factory={"title": "offline", "summary": "offline"},
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": api_key}
            ),
            provider_callable=lambda **_: fake_provider_result(text='{"title":"ai"}', parsed_json={"title": "ai"}, ok=True),
        )
        self.assertEqual(data["summary"], "offline")
        self.assertEqual(provider.fallback_reason, "openai_schema_invalid")
        self.assertIn("missing required fields", provider.error.lower())

    def test_generate_json_with_ai_returns_app_validation_fallback_for_missing_required_app_file(self) -> None:
        api_key = "sk-openai-missing-app-file-test"
        payload = self.app_file_generation_payload()
        payload["files"] = [item for item in payload["files"] if item["filename"] != "app.js"]

        data, provider = generate_json_with_ai(
            task_name="app_file_generation",
            instructions="Task name: app_file_generation\nReturn JSON only.",
            user_input="Generate a local app.",
            expected_schema_description="app file generation schema",
            fallback_factory=self.app_file_generation_payload(),
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": api_key}
            ),
            provider_callable=lambda **_: fake_provider_result(
                text=json.dumps(payload),
                parsed_json=payload,
                ok=True,
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                task_name="app_file_generation",
            ),
        )

        self.assertIn("app.js", [item["filename"] for item in data["files"]])
        self.assertEqual(provider.fallback_reason, "missing_required_files")
        self.assertFalse(provider.used_ai)

    def test_app_file_generation_retries_once_on_invalid_json_then_uses_repaired_payload(self) -> None:
        api_key = "sk-openai-app-retry-json-test"
        payload = self.app_file_generation_payload()
        calls: list[dict[str, Any]] = []

        def provider(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return fake_provider_result(text="not-json", parsed_json=None, ok=True, provider="openai", model=DEFAULT_OPENAI_MODEL)
            return fake_provider_result(
                text=json.dumps(payload),
                parsed_json=payload,
                ok=True,
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                task_name="app_file_generation",
            )

        data, provider_result = generate_json_with_ai(
            task_name="app_file_generation",
            instructions="Task name: app_file_generation\nReturn JSON only.",
            user_input="Generate a local app.",
            expected_schema_description="app file generation schema",
            fallback_factory=self.app_file_generation_payload(),
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": api_key}
            ),
            provider_callable=provider,
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(data["app_name"], "Idea Scoreboard")
        self.assertTrue(provider_result.used_ai)
        self.assertIn("app_file_generation_retry:invalid_json", provider_result.warnings)
        self.assertIn("Retry repair for app_file_generation", calls[1]["instructions"])
        self.assertNotIn("not-json", calls[1]["instructions"])

    def test_app_file_generation_retries_once_on_transient_provider_failure(self) -> None:
        api_key = "sk-openai-app-retry-timeout-test"
        payload = self.app_file_generation_payload()
        calls: list[dict[str, Any]] = []

        def provider(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                return fake_provider_result(
                    ok=False,
                    text="",
                    parsed_json=None,
                    error="OpenAI request failed: timed out",
                    provider="openai",
                    model=DEFAULT_OPENAI_MODEL,
                    used_ai=False,
                    fallback_reason="openai_timeout",
                )
            return fake_provider_result(
                text=json.dumps(payload),
                parsed_json=payload,
                ok=True,
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                task_name="app_file_generation",
            )

        data, provider_result = generate_json_with_ai(
            task_name="app_file_generation",
            instructions="Task name: app_file_generation\nReturn JSON only.",
            user_input="Generate a local app.",
            expected_schema_description="app file generation schema",
            fallback_factory=self.app_file_generation_payload(),
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": api_key}
            ),
            provider_callable=provider,
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(data["app_name"], "Idea Scoreboard")
        self.assertTrue(provider_result.used_ai)
        self.assertIn("app_file_generation_retry:provider_transient", provider_result.warnings)

    def test_app_file_generation_retries_json_shape_failure_then_uses_repaired_payload(self) -> None:
        api_key = "sk-openai-app-retry-shape-test"
        bad_payload = self.app_file_generation_payload()
        bad_payload["files"] = [item for item in bad_payload["files"] if item["filename"] != "app.js"]
        fixed_payload = self.app_file_generation_payload()
        calls: list[dict[str, Any]] = []

        def provider(**kwargs):
            calls.append(kwargs)
            payload = bad_payload if len(calls) == 1 else fixed_payload
            return fake_provider_result(
                text=json.dumps(payload),
                parsed_json=payload,
                ok=True,
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                task_name="app_file_generation",
            )

        data, provider_result = generate_json_with_ai(
            task_name="app_file_generation",
            instructions="Task name: app_file_generation\nReturn JSON only.",
            user_input="Generate a local app.",
            expected_schema_description="app file generation schema",
            fallback_factory=self.app_file_generation_payload(),
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": api_key}
            ),
            provider_callable=provider,
        )

        self.assertEqual(len(calls), 2)
        self.assertIn("app.js", [item["filename"] for item in data["files"]])
        self.assertTrue(provider_result.used_ai)
        self.assertIn("app_file_generation_retry:json_shape", provider_result.warnings)

    def test_app_file_generation_retries_app_shape_failure_with_missing_surface_detail(self) -> None:
        api_key = "sk-openai-app-retry-app-shape-test"
        bad_payload = self.app_file_fixture("business_idea_scorer.json")
        bad_payload["files"][0]["content"] = bad_payload["files"][0]["content"].replace("id=\"idea-risks\"", "id=\"idea-risks-missing\"")
        fixed_payload = self.app_file_fixture("business_idea_scorer.json")
        calls: list[dict[str, Any]] = []

        def provider(**kwargs):
            calls.append(kwargs)
            payload = bad_payload if len(calls) == 1 else fixed_payload
            return fake_provider_result(
                text=json.dumps(payload),
                parsed_json=payload,
                ok=True,
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                task_name="app_file_generation",
            )

        data, provider_result = generate_json_with_ai(
            task_name="app_file_generation",
            instructions=sprintos.app_file_generation_instructions("business_idea_scorer"),
            user_input="Generate a local business idea scorer.",
            expected_schema_description="app file generation schema",
            fallback_factory=self.app_file_generation_payload(),
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": api_key}
            ),
            provider_callable=provider,
            validator=lambda candidate: sprintos.validate_app_file_payload_for_shape(candidate, "business_idea_scorer"),
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(data["app_name"], "Idea Scoreboard")
        self.assertTrue(provider_result.used_ai)
        self.assertIn("app_file_generation_retry:app_shape", provider_result.warnings)
        self.assertIn("Fix these missing required surfaces", calls[1]["instructions"])
        self.assertIn("risk_output_exists", calls[1]["instructions"])

    def test_flashcard_helper_repair_guidance_requires_visible_limitation_note(self) -> None:
        api_key = "sk-openai-app-retry-flashcard-shape-test"
        bad_payload = self.app_file_fixture("flashcard_helper.json")
        bad_payload["files"][0]["content"] = bad_payload["files"][0]["content"].replace(
            'data-template-marker="flashcard-cards"',
            'data-template-marker="plain-output"',
        )
        fixed_payload = self.app_file_fixture("flashcard_helper.json")
        calls: list[dict[str, Any]] = []

        def provider(**kwargs):
            calls.append(kwargs)
            payload = bad_payload if len(calls) == 1 else fixed_payload
            return fake_provider_result(
                text=json.dumps(payload),
                parsed_json=payload,
                ok=True,
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                task_name="app_file_generation",
            )

        data, provider_result = generate_json_with_ai(
            task_name="app_file_generation",
            instructions=sprintos.app_file_generation_instructions("flashcard_helper"),
            user_input="Generate a local study card builder.",
            expected_schema_description="app file generation schema",
            fallback_factory=self.app_file_generation_payload(),
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": api_key}
            ),
            provider_callable=provider,
            validator=lambda candidate: sprintos.validate_app_file_payload_for_shape(candidate, "flashcard_helper"),
        )

        self.assertEqual(len(calls), 2)
        self.assertEqual(data["app_name"], "Study Card Builder")
        self.assertTrue(provider_result.used_ai)
        self.assertIn("app_file_generation_retry:app_shape", provider_result.warnings)
        self.assertIn("For flashcard_helper repairs", calls[1]["instructions"])
        self.assertIn(
            "This prototype builds study cards locally from your notes. It does not call live AI or external services inside the browser.",
            calls[1]["instructions"],
        )

    def test_app_file_generation_does_not_retry_safety_validation_failure(self) -> None:
        api_key = "sk-openai-app-no-retry-safety-test"
        unsafe_payload = self.app_file_generation_payload()
        for item in unsafe_payload["files"]:
            if item["filename"] == "index.html":
                item["content"] = item["content"].replace("</body>", '<script src="https://cdn.example.com/app.js"></script></body>')
        calls: list[dict[str, Any]] = []

        def provider(**kwargs):
            calls.append(kwargs)
            return fake_provider_result(
                text=json.dumps(unsafe_payload),
                parsed_json=unsafe_payload,
                ok=True,
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                task_name="app_file_generation",
            )

        data, provider_result = generate_json_with_ai(
            task_name="app_file_generation",
            instructions="Task name: app_file_generation\nReturn JSON only.",
            user_input="Generate a local app.",
            expected_schema_description="app file generation schema",
            fallback_factory=self.app_file_generation_payload(),
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": api_key}
            ),
            provider_callable=provider,
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(data["app_name"], "Idea Scoreboard")
        self.assertEqual(provider_result.fallback_reason, "app_safety_validation_failed")
        self.assertFalse(provider_result.used_ai)
        self.assertEqual(provider_result.warnings, ())

    def test_generate_json_with_ai_returns_ai_data_when_valid(self) -> None:
        api_key = "sk" + "-test"
        data, provider = generate_json_with_ai(
            task_name="valid_json",
            instructions="Return JSON.",
            user_input="ignored",
            expected_schema_description='{"title":"value","summary":"value"}',
            fallback_factory={"title": "offline", "summary": "offline"},
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "openai", "SPRINTOS_AI_ENABLED": "true", "OPENAI_API_KEY": api_key}
            ),
            provider_callable=lambda **_: fake_provider_result(
                text='{"title":"ai","summary":"better"}',
                parsed_json={"title": "ai", "summary": "better"},
                ok=True,
            ),
        )
        self.assertEqual(data["title"], "ai")
        self.assertTrue(provider.used_ai)

    def test_generate_json_with_ai_returns_fallback_on_deepseek_malformed_json(self) -> None:
        data, provider = generate_json_with_ai(
            task_name="bad_json",
            instructions="Return JSON.",
            user_input="ignored",
            expected_schema_description='{"title":"value"}',
            fallback_factory={"title": "offline"},
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "deepseek", "SPRINTOS_AI_ENABLED": "true", "DEEPSEEK_API_KEY": "sk-deepseek-test"}
            ),
            provider_callable=lambda **_: fake_provider_result(text="not-json", parsed_json=None, ok=True, provider="deepseek", model=DEFAULT_DEEPSEEK_MODEL),
        )
        self.assertEqual(data["title"], "offline")
        self.assertIn("valid JSON", provider.error)
        self.assertEqual(provider.fallback_reason, "deepseek_invalid_json")
        self.assertFalse(provider.used_ai)

    def test_generate_json_with_ai_returns_fallback_on_deepseek_missing_required_fields(self) -> None:
        data, provider = generate_json_with_ai(
            task_name="missing_fields",
            instructions="Return JSON.",
            user_input="ignored",
            expected_schema_description='{"title":"value","summary":"value"}',
            fallback_factory={"title": "offline", "summary": "offline"},
            config=load_ai_provider_config(
                {"SPRINTOS_AI_PROVIDER": "deepseek", "SPRINTOS_AI_ENABLED": "true", "DEEPSEEK_API_KEY": "sk-deepseek-test"}
            ),
            provider_callable=lambda **_: fake_provider_result(
                text='{"title":"ai"}',
                parsed_json={"title": "ai"},
                ok=True,
                provider="deepseek",
                model=DEFAULT_DEEPSEEK_MODEL,
            ),
        )
        self.assertEqual(data["summary"], "offline")
        self.assertEqual(provider.fallback_reason, "deepseek_schema_invalid")
        self.assertIn("missing required fields", provider.error.lower())


class AIQualitySupportMixin:
    def enable_ai(self, provider: str = "openai") -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = provider
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = ""
        os.environ["DEEPSEEK_API_KEY"] = ""
        if provider == "deepseek":
            os.environ["DEEPSEEK_API_KEY"] = "sk-test-quality-layer-deepseek"
            os.environ["SPRINTOS_MODEL"] = DEFAULT_DEEPSEEK_MODEL
        else:
            os.environ["OPENAI_API_KEY"] = "sk-test-quality-layer"

    def valid_payload_for_task(self, task_name: str):
        if task_name == "sprint_generation":
            return self.read_ai_fixture_json("software_mvp_valid_sprint.json")
        if task_name == "resume_plan":
            return {
                "recap": "This project already has a clear scope and needs one focused restart.",
                "next_tiny_action": "Open brief.md and finish the first unfinished section.",
                "restart_15_min": [
                    "Reopen the project and read the restart card.",
                    "Finish the first unfinished section in brief.md.",
                    "Save one visible change and note the next step."
                ],
                "restart_30_min": [
                    "Reopen the smallest artifact and regain context.",
                    "Complete the next tiny action in brief.md.",
                    "Package the updated artifact and log the next blocker."
                ],
                "one_thing_not_to_do": "Do not redesign the project or restart from zero.",
                "done_definition": "Done when the first unfinished section is complete and the next step is obvious."
            }
        if task_name == "prototype_content":
            return {
                "headline": "Turn rough planning into one clear local sprint",
                "subheadline": "A small local-first package that helps one user turn messy ideas into the next visible step.",
                "problem": "The idea is still trapped in scattered notes and needs one visible path forward.",
                "solution": "Give the user a compact local-first prototype with one action and one clear result.",
                "feature_bullets": [
                    "One focused input",
                    "One visible result",
                    "Local feedback capture"
                ],
                "cta_text": "Share feedback",
                "tester_questions": [
                    "What confused you first?",
                    "What felt useful right away?",
                    "What would make this worth trying again?"
                ]
            }
        if task_name == "app_file_generation":
            return {
                "app_name": "Idea Scoreboard",
                "app_type": "static_app",
                "short_description": "Score a rough business idea and show the smallest next test.",
                "user_flow": [
                    "Paste the business idea into the textarea.",
                    "Click Score Idea.",
                    "Review the score, risks, smallest test, and next action."
                ],
                "files": [
                    {
                        "filename": "index.html",
                        "content": """<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" /><title>Idea Scoreboard</title><link rel=\"stylesheet\" href=\"style.css\" /></head><body><main data-app-shape=\"business_idea_scorer\"><h1>Idea Scoreboard</h1><textarea id=\"idea-input\" data-template-marker=\"main-input\"></textarea><button id=\"score-idea\" data-template-marker=\"primary-action\">Score Idea</button><section id=\"result\" class=\"result\" data-template-marker=\"result-output\"><div id=\"idea-score\">0</div><ul id=\"idea-risks\" data-template-marker=\"risk_breakdown\"><li>No score yet.</li></ul><div id=\"idea-smallest-test\" data-template-marker=\"smallest-testable-version\">No score yet.</div><div id=\"idea-next-action\" data-template-marker=\"next-action\">No score yet.</div></section></main><script src=\"app.js\"></script></body></html>""",
                    },
                    {
                        "filename": "style.css",
                        "content": "body{font-family:sans-serif;margin:0;padding:24px;}textarea{width:100%;min-height:140px;}button{margin-top:12px;} .result{margin-top:16px;border:1px solid #ccc;padding:12px;}",
                    },
                    {
                        "filename": "app.js",
                        "content": "function scoreIdea(){const text=document.getElementById('idea-input').value.trim();const words=text.split(/\\s+/).filter(Boolean).length;const score=Math.max(1, Math.min(10, Math.ceil(words/6)));document.getElementById('idea-score').textContent=String(score);document.getElementById('idea-risks').innerHTML='<li>Demand risk: '+(score >= 7 ? 'Medium' : 'High')+'</li><li>Execution risk: medium</li>';document.getElementById('idea-smallest-test').textContent='Smallest testable version: interview 3 users this week.';document.getElementById('idea-next-action').textContent='Next action: '+(score >= 7 ? 'Interview 3 users this week.' : 'Rewrite the offer in one sentence.');}document.getElementById('score-idea').addEventListener('click', scoreIdea);",
                    },
                    {
                        "filename": "README.md",
                        "content": "# Idea Scoreboard\n\nRun `python3 -m http.server 8080` and open `index.html`.",
                    },
                    {
                        "filename": "TEST_PLAN.md",
                        "content": "# Test Plan\n\n- Open the app.\n- Paste an idea.\n- Click Score Idea.\n- Confirm the result updates locally.",
                    },
                ],
                "run_instructions": "Run `python3 -m http.server 8080` and open `index.html`.",
                "test_instructions": "Paste an idea, click the main button, and confirm the visible result changes locally.",
                "codex_next_prompt": "Preserve the working flow, improve one small part only, and run the included tests.",
                "limitations": ["This is a local prototype only."],
                "mocked_parts": ["The scoring logic is deterministic and intentionally simple."],
            }
        if task_name == "codex_handoff":
            return {
                "objective": "Implement the smallest shippable local-first version of the sprint.",
                "context": "The project already has a scoped sprint, saved artifacts, and a clear next step.",
                "constraints": [
                    "Read AGENTS.md first before editing.",
                    "Keep the work local-first.",
                    "Do not overbuild."
                ],
                "files_likely_touched": [
                    "brief.md",
                    "build-checklist.md",
                    "tests/test_sprintos.py"
                ],
                "acceptance_criteria": [
                    "The smallest useful version produces one visible output.",
                    "The implementation stays PR-sized."
                ],
                "verification_commands": [
                    "python3 -m unittest",
                    "python3 scripts/smoke.py"
                ],
                "review_checklist": [
                    "Existing behavior outside the touched path is preserved.",
                    "Tests cover the changed path."
                ],
                "non_goals": [
                    "No auth.",
                    "No cloud sync."
                ]
            }
        if task_name == "quick_launch_summary":
            return {
                "title": "Quick Launch Package",
                "summary": "A compact local test package is ready with a clear next Codex step.",
                "share_message": "Could you click through this local package and tell me what feels confusing first?",
                "suggested_first_codex_task": "Open the Build Pack and implement the first core flow only.",
                "next_tiny_action": "Open the Quick Launch report and send the share message to 3 testers."
            }
        raise AssertionError(f"Unhandled task payload: {task_name}")

    def provider_side_effect(self, *, malformed_task: str = "", missing_fields_task: str = "", sprint_payload=None):
        def _provider(**kwargs):
            config = kwargs.get("config")
            provider_name = str(getattr(config, "provider", os.environ.get("SPRINTOS_AI_PROVIDER", "openai")) or "openai")
            model_name = str(getattr(config, "model", os.environ.get("SPRINTOS_MODEL", "offline")) or "offline")
            instructions = kwargs.get("instructions", "")
            task_name = ""
            for candidate in ("sprint_generation", "resume_plan", "prototype_content", "app_file_generation", "codex_handoff", "quick_launch_summary"):
                if f"Task name: {candidate}" in instructions:
                    task_name = candidate
                    break
            if not task_name:
                raise AssertionError(f"Unknown task in instructions: {instructions}")
            if task_name == malformed_task:
                return fake_provider_result(text="not-json", parsed_json=None, ok=True, task_name=task_name, provider=provider_name, model=model_name)
            payload = sprint_payload if task_name == "sprint_generation" and sprint_payload is not None else self.valid_payload_for_task(task_name)
            if task_name == missing_fields_task:
                payload = dict(payload)
                payload.pop(next(iter(payload.keys())), None)
            text = json.dumps(payload)
            return fake_provider_result(text=text, parsed_json=payload, ok=True, task_name=task_name, provider=provider_name, model=model_name)
        return _provider

    def assert_metadata_fields(self, payload: dict, requested_mode: str) -> None:
        self.assertEqual(payload["generation_mode_requested"], requested_mode)
        self.assertIn("used_ai", payload)
        self.assertIn("ai_provider", payload)
        self.assertIn("ai_model", payload)
        self.assertIn("ai_task_name", payload)
        self.assertIn("ai_fallback_reason", payload)
        self.assertIn("route_used", payload)
        self.assertIn("resolved_provider", payload)
        self.assertIn("resolved_model", payload)


class AIQualityLayerTests(AIQualitySupportMixin, SprintOSTestCase):
    def test_ai_schema_validation_passes_valid_payload(self) -> None:
        result = validate_ai_payload("sprint_generation", self.read_ai_fixture_json("software_mvp_valid_sprint.json"))
        self.assertTrue(result["ok"])
        self.assertFalse(result["missing_fields"])
        self.assertFalse(result["wrong_type_fields"])

    def test_ai_schema_validation_fails_missing_fields(self) -> None:
        result = validate_ai_payload("resume_plan", {"recap": "ok"})
        self.assertFalse(result["ok"])
        self.assertIn("next_tiny_action", result["missing_fields"])

    def test_ai_schema_validation_fails_wrong_types(self) -> None:
        result = validate_ai_payload(
            "prototype_content",
            {
                "headline": "ok",
                "subheadline": "ok",
                "problem": "ok",
                "solution": "ok",
                "feature_bullets": "not-a-list",
                "cta_text": "ok",
                "tester_questions": ["One question"]
            },
        )
        self.assertFalse(result["ok"])
        self.assertIn("feature_bullets", result["wrong_type_fields"])

    def test_app_file_generation_schema_accepts_valid_payload(self) -> None:
        result = validate_ai_payload("app_file_generation", self.valid_payload_for_task("app_file_generation"))
        self.assertTrue(result["ok"])
        self.assertFalse(result["missing_fields"])
        self.assertFalse(result["wrong_type_fields"])

    def test_app_file_generation_schema_requires_concise_name_and_description(self) -> None:
        payload = self.valid_payload_for_task("app_file_generation")
        payload["app_name"] = "Very Long Generic Prototype Application Name"
        payload["short_description"] = "x" * 141
        result = validate_ai_payload("app_file_generation", payload)

        self.assertFalse(result["ok"])
        self.assertIn("app_name", result["wrong_type_fields"])
        self.assertIn("short_description", result["wrong_type_fields"])

    def test_app_file_generation_schema_rejects_missing_required_files(self) -> None:
        payload = self.valid_payload_for_task("app_file_generation")
        payload["files"] = [item for item in payload["files"] if item["filename"] != "app.js"]
        result = validate_ai_payload("app_file_generation", payload)
        self.assertFalse(result["ok"])
        self.assertIn("files:app.js", result["missing_fields"])

    def test_app_file_generation_schema_rejects_path_traversal_filename(self) -> None:
        payload = self.valid_payload_for_task("app_file_generation")
        payload["files"][0]["filename"] = "../index.html"
        result = validate_ai_payload("app_file_generation", payload)
        self.assertFalse(result["ok"])
        self.assertIn("files[0].filename", result["wrong_type_fields"])

    def test_app_file_generation_schema_rejects_hardcoded_key_patterns(self) -> None:
        payload = self.valid_payload_for_task("app_file_generation")
        payload["files"][2]["content"] += "\nconst leaked = 'sk-test-app-secret';\n"
        result = validate_ai_payload("app_file_generation", payload)
        self.assertFalse(result["ok"])
        self.assertIn("files:secret_pattern", result["wrong_type_fields"])

    def test_app_file_generation_schema_rejects_external_cdn_urls(self) -> None:
        payload = self.valid_payload_for_task("app_file_generation")
        payload["files"][0]["content"] = payload["files"][0]["content"].replace(
            "</head>",
            '<script src="https://cdn.example.com/app.js"></script></head>',
        )
        result = validate_ai_payload("app_file_generation", payload)
        self.assertFalse(result["ok"])
        self.assertIn("files:external_urls", result["wrong_type_fields"])

    def test_filename_sanitization_applies_inside_ai_artifacts(self) -> None:
        result = validate_ai_payload(
            "sprint_generation",
            {
                "title": "Title",
                "summary": "Summary",
                "workflow": "Workflow",
                "done_definition": "Done",
                "next_tiny_action": "Open safe.md and write the first section.",
                "plan_steps": ["Do one safe thing."],
                "artifacts": [{"title": "Artifact", "filename": "../Bad Name!!.MD", "content": "Hello"}],
            },
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["sanitized_payload"]["artifacts"][0]["filename"], "bad-name.md")

    def test_ai_prompt_instructions_request_json_only(self) -> None:
        prompt = build_json_only_instructions("codex_handoff", "Write a Codex task brief.")
        self.assertIn("Task name: codex_handoff", prompt)
        self.assertIn("Return JSON only.", prompt)
        self.assertIn("Do not use markdown fences.", prompt)
        self.assertIn('"verification_commands": list[string]', prompt)

    def test_generation_mode_offline_never_attempts_provider_call(self) -> None:
        with mock.patch("sprintos_core.ai_provider.call_openai_responses") as mocked_openai, mock.patch(
            "sprintos_core.ai_provider.call_deepseek_chat_completions"
        ) as mocked_deepseek:
            sprint = sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="offline")
        mocked_openai.assert_not_called()
        mocked_deepseek.assert_not_called()
        self.assertFalse(sprint["used_ai"])
        self.assertEqual(sprint["generation_mode_requested"], "offline")

    def test_generation_mode_auto_uses_ai_only_when_globally_usable(self) -> None:
        self.enable_ai()
        with mock.patch("sprintos_core.ai_provider.call_openai_responses", side_effect=self.provider_side_effect()):
            sprint = sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="auto")
        self.assertTrue(sprint["used_ai"])
        self.assertEqual(sprint["generation_mode_requested"], "auto")

        os.environ["OPENAI_API_KEY"] = ""
        with mock.patch("sprintos_core.ai_provider.call_openai_responses") as mocked:
            fallback = sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="auto")
        mocked.assert_not_called()
        self.assertFalse(fallback["used_ai"])

    def test_generation_mode_ai_attempts_provider_and_falls_back_safely(self) -> None:
        self.enable_ai()
        with mock.patch("sprintos_core.ai_provider.call_openai_responses", side_effect=self.provider_side_effect(malformed_task="sprint_generation")):
            sprint = sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="ai")
        self.assertFalse(sprint["used_ai"])
        self.assertEqual(sprint["generation_mode_requested"], "ai")
        self.assertTrue(sprint["ai_fallback_reason"])

    def test_generation_mode_auto_calls_deepseek_only_when_provider_is_usable(self) -> None:
        self.enable_ai("deepseek")
        with mock.patch("sprintos_core.ai_provider.call_deepseek_chat_completions", side_effect=self.provider_side_effect()):
            sprint = sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="auto")
        self.assertTrue(sprint["used_ai"])
        self.assertEqual(sprint["ai_provider"], "deepseek")
        self.assertEqual(sprint["generation_mode_requested"], "auto")

        os.environ["DEEPSEEK_API_KEY"] = ""
        with mock.patch("sprintos_core.ai_provider.call_deepseek_chat_completions") as mocked:
            fallback = sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="auto")
        mocked.assert_not_called()
        self.assertFalse(fallback["used_ai"])

    def test_generation_mode_ai_attempts_deepseek_and_falls_back_safely(self) -> None:
        self.enable_ai("deepseek")
        with mock.patch("sprintos_core.ai_provider.call_deepseek_chat_completions", side_effect=self.provider_side_effect(malformed_task="sprint_generation")):
            sprint = sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="ai")
        self.assertFalse(sprint["used_ai"])
        self.assertEqual(sprint["generation_mode_requested"], "ai")
        self.assertEqual(sprint["ai_provider"], "deepseek")
        self.assertTrue(sprint["ai_fallback_reason"])

    def test_sprint_resume_prototype_and_quick_launch_metadata_include_ai_fields(self) -> None:
        project = self.create_project()
        self.assert_metadata_fields(project["sprint"], "auto")

        resumed = sprintos.generate_and_store_resume_plan(project["id"], generation_mode="offline")
        self.assert_metadata_fields(resumed["sprint"]["resume_plan"], "offline")

        prototype = self.generate_prototype(project, generation_mode="offline")
        self.assert_metadata_fields(prototype["metadata"], "offline")

        quick_launch = self.generate_quick_launch(generation_mode="offline")
        self.assert_metadata_fields(quick_launch["metadata"], "offline")

    def test_pipeline_metadata_includes_ai_fields_when_generation_runs(self) -> None:
        project = self.create_project()
        pipeline_run = self.generate_pipeline(project, generation_mode="offline")
        self.assertEqual(pipeline_run["generation_mode_requested"], "offline")
        self.assertIn("used_ai", pipeline_run["metadata"])
        self.assertIn("ai_provider", pipeline_run["metadata"])
        self.assertIn("ai_task_name", pipeline_run["metadata"])

    def test_ai_diagnostics_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertIn("ai_diagnostics", tables)

    def test_diagnostics_are_recorded_for_offline_fallback_and_fake_ai_success(self) -> None:
        sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="offline")
        self.enable_ai()
        with mock.patch("sprintos_core.ai_provider.call_openai_responses", side_effect=self.provider_side_effect()):
            sprintos.generate_sprint("Build another local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="auto")
        diagnostics = sprintos.list_ai_diagnostics(limit=20)
        self.assertTrue(any(item["task_name"] == "sprint_generation" and not item["used_ai"] for item in diagnostics))
        self.assertTrue(any(item["task_name"] == "sprint_generation" and item["used_ai"] for item in diagnostics))

    def test_ai_diagnostics_endpoint_returns_redacted_payload(self) -> None:
        secret = "sk-test-hidden-secret"
        sprintos.record_ai_diagnostic(
            "sprint_generation",
            fake_provider_result(error=secret, provider="openai", used_ai=False, fallback_reason=secret),
            metadata={"project_id": "p1", "note": secret, "authorization": f"Bearer {secret}"},
        )
        server = self.start_server()
        payload = json.loads(self.http_get(server, "/api/ai_diagnostics?limit=20").decode("utf-8"))
        encoded = json.dumps(payload)
        self.assertNotIn(secret, encoded)
        self.assertNotIn("authorization", encoded.lower())

    def test_ai_status_includes_app_generation_readiness_without_secrets(self) -> None:
        secret = "sk-test-hidden-app-generation-secret"
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = secret
        os.environ["SPRINTOS_AI_TIMEOUT_SECONDS"] = "90"
        os.environ["SPRINTOS_AI_MAX_OUTPUT_TOKENS"] = "6000"
        sprintos.record_ai_diagnostic(
            "app_file_generation",
            fake_provider_result(
                ok=False,
                error=secret,
                provider="openai",
                model="gpt-4.1-mini",
                used_ai=False,
                fallback_reason="openai_timeout",
            ),
            metadata={"project_id": "p1", "raw_response": secret},
        )

        payload = sprintos.ai_status_payload()
        for key in (
            "app_generation_ready",
            "app_generation_warning",
            "app_generation_provider",
            "app_generation_model",
            "app_generation_timeout_seconds",
            "app_generation_max_output_tokens",
            "last_app_generation_result",
            "last_app_generation_fallback_reason",
        ):
            self.assertIn(key, payload)
        self.assertEqual(payload["last_app_generation_result"], "timeout")
        self.assertNotIn(secret, json.dumps(payload))

    def test_app_generation_fallback_mode_defaults_to_template(self) -> None:
        self.assertEqual(sprintos.normalize_app_generation_fallback_mode(), "template")
        payload = sprintos.ai_status_payload()
        self.assertEqual(payload["app_generation_fallback_mode"], "template")
        self.assertTrue(payload["offline_fallback_enabled"])
        self.assertFalse(payload["ai_only_mode_enabled"])

    def test_app_generation_report_only_env_and_boolean_alias(self) -> None:
        os.environ["SPRINTOS_APP_GENERATION_FALLBACK_MODE"] = "report_only"
        self.assertEqual(sprintos.normalize_app_generation_fallback_mode(), "report_only")
        os.environ.pop("SPRINTOS_APP_GENERATION_FALLBACK_MODE", None)
        os.environ["SPRINTOS_DISABLE_OFFLINE_APP_FALLBACK"] = "true"
        self.assertEqual(sprintos.normalize_app_generation_fallback_mode(), "report_only")
        payload = sprintos.ai_status_payload()
        self.assertEqual(payload["app_generation_fallback_mode"], "report_only")
        self.assertFalse(payload["offline_fallback_enabled"])
        self.assertTrue(payload["ai_only_mode_enabled"])

    def test_app_generation_failure_categories(self) -> None:
        cases = [
            ("openai_invalid_json", "AI output was not valid JSON.", "invalid_ai_json"),
            ("openai_timeout", "OpenAI request failed: timed out", "provider_timeout"),
            ("openai_http_error", "OpenAI HTTP error 402: insufficient balance", "provider_insufficient_balance"),
            ("deepseek_http_error", "DeepSeek HTTP error 503: service unavailable", "provider_unavailable"),
            ("openai_app_validation_failed", "AI output failed safety validation.", "app_safety_validation_failed"),
        ]
        for fallback_reason, error, expected in cases:
            with self.subTest(fallback_reason=fallback_reason):
                result = fake_provider_result(
                    ok=False,
                    error=error,
                    provider="openai",
                    model=DEFAULT_OPENAI_MODEL,
                    used_ai=False,
                    fallback_reason=fallback_reason,
                )
                self.assertEqual(sprintos.app_generation_failure_category(result), expected)

    def test_app_fallback_reason_translation_uses_approved_creator_copy(self) -> None:
        cases = {
            "openai_timeout": "timed out",
            "deepseek_http_error 503": "provider busy",
            "openai_invalid_json": "invalid AI output",
            "openai_schema_invalid": "invalid AI output",
            "openai_app_validation_failed": "safety validation failed",
            "missing_deepseek_key": "offline template selected",
        }
        for raw_reason, expected in cases.items():
            with self.subTest(raw_reason=raw_reason):
                self.assertEqual(sprintos.user_facing_app_fallback_reason(raw_reason), expected)
                self.assertIn(expected, sprintos.APP_FALLBACK_USER_REASONS)

    def test_ai_status_preflight_says_ai_ready_when_budget_and_provider_are_ready(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-test-present"
        os.environ["SPRINTOS_AI_TIMEOUT_SECONDS"] = "90"
        os.environ["SPRINTOS_AI_MAX_OUTPUT_TOKENS"] = "6000"

        payload = sprintos.ai_status_payload()

        self.assertTrue(payload["app_generation_ai_ready"])
        self.assertFalse(payload["app_generation_likely_local_template"])
        self.assertEqual(payload["app_generation_preflight_summary"], "AI app generation is ready.")
        self.assertEqual(payload["app_generation_preflight_details"], [])

    def test_ai_status_preflight_says_local_template_when_offline(self) -> None:
        payload = sprintos.ai_status_payload()

        self.assertFalse(payload["app_generation_ai_ready"])
        self.assertTrue(payload["app_generation_likely_local_template"])
        self.assertIn("local template", payload["app_generation_preflight_summary"])

    def test_ai_status_uses_safer_app_generation_defaults_when_env_budget_absent(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-test-present"
        os.environ.pop("SPRINTOS_AI_TIMEOUT_SECONDS", None)
        os.environ.pop("SPRINTOS_AI_MAX_OUTPUT_TOKENS", None)

        payload = sprintos.ai_status_payload()

        self.assertEqual(payload["timeout_seconds"], 20)
        self.assertEqual(payload["max_output_tokens"], 2000)
        self.assertEqual(payload["app_generation_timeout_seconds"], 90)
        self.assertEqual(payload["app_generation_max_output_tokens"], 6000)
        self.assertTrue(payload["app_generation_ai_ready"])

    def test_app_file_generation_call_uses_safer_defaults_when_env_budget_absent(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-test-present"
        os.environ.pop("SPRINTOS_AI_TIMEOUT_SECONDS", None)
        os.environ.pop("SPRINTOS_AI_MAX_OUTPUT_TOKENS", None)
        project = self.create_project(raw_idea="Build a business idea scoring app that evaluates startup ideas.")
        ctx = sprintos.prototype_context_offline(project, "landing_page", prototype_id="budget-default-test")
        payload = sprintos.prototype_offline_app_file_generation_payload(project, "landing_page", "budget-default-test", ctx=ctx)
        seen: dict[str, int] = {}

        def fake_call(**kwargs):
            config = kwargs["config"]
            seen["timeout_seconds"] = config.timeout_seconds
            seen["max_output_tokens"] = config.max_output_tokens
            return fake_provider_result(
                text=json.dumps(payload),
                parsed_json=payload,
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                task_name="app_file_generation",
            )

        with mock.patch("sprintos_core.ai_provider.call_openai_responses", side_effect=fake_call):
            prototype = self.generate_prototype(project, "landing_page", generation_mode="auto")

        metadata = json.loads((Path(prototype["path"]) / "prototype.json").read_text(encoding="utf-8"))
        self.assertTrue(metadata["used_ai"])
        self.assertEqual(seen["timeout_seconds"], 90)
        self.assertEqual(seen["max_output_tokens"], 6000)

    def test_ai_status_preflight_summarizes_low_budget_plainly(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-test-present"
        os.environ["SPRINTOS_AI_TIMEOUT_SECONDS"] = "30"
        os.environ["SPRINTOS_AI_MAX_OUTPUT_TOKENS"] = "3000"

        payload = sprintos.ai_status_payload()
        joined_details = " ".join(payload["app_generation_preflight_details"])

        self.assertFalse(payload["app_generation_ai_ready"])
        self.assertTrue(payload["app_generation_likely_local_template"])
        self.assertIn("Current app-generation budget is 30 seconds / 3000 tokens.", joined_details)
        self.assertIn("Recommended: 90 seconds / 6000 tokens.", joined_details)

    def test_ai_status_preflight_summarizes_recent_provider_failure_without_raw_payload(self) -> None:
        raw_provider_payload = '{"error":{"message":"Service is too busy","code":"service_unavailable_error"}}'
        sprintos.record_ai_diagnostic(
            "app_file_generation",
            fake_provider_result(
                ok=False,
                error=f"DeepSeek HTTP error 503: {raw_provider_payload}",
                provider="deepseek",
                used_ai=False,
                fallback_reason="deepseek_http_error",
            ),
        )

        payload = sprintos.ai_status_payload()
        encoded = json.dumps(
            {
                "summary": payload["app_generation_preflight_summary"],
                "details": payload["app_generation_preflight_details"],
            }
        )

        self.assertTrue(payload["app_generation_likely_local_template"])
        self.assertIn("provider availability issue", encoded)
        self.assertIn("503", encoded)
        self.assertNotIn("Service is too busy", encoded)
        self.assertNotIn("service_unavailable_error", encoded)

    def test_ai_diagnostics_endpoint_redacts_deepseek_key_patterns(self) -> None:
        secret = "sk-test-deepseek-hidden-secret"
        sprintos.record_ai_diagnostic(
            "sprint_generation",
            fake_provider_result(error=secret, provider="deepseek", used_ai=False, fallback_reason="missing_deepseek_key"),
            metadata={"project_id": "p1", "deepseek_api_key": secret, "note": "Authorization: " + "Bearer " + secret},
        )
        server = self.start_server()
        payload = json.loads(self.http_get(server, "/api/ai_diagnostics?limit=20").decode("utf-8"))
        encoded = json.dumps(payload)
        self.assertNotIn(secret, encoded)
        self.assertNotIn("deepseek_api_key", encoded.lower())

    def test_diagnostics_and_exports_never_include_fake_api_key(self) -> None:
        secret = "sk-test-do-not-leak"
        sprintos.record_ai_diagnostic(
            "prototype_content",
            fake_provider_result(error=secret, provider="openai", used_ai=False, fallback_reason=secret),
            metadata={"project_id": "p1", "note": secret},
        )
        project = self.create_project()
        _, markdown = sprintos.write_markdown_export(project)
        _, payload = sprintos.build_zip_export(project)
        diagnostics = sprintos.list_ai_diagnostics(limit=20)
        self.assertNotIn(secret, json.dumps(diagnostics))
        self.assertNotIn(secret, markdown)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for name in zf.namelist():
                self.assertNotIn(secret, zf.read(name).decode("utf-8", errors="ignore"), name)

    def test_ai_quality_eval_fixtures_pass_offline(self) -> None:
        for name in sorted(self.ai_fixture_dir().glob("*_idea.txt")):
            sprint = sprintos.generate_sprint(name.read_text(encoding="utf-8"), "auto", 120, "medium", "a local prototype", generation_mode="offline")
            self.assertTrue(sprint["title"])
            self.assertTrue(sprint["done_definition"])
            self.assertFalse(sprintos.is_vague_next_action((sprint.get("restart_card") or {}).get("next_tiny_action", "")))
            self.assertIn("## Acceptance Criteria", sprint["codex_handoff"]["content"])
            self.assertIn("## Verification Commands", sprint["codex_handoff"]["content"])
            self.assertFalse(sprint["used_ai"])

    def test_ai_quality_eval_fixtures_pass_fake_valid_ai(self) -> None:
        self.enable_ai()
        for idea_name, payload_name in (
            ("software_mvp_idea.txt", "software_mvp_valid_sprint.json"),
            ("ai_text_tool_idea.txt", "ai_text_tool_valid_sprint.json"),
            ("calculator_idea.txt", "calculator_valid_sprint.json"),
            ("quiz_recommender_idea.txt", "quiz_recommender_valid_sprint.json"),
            ("landing_page_idea.txt", "landing_page_valid_sprint.json"),
        ):
            with mock.patch(
                "sprintos_core.ai_provider.call_openai_responses",
                side_effect=self.provider_side_effect(sprint_payload=self.read_ai_fixture_json(payload_name)),
            ):
                sprint = sprintos.generate_sprint(
                    self.read_ai_fixture_text(idea_name),
                    "auto",
                    120,
                    "medium",
                    "a local prototype",
                    generation_mode="auto",
                )
            self.assertTrue(sprint["used_ai"])
            self.assertFalse(sprintos.is_vague_next_action((sprint.get("restart_card") or {}).get("next_tiny_action", "")))

    def test_ai_quality_eval_fixtures_fallback_on_malformed_ai(self) -> None:
        self.enable_ai()
        for name in sorted(self.ai_fixture_dir().glob("*_idea.txt")):
            with mock.patch("sprintos_core.ai_provider.call_openai_responses", side_effect=self.provider_side_effect(malformed_task="sprint_generation")):
                sprint = sprintos.generate_sprint(name.read_text(encoding="utf-8"), "auto", 120, "medium", "a local prototype", generation_mode="ai")
            self.assertFalse(sprint["used_ai"])
            self.assertTrue(sprint["ai_fallback_reason"])

    def test_ai_quality_eval_fixtures_fallback_on_missing_fields(self) -> None:
        self.enable_ai()
        for name in sorted(self.ai_fixture_dir().glob("*_idea.txt")):
            with mock.patch("sprintos_core.ai_provider.call_openai_responses", side_effect=self.provider_side_effect(missing_fields_task="sprint_generation")):
                sprint = sprintos.generate_sprint(name.read_text(encoding="utf-8"), "auto", 120, "medium", "a local prototype", generation_mode="ai")
            self.assertFalse(sprint["used_ai"])
            self.assertTrue(sprint["ai_fallback_reason"])


class AIProviderSecurityAndOfflineTests(AIQualitySupportMixin, SprintOSTestCase):
    def test_ai_status_endpoint_never_returns_api_key(self) -> None:
        secret = "sk" + "-test-secret-value"
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = secret
        server = self.start_server()
        payload = json.loads(self.http_get(server, "/api/ai_status").decode("utf-8"))
        self.assertNotIn("OPENAI_API_KEY", payload)
        self.assertNotIn("api_key", payload)
        self.assertTrue(payload["api_key_present"])

    def test_ai_status_endpoint_never_returns_deepseek_api_key(self) -> None:
        secret = "sk" + "-test-deepseek-secret-value"
        os.environ["SPRINTOS_AI_PROVIDER"] = "deepseek"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["DEEPSEEK_API_KEY"] = secret
        server = self.start_server()
        payload = json.loads(self.http_get(server, "/api/ai_status").decode("utf-8"))
        self.assertNotIn("DEEPSEEK_API_KEY", payload)
        self.assertNotIn("deepseek_api_key", json.dumps(payload))
        self.assertTrue(payload["api_key_present"])

    def test_test_ai_provider_endpoint_never_returns_api_key(self) -> None:
        secret = "sk" + "-test-secret-value"
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = secret
        server = self.start_server()
        with mock.patch(
            "sprintos.call_openai_responses",
            return_value=fake_provider_result(
                text='{"status":"ok","message":"SprintOS AI provider ready"}',
                parsed_json={"status": "ok", "message": "SprintOS AI provider ready"},
                ok=True,
                provider="openai",
            ),
        ):
            payload = self.http_post_json(server, "/api/test_ai_provider", {})
        encoded = json.dumps(payload)
        self.assertNotIn(secret, encoded)
        self.assertTrue(payload["usable"])

    def test_test_ai_provider_endpoint_never_returns_deepseek_api_key(self) -> None:
        secret = "sk" + "-deepseek-secret-value"
        os.environ["SPRINTOS_AI_PROVIDER"] = "deepseek"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["DEEPSEEK_API_KEY"] = secret
        server = self.start_server()
        with mock.patch(
            "sprintos.call_deepseek_chat_completions",
            return_value=fake_provider_result(
                text='{"status":"ok","message":"SprintOS DeepSeek provider ready"}',
                parsed_json={"status": "ok", "message": "SprintOS DeepSeek provider ready"},
                ok=True,
                provider="deepseek",
                model=DEFAULT_DEEPSEEK_MODEL,
            ),
        ):
            payload = self.http_post_json(server, "/api/test_ai_provider", {})
        encoded = json.dumps(payload)
        self.assertNotIn("DEEPSEEK_API_KEY", encoded)
        self.assertNotIn(secret, encoded)
        self.assertTrue(payload["usable"])

    def test_exports_do_not_contain_fake_key_values(self) -> None:
        secret = "sk-fake-openai-export-secret"
        os.environ["OPENAI_API_KEY"] = secret
        project = self.create_project()
        _, markdown = sprintos.write_markdown_export(project)
        _, payload = sprintos.build_zip_export(project)
        self.assertNotIn(secret, markdown)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for name in zf.namelist():
                self.assertNotIn(secret, zf.read(name).decode("utf-8", errors="ignore"), name)

    def test_exports_do_not_contain_fake_deepseek_key_values(self) -> None:
        secret = "sk-fake-deepseek-export-secret"
        os.environ["DEEPSEEK_API_KEY"] = secret
        project = self.create_project()
        _, markdown = sprintos.write_markdown_export(project)
        _, payload = sprintos.build_zip_export(project)
        self.assertNotIn(secret, markdown)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for name in zf.namelist():
                self.assertNotIn(secret, zf.read(name).decode("utf-8", errors="ignore"), name)

    def test_health_secret_scan_catches_obvious_hardcoded_key_patterns(self) -> None:
        root = self.root / "repo"
        (root / "sprintos_core").mkdir(parents=True, exist_ok=True)
        secret = "sk-test-openai-hardcoded"
        (root / "sprintos_core" / "ai_provider.py").write_text(f'OPENAI_API_KEY="{secret}"\n', encoding="utf-8")
        with mock.patch.object(health, "ROOT", root):
            findings = health.scan_for_secrets()
        self.assertTrue(any("literal OPENAI_API_KEY value" in item for item in findings))

    def test_health_secret_scan_ignores_blank_env_example(self) -> None:
        root = self.root / "repo"
        root.mkdir(parents=True, exist_ok=True)
        (root / ".env.example").write_text("OPENAI_API_KEY=\nDEEPSEEK_API_KEY=\n", encoding="utf-8")
        with mock.patch.object(health, "ROOT", root):
            findings = health.scan_for_secrets()
        self.assertEqual(findings, [])

    def test_health_secret_scan_catches_obvious_hardcoded_deepseek_key_pattern(self) -> None:
        root = self.root / "repo"
        (root / "sprintos_core").mkdir(parents=True, exist_ok=True)
        secret = "sk-test-deepseek-hardcoded"
        (root / "sprintos_core" / "ai_provider.py").write_text(f'DEEPSEEK_API_KEY="{secret}"\n', encoding="utf-8")
        with mock.patch.object(health, "ROOT", root):
            findings = health.scan_for_secrets()
        self.assertTrue(any("literal DEEPSEEK_API_KEY value" in item for item in findings))

    def test_sprint_generation_still_works_offline(self) -> None:
        project = self.create_project()
        self.assertEqual(project["sprint"]["_mode"], "offline")
        self.assertFalse(project["sprint"]["used_ai"])

    def test_resume_generation_still_works_offline(self) -> None:
        project = self.create_project()
        project = sprintos.generate_and_store_resume_plan(project["id"])
        self.assertEqual(project["sprint"]["resume_plan"]["_mode"], "offline")
        self.assertFalse(project["sprint"]["resume_plan"]["used_ai"])

    def test_prototype_generation_still_works_offline(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        self.assertEqual(prototype["metadata"]["_mode"], "offline")
        self.assertFalse(prototype["metadata"]["used_ai"])

    def test_quick_launch_still_works_offline(self) -> None:
        quick_launch = self.generate_quick_launch()
        self.assertEqual(quick_launch["metadata"]["_mode"], "offline")
        self.assertFalse(quick_launch["metadata"]["used_ai"])

    def test_run_and_verify_still_works_offline(self) -> None:
        chain = self.generate_full_chain()
        self.assertEqual(chain["verification"]["status"], "passed")

    def test_json_helpers_handle_malformed_json_gracefully(self) -> None:
        broken_path = self.root / "broken.json"
        broken_path.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(safe_json_loads("{oops", {"ok": False}), {"ok": False})
        self.assertEqual(read_json_file(broken_path, {"broken": True}), {"broken": True})

    def test_zip_helper_includes_expected_files(self) -> None:
        payload = build_zip_from_pairs([("a.txt", "alpha"), ("folder/b.txt", "beta")])
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertEqual(set(zf.namelist()), {"a.txt", "folder/b.txt"})
            self.assertEqual(zf.read("folder/b.txt").decode("utf-8"), "beta")

    def test_external_network_marker_detection_ignores_localhost_and_flags_remote_urls(self) -> None:
        markers = external_network_markers("app.js", 'fetch("https://example.com/api");\nconst ok = "http://127.0.0.1:8000";\n')
        self.assertTrue(any("fetch()" in item for item in markers))
        self.assertTrue(any("external URL https://example.com/api" in item for item in markers))
        self.assertFalse(any("127.0.0.1" in item for item in markers))

    def test_vague_next_action_detection_matches_generic_phrases(self) -> None:
        self.assertTrue(sprintos.is_vague_next_action("continue building"))
        self.assertTrue(sprintos.is_vague_next_action(""))
        self.assertFalse(sprintos.is_vague_next_action("Open the Build Pack folder and run the smoke test."))

    def test_report_path_helpers_create_unique_dirs_and_block_traversal(self) -> None:
        report_root = self.root / "reports"
        report_root.mkdir(parents=True, exist_ok=True)
        first = create_report_dir(report_root, "Demo Project", "pipeline", "20260506-120000")
        second = create_report_dir(report_root, "Demo Project", "pipeline", "20260506-120000")
        (first / "report.md").write_text("ok", encoding="utf-8")
        nested = first / "nested"
        nested.mkdir()
        (nested / "child.txt").write_text("nested ok", encoding="utf-8")
        self.assertNotEqual(first, second)
        self.assertTrue(first.name.startswith("demo-project-pipeline-20260506-120000"))
        self.assertEqual(safe_flat_file_path(first, "report.md", ("report.md",), "Invalid report file").read_text(encoding="utf-8"), "ok")
        self.assertEqual(
            safe_relative_file_path(first, "nested/child.txt", ("nested/child.txt",), "Invalid report file").read_text(encoding="utf-8"),
            "nested ok",
        )
        with self.assertRaises(ValueError):
            safe_flat_file_path(first, "../report.md", ("report.md",), "Invalid report file")
        with self.assertRaises(ValueError):
            safe_relative_file_path(first, "../report.md", ("nested/child.txt",), "Invalid report file")

    def test_metadata_path_safety_allows_local_routes_but_blocks_system_paths(self) -> None:
        self.assertFalse(sprintos.metadata_has_unsafe_path({"api_endpoint": "/api/generate"}))
        self.assertTrue(sprintos.metadata_has_unsafe_path({"path": "/Users/example/secret"}))


class AIRoutingTests(AIQualitySupportMixin, SprintOSTestCase):
    def test_ai_provider_routes_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertIn("ai_provider_routes", tables)

    def test_ai_routes_endpoint_returns_supported_task_names(self) -> None:
        server = self.start_server()
        payload = json.loads(self.http_get(server, "/api/ai_routes").decode("utf-8"))
        self.assertEqual({item["task_name"] for item in payload["routes"]}, set(sprintos.SUPPORTED_AI_TASK_NAMES))
        self.assertIn("defaults", payload)

    def test_post_ai_route_saves_valid_route(self) -> None:
        server = self.start_server()
        payload = self.http_post_json(
            server,
            "/api/ai_route",
            {
                "task_name": "sprint_generation",
                "generation_mode": "ai",
                "provider": "deepseek",
                "model": "deepseek-v4-flash",
                "enabled": True,
            },
        )
        route = payload["route"]
        self.assertEqual(route["task_name"], "sprint_generation")
        self.assertEqual(route["generation_mode"], "ai")
        self.assertEqual(route["provider"], "deepseek")
        self.assertEqual(route["model"], "deepseek-v4-flash")
        self.assertTrue(route["enabled"])

    def test_post_ai_route_rejects_invalid_task_name(self) -> None:
        server = self.start_server()
        with self.assertRaises(urllib.error.HTTPError):
            self.http_post_json(server, "/api/ai_route", {"task_name": "bad_task", "generation_mode": "ai", "provider": "openai", "enabled": True})

    def test_post_ai_route_rejects_invalid_provider(self) -> None:
        server = self.start_server()
        with self.assertRaises(urllib.error.HTTPError):
            self.http_post_json(server, "/api/ai_route", {"task_name": "sprint_generation", "generation_mode": "ai", "provider": "weird", "enabled": True})

    def test_post_ai_route_rejects_invalid_generation_mode(self) -> None:
        server = self.start_server()
        with self.assertRaises(urllib.error.HTTPError):
            self.http_post_json(server, "/api/ai_route", {"task_name": "sprint_generation", "generation_mode": "sometimes", "provider": "openai", "enabled": True})

    def test_reset_ai_route_removes_saved_route(self) -> None:
        sprintos.save_ai_route("sprint_generation", "ai", "openai", enabled=True)
        self.assertIsNotNone(sprintos.get_ai_route("sprint_generation"))
        server = self.start_server()
        payload = self.http_post_json(server, "/api/reset_ai_route", {"task_name": "sprint_generation"})
        self.assertIsNone(sprintos.get_ai_route("sprint_generation"))
        self.assertEqual(payload["route"]["effective_provider"], "offline")

    def test_cheap_deepseek_preset_creates_deepseek_routes(self) -> None:
        server = self.start_server()
        payload = self.http_post_json(server, "/api/apply_ai_route_preset", {"preset": "cheap_deepseek"})
        self.assertEqual(payload["preset"], "cheap_deepseek")
        self.assertTrue(all(item["provider"] == "deepseek" for item in payload["routes"]))
        self.assertTrue(all(item["enabled"] for item in payload["routes"]))

    def test_conservative_openai_preset_creates_openai_routes(self) -> None:
        server = self.start_server()
        payload = self.http_post_json(server, "/api/apply_ai_route_preset", {"preset": "conservative_openai"})
        self.assertEqual(payload["preset"], "conservative_openai")
        self.assertTrue(all(item["provider"] == "openai" for item in payload["routes"]))
        self.assertTrue(all(item["generation_mode"] == "auto" for item in payload["routes"]))

    def test_offline_only_preset_creates_offline_routes(self) -> None:
        server = self.start_server()
        payload = self.http_post_json(server, "/api/apply_ai_route_preset", {"preset": "offline_only"})
        self.assertEqual(payload["preset"], "offline_only")
        self.assertTrue(all(item["provider"] == "offline" for item in payload["routes"]))
        self.assertTrue(all(item["generation_mode"] == "offline" for item in payload["routes"]))

    def test_route_resolver_uses_task_route_when_enabled(self) -> None:
        self.enable_ai("openai")
        os.environ["DEEPSEEK_API_KEY"] = "sk-route-deepseek"
        sprintos.save_ai_route("sprint_generation", "ai", "deepseek", model="deepseek-v4-flash", enabled=True)
        resolution = sprintos.resolve_ai_route("sprint_generation", requested_generation_mode="auto")
        self.assertTrue(resolution["route_used"])
        self.assertEqual(resolution["resolved_provider"], "deepseek")
        self.assertEqual(resolution["resolved_model"], "deepseek-v4-flash")
        self.assertEqual(resolution["effective_generation_mode"], "ai")

    def test_route_resolver_falls_back_to_global_provider_when_route_disabled(self) -> None:
        self.enable_ai("openai")
        sprintos.save_ai_route("sprint_generation", "ai", "deepseek", model="deepseek-v4-flash", enabled=False)
        resolution = sprintos.resolve_ai_route("sprint_generation", requested_generation_mode="auto")
        self.assertFalse(resolution["route_used"])
        self.assertEqual(resolution["resolved_provider"], "openai")

    def test_generation_mode_offline_overrides_route(self) -> None:
        self.enable_ai("openai")
        sprintos.save_ai_route("sprint_generation", "ai", "openai", model="gpt-4.1-mini", enabled=True)
        resolution = sprintos.resolve_ai_route("sprint_generation", requested_generation_mode="offline")
        self.assertFalse(resolution["route_used"])
        self.assertEqual(resolution["resolved_provider"], "offline")
        self.assertEqual(resolution["effective_generation_mode"], "offline")

    def test_route_with_missing_key_falls_back_offline_and_records_reason(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "offline"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = ""
        os.environ["DEEPSEEK_API_KEY"] = ""
        sprintos.save_ai_route("sprint_generation", "ai", "deepseek", model="deepseek-v4-flash", enabled=True)
        with mock.patch("sprintos_core.ai_provider.call_deepseek_chat_completions") as mocked:
            sprint = sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="auto")
        mocked.assert_not_called()
        self.assertFalse(sprint["used_ai"])
        self.assertTrue(sprint["route_used"])
        self.assertEqual(sprint["resolved_provider"], "deepseek")
        self.assertEqual(sprint["ai_fallback_reason"], "missing_deepseek_key")

    def test_route_model_override_is_used_in_diagnostics_metadata(self) -> None:
        self.enable_ai("openai")
        sprintos.save_ai_route("sprint_generation", "ai", "openai", model="gpt-route-mini", enabled=True)
        with mock.patch("sprintos_core.ai_provider.call_openai_responses", side_effect=self.provider_side_effect()):
            sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="auto")
        diagnostics = sprintos.list_ai_diagnostics(limit=20)
        item = next(diag for diag in diagnostics if diag["task_name"] == "sprint_generation")
        self.assertTrue(item["route_used"])
        self.assertEqual(item["resolved_model"], "gpt-route-mini")

    def test_sprint_generation_metadata_includes_resolved_route_fields(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "offline"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["DEEPSEEK_API_KEY"] = "sk-route-deepseek"
        sprintos.save_ai_route("sprint_generation", "ai", "deepseek", model="deepseek-v4-flash", enabled=True)
        with mock.patch("sprintos_core.ai_provider.call_deepseek_chat_completions", side_effect=self.provider_side_effect()):
            sprint = sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="auto")
        self.assertTrue(sprint["route_used"])
        self.assertEqual(sprint["resolved_provider"], "deepseek")

    def test_app_file_generation_metadata_includes_resolved_route_fields(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "offline"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["DEEPSEEK_API_KEY"] = "sk-route-deepseek"
        sprintos.save_ai_route("app_file_generation", "ai", "deepseek", model="deepseek-v4-flash", enabled=True)
        project = self.create_project()
        with mock.patch("sprintos_core.ai_provider.call_deepseek_chat_completions", side_effect=self.provider_side_effect()):
            prototype = self.generate_prototype(project, generation_mode="auto")
        self.assertTrue(prototype["metadata"]["route_used"])
        self.assertEqual(prototype["metadata"]["resolved_provider"], "deepseek")

    def test_quick_launch_summary_metadata_includes_resolved_route_fields(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "offline"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["DEEPSEEK_API_KEY"] = "sk-route-deepseek"
        sprintos.save_ai_route("quick_launch_summary", "ai", "deepseek", model="deepseek-v4-flash", enabled=True)
        with mock.patch("sprintos_core.ai_provider.call_deepseek_chat_completions", side_effect=self.provider_side_effect()):
            quick_launch = self.generate_quick_launch(generation_mode="auto")
        self.assertTrue(quick_launch["metadata"]["route_used"])
        self.assertEqual(quick_launch["metadata"]["resolved_provider"], "deepseek")

    def test_exports_include_ai_routing_summary_without_secrets(self) -> None:
        secret = "sk" + "-route-export-secret"
        os.environ["OPENAI_API_KEY"] = secret
        sprintos.save_ai_route("sprint_generation", "ai", "openai", model="gpt-route-mini", enabled=True)
        project = self.create_project()
        _, markdown = sprintos.write_markdown_export(project)
        zip_name, payload = sprintos.build_zip_export(project)
        self.assertIn("## AI Routing", markdown)
        self.assertTrue(zip_name.endswith(".zip"))
        self.assertNotIn(secret, markdown)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertIn("ai-routing.md", set(zf.namelist()))
            self.assertNotIn(secret, zf.read("ai-routing.md").decode("utf-8"))

    def test_ai_diagnostics_endpoint_includes_routing_fields(self) -> None:
        self.enable_ai("openai")
        sprintos.save_ai_route("sprint_generation", "ai", "openai", model="gpt-route-mini", enabled=True)
        with mock.patch("sprintos_core.ai_provider.call_openai_responses", side_effect=self.provider_side_effect()):
            sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="auto")
        server = self.start_server()
        payload = json.loads(self.http_get(server, "/api/ai_diagnostics?limit=20").decode("utf-8"))
        item = next(diag for diag in payload["diagnostics"] if diag["task_name"] == "sprint_generation")
        self.assertIn("route_used", item)
        self.assertIn("resolved_provider", item)
        self.assertIn("resolved_model", item)

    def test_test_ai_route_endpoint_never_returns_api_key(self) -> None:
        secret = "sk" + "-route-openai-secret"
        os.environ["SPRINTOS_AI_PROVIDER"] = "offline"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = secret
        sprintos.save_ai_route("codex_handoff", "ai", "openai", model="gpt-route-mini", enabled=True)
        server = self.start_server()
        with mock.patch(
            "sprintos.call_openai_responses",
            return_value=fake_provider_result(
                text='{"status":"ok","message":"SprintOS routed AI provider ready"}',
                parsed_json={"status": "ok", "message": "SprintOS routed AI provider ready"},
                ok=True,
                provider="openai",
                model="gpt-route-mini",
            ),
        ):
            payload = self.http_post_json(server, "/api/test_ai_route", {"task_name": "codex_handoff"})
        encoded = json.dumps(payload)
        self.assertNotIn(secret, encoded)
        self.assertTrue(payload["usable"])


class AIProviderComparisonTests(AIQualitySupportMixin, SprintOSTestCase):
    def test_ai_provider_evals_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertIn("ai_provider_evals", tables)

    def test_token_estimate_is_deterministic(self) -> None:
        text = "SprintOS compares provider routes safely."
        self.assertEqual(estimate_tokens_from_chars(text), estimate_tokens_from_chars(text))
        self.assertEqual(estimate_tokens_from_chars(text), estimate_tokens_from_chars(len(text)))

    def test_offline_provider_cost_is_zero(self) -> None:
        estimate = estimate_ai_cost("offline", "offline", 100, 50)
        self.assertEqual(estimate["estimated_cost_usd"], 0.0)
        self.assertEqual(estimate["warning"], "")

    def test_unknown_provider_or_model_returns_warning_and_null_cost(self) -> None:
        unknown_provider = estimate_ai_cost("mystery", "x", 100, 50)
        unknown_model = estimate_ai_cost("openai", "unknown-model", 100, 50)
        self.assertIsNone(unknown_provider["estimated_cost_usd"])
        self.assertIsNone(unknown_model["estimated_cost_usd"])
        self.assertTrue(unknown_provider["warning"])
        self.assertTrue(unknown_model["warning"])

    def test_cost_env_overrides_work(self) -> None:
        os.environ["SPRINTOS_OPENAI_INPUT_COST_PER_1M"] = "1.5"
        os.environ["SPRINTOS_OPENAI_OUTPUT_COST_PER_1M"] = "3.5"
        estimate = estimate_ai_cost("openai", "any-openai-model", 1000, 1000)
        self.assertEqual(estimate["estimated_cost_usd"], 0.005)
        self.assertIn("override", estimate["warning"].lower())

    def test_offline_eval_runs_for_all_supported_tasks(self) -> None:
        payload = sprintos.run_ai_provider_eval(eval_mode="offline_eval")
        self.assertEqual(payload["summary"]["count"], len(sprintos.SUPPORTED_AI_TASK_NAMES))
        self.assertEqual({item["task_name"] for item in payload["results"]}, set(sprintos.SUPPORTED_AI_TASK_NAMES))
        self.assertTrue(all(item["provider"] == "offline" for item in payload["results"]))

    def test_fake_valid_provider_eval_passes_schema(self) -> None:
        payload = sprintos.run_ai_provider_eval(eval_mode="fake_provider_eval", task_name="sprint_generation", provider="openai")
        valid = next(item for item in payload["results"] if item["metadata"]["scenario"] == "valid")
        self.assertTrue(valid["metadata"]["schema_valid"])
        self.assertIn(valid["status"], {"passed", "passed_with_warnings"})

    def test_fake_malformed_provider_eval_falls_back(self) -> None:
        payload = sprintos.run_ai_provider_eval(eval_mode="fake_provider_eval", task_name="resume_plan", provider="deepseek")
        malformed = next(item for item in payload["results"] if item["metadata"]["scenario"] == "malformed")
        self.assertEqual(malformed["status"], "fallback")
        self.assertTrue(malformed["metadata"]["fallback_used"])

    def test_fake_missing_field_provider_eval_falls_back(self) -> None:
        payload = sprintos.run_ai_provider_eval(eval_mode="fake_provider_eval", task_name="prototype_content", provider="openai")
        missing = next(item for item in payload["results"] if item["metadata"]["scenario"] == "missing_fields")
        self.assertEqual(missing["status"], "fallback")
        self.assertTrue(missing["metadata"]["fallback_used"])

    def test_eval_scores_stay_in_range(self) -> None:
        payload = sprintos.run_ai_provider_eval(eval_mode="fake_provider_eval", task_name="codex_handoff", provider="openai")
        for item in payload["results"]:
            self.assertGreaterEqual(item["score"], 0)
            self.assertLessEqual(item["score"], 100)

    def test_eval_rows_never_contain_fake_keys(self) -> None:
        sprintos.run_ai_provider_eval(eval_mode="fake_provider_eval", task_name="quick_launch_summary", provider="deepseek")
        encoded = json.dumps(sprintos.list_ai_provider_evals(limit=20))
        self.assertNotIn("sk-fake-openai-eval", encoded)
        self.assertNotIn("sk-fake-deepseek-eval", encoded)

    def test_route_recommendation_returns_offline_only_when_no_keys_usable(self) -> None:
        payload = sprintos.ai_route_recommendations_payload()
        self.assertEqual(payload["recommended_preset"], "offline_only")
        self.assertTrue(all(item["provider"] == "offline" for item in payload["routes"]))

    def test_route_recommendation_prefers_deepseek_for_high_volume_tasks_when_usable(self) -> None:
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["DEEPSEEK_API_KEY"] = "sk-deepseek-local-only"
        sprintos.run_ai_provider_eval(eval_mode="fake_provider_eval", provider="deepseek")
        payload = sprintos.ai_route_recommendations_payload()
        high_volume = {item["task_name"]: item for item in payload["routes"] if item["task_name"] in sprintos.HIGH_VOLUME_AI_TASKS}
        self.assertEqual(payload["recommended_preset"], "cheap_deepseek")
        self.assertTrue(all(item["provider"] == "deepseek" for item in high_volume.values()))

    def test_route_recommendation_can_return_mixed_when_both_providers_usable(self) -> None:
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-local-only"
        os.environ["DEEPSEEK_API_KEY"] = "sk-deepseek-local-only"
        sprintos.run_ai_provider_eval(eval_mode="fake_provider_eval")
        payload = sprintos.ai_route_recommendations_payload()
        by_task = {item["task_name"]: item for item in payload["routes"]}
        self.assertEqual(payload["recommended_preset"], "mixed")
        self.assertEqual(by_task["sprint_generation"]["provider"], "deepseek")
        self.assertEqual(by_task["codex_handoff"]["provider"], "openai")

    def test_applying_recommendations_updates_ai_provider_routes(self) -> None:
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["DEEPSEEK_API_KEY"] = "sk-deepseek-local-only"
        sprintos.run_ai_provider_eval(eval_mode="fake_provider_eval", provider="deepseek")
        server = self.start_server()
        payload = self.http_post_json(server, "/api/apply_ai_route_recommendations", {"apply": True, "latest": True})
        self.assertEqual(payload["recommended_preset"], "cheap_deepseek")
        self.assertEqual(sprintos.get_ai_route("sprint_generation")["provider"], "deepseek")

    def test_ai_provider_evals_endpoint_returns_redacted_rows(self) -> None:
        secret = "sk" + "-fake-openai-key"
        sprintos.record_ai_provider_eval(
            {
                "eval_name": "fake_provider_eval:valid",
                "task_name": "sprint_generation",
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "generation_mode": "ai",
                "status": "passed",
                "score": 100,
                "input_size_chars": 10,
                "output_size_chars": 10,
                "estimated_input_tokens": 3,
                "estimated_output_tokens": 3,
                "estimated_cost_usd": 0.00001,
                "fallback_reason": "",
                "metadata": {"note": secret, "openai_api_key": secret},
            }
        )
        server = self.start_server()
        payload = json.loads(self.http_get(server, "/api/ai_provider_evals?limit=20").decode("utf-8"))
        encoded = json.dumps(payload)
        self.assertNotIn(secret, encoded)
        self.assertEqual(payload["count"], 1)

    def test_ai_route_recommendations_endpoint_returns_explainable_reasons(self) -> None:
        server = self.start_server()
        payload = json.loads(self.http_get(server, "/api/ai_route_recommendations").decode("utf-8"))
        self.assertTrue(payload["recommendation_id"])
        self.assertTrue(all(item["reason"] for item in payload["routes"]))

    def test_diagnostics_include_estimated_token_and_cost_fields_when_available(self) -> None:
        self.enable_ai("openai")
        with mock.patch("sprintos_core.ai_provider.call_openai_responses", side_effect=self.provider_side_effect()):
            sprintos.generate_sprint("Build a small local tool.", "software_mvp", 120, "medium", "a local prototype", generation_mode="auto")
        diagnostic = next(item for item in sprintos.list_ai_diagnostics(limit=20) if item["task_name"] == "sprint_generation")
        self.assertGreater(diagnostic["estimated_input_tokens"], 0)
        self.assertGreaterEqual(diagnostic["estimated_output_tokens"], 0)
        self.assertIsNotNone(diagnostic["estimated_cost_usd"])

    def test_exports_do_not_leak_fake_keys_from_provider_evals(self) -> None:
        secret = "sk" + "-provider-eval-export-secret"
        sprintos.record_ai_provider_eval(
            {
                "eval_name": "fake_provider_eval:valid",
                "task_name": "sprint_generation",
                "provider": "openai",
                "model": "gpt-4.1-mini",
                "generation_mode": "ai",
                "status": "passed",
                "score": 100,
                "input_size_chars": 10,
                "output_size_chars": 10,
                "estimated_input_tokens": 3,
                "estimated_output_tokens": 3,
                "estimated_cost_usd": 0.00001,
                "fallback_reason": "",
                "metadata": {"note": secret, "openai_api_key": secret},
            }
        )
        project = self.create_project()
        _, markdown = sprintos.write_markdown_export(project)
        _, payload = sprintos.build_zip_export(project)
        self.assertNotIn(secret, markdown)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for name in zf.namelist():
                self.assertNotIn(secret, zf.read(name).decode("utf-8", errors="ignore"), name)
