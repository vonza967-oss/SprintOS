import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

import scripts.launch as launch
import scripts.live_app_generation_acceptance as live_acceptance
import scripts.readiness as readiness
import scripts.test_fast as test_fast
import scripts.test_full as test_full
from tests.test_support import SprintOSTestCase


class TestingToolTests(SprintOSTestCase):
    def test_fast_script_and_full_script_exist(self) -> None:
        self.assertTrue((Path(__file__).resolve().parent.parent / "scripts" / "test_fast.py").exists())
        self.assertTrue((Path(__file__).resolve().parent.parent / "scripts" / "test_full.py").exists())
        self.assertTrue((Path(__file__).resolve().parent.parent / "scripts" / "readiness.py").exists())

    def test_fast_runner_can_run_one_target(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            ok = test_fast.run_targets(["tests.test_core_helpers.CoreHelperTests.test_safe_slug_generation_is_stable"], verbosity=0)
        self.assertTrue(ok)

    def test_fast_runner_returns_false_for_bad_target(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            ok = test_fast.run_targets(["tests.does_not_exist"], verbosity=0)
        self.assertFalse(ok)

    def test_full_runner_commands_cover_unittest_smoke_and_health(self) -> None:
        joined = [" ".join(command) for command in test_full.FULL_COMMANDS]
        self.assertTrue(any("-m unittest" in command for command in joined))
        self.assertTrue(any("scripts/smoke.py" in command for command in joined))
        self.assertTrue(any("scripts/health.py" in command for command in joined))
        manual_joined = [" ".join(command) for command in test_full.OPTIONAL_RELEASE_CANDIDATE_COMMANDS]
        self.assertTrue(any("scripts/readiness.py" in command for command in manual_joined))

    def test_docs_mention_fast_and_full_testing_commands(self) -> None:
        root = Path(__file__).resolve().parent.parent
        readme = (root / "README.md").read_text(encoding="utf-8")
        agents = (root / "AGENTS.md").read_text(encoding="utf-8")
        review = (root / "docs" / "CODE_REVIEW.md").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/test_fast.py", readme)
        self.assertIn("python3 scripts/test_full.py", readme)
        self.assertIn("python3 scripts/readiness.py", readme)
        self.assertIn("python3 scripts/test_fast.py", agents)
        self.assertIn("python3 scripts/test_full.py", agents)
        self.assertIn("Fast tests cover the changed area", review)

    def test_readiness_docs_exist(self) -> None:
        root = Path(__file__).resolve().parent.parent
        self.assertTrue((root / "docs" / "V0_1_READINESS_AUDIT.md").exists())
        self.assertTrue((root / "docs" / "NEXT_REAL_USE.md").exists())
        self.assertTrue((root / "docs" / "DEMO_READINESS.md").exists())

    def test_demo_readiness_docs_summarize_acceptance_without_raw_payloads(self) -> None:
        root = Path(__file__).resolve().parent.parent
        demo_doc = (root / "docs" / "DEMO_READINESS.md").read_text(encoding="utf-8")
        checklist = (root / "docs" / "APP_GENERATION_ACCEPTANCE_CHECKLIST.md").read_text(encoding="utf-8")
        combined = demo_doc + "\n" + checklist

        for case_name in ("Idea Scorecard", "Budget Snapshot", "Habit Tracker", "Tattoo Studio CRM", "Agency Project Tracker"):
            with self.subTest(case_name=case_name):
                self.assertIn(case_name, combined)
        for unsafe in (
            "sk-",
            "Authorization:",
            "OPENAI_API_KEY=",
            "DEEPSEEK_API_KEY=",
            "raw_provider_response",
            "raw provider payload",
            "live-app-generation-acceptance.json",
            "live-app-generation-acceptance.md",
        ):
            with self.subTest(unsafe=unsafe):
                self.assertNotIn(unsafe, combined)
        self.assertIn("Live acceptance reports are local, redacted, and not committed.", demo_doc)

    def test_readiness_script_avoids_direct_external_api_calls(self) -> None:
        root = Path(__file__).resolve().parent.parent
        script = (root / "scripts" / "readiness.py").read_text(encoding="utf-8")
        self.assertNotIn("urlopen(", script)
        self.assertNotIn("requests.", script)
        self.assertNotIn("openai.", script.lower())
        self.assertNotIn("httpx.", script)

    def test_static_verification_utils_avoid_live_provider_calls(self) -> None:
        root = Path(__file__).resolve().parent.parent
        source = (root / "sprintos_core" / "verification_utils.py").read_text(encoding="utf-8")
        self.assertNotIn("urlopen(", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("openai.", source.lower())
        self.assertNotIn("deepseek", source.lower())
        self.assertNotIn("httpx.", source)

    def test_live_acceptance_shape_policy_rejects_flashcard_without_limitation_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "index.html").write_text(
                """<!doctype html><html><body><main data-app-shape="flashcard_helper"><textarea id="notes-input" data-template-marker="main-input"></textarea><button id="build-cards" data-template-marker="primary-action">Build Flashcards</button><section id="card-output" data-template-marker="flashcard-cards">Cards appear here.</section></main><script src="app.js"></script></body></html>""",
                encoding="utf-8",
            )
            (base / "app.js").write_text(
                "function buildCards(){const notes=document.getElementById('notes-input').value.trim();document.getElementById('card-output').innerHTML='<article class=\"flashcard-card\"><strong>Question</strong><p>Answer: '+notes+'</p></article>';}document.getElementById('build-cards').addEventListener('click', buildCards);",
                encoding="utf-8",
            )
            (base / "README.md").write_text("# Study Card Builder\n\nRun locally.\n", encoding="utf-8")

            result = live_acceptance._shape_result("flashcard_helper", base)

        self.assertFalse(result["ok"])
        self.assertTrue(
            any(item["name"] == "flashcard helper: mocked/local limitation note exists" and item["status"] == "warn" for item in result["failures"])
        )

    def test_live_acceptance_refuses_without_live_confirmation(self) -> None:
        with mock.patch.object(sys, "argv", ["live_app_generation_acceptance.py"]), \
             mock.patch.object(live_acceptance, "load_ai_provider_config", side_effect=AssertionError("provider config should not load")), \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            result = live_acceptance.main()

        self.assertEqual(result, 2)
        self.assertIn("--confirm-live-provider", stdout.getvalue())

    def test_live_acceptance_defaults_to_canonical_cases(self) -> None:
        with mock.patch.object(sys, "argv", ["live_app_generation_acceptance.py"]):
            args = live_acceptance.parse_args()

        self.assertEqual(args.case_set, "canonical")
        self.assertEqual(args.max_cases, 0)
        self.assertEqual(live_acceptance._case_sets(args.case_set), live_acceptance.CANONICAL_CASES)
        self.assertNotIn("habit_tracker", [item["name"] for item in live_acceptance._case_sets(args.case_set)])
        self.assertNotIn("tattoo_studio_crm", [item["name"] for item in live_acceptance._case_sets(args.case_set)])

    def test_live_acceptance_can_select_generic_all_or_broad_cases(self) -> None:
        with mock.patch.object(sys, "argv", ["live_app_generation_acceptance.py", "--case-set", "generic"]):
            generic_args = live_acceptance.parse_args()
        with mock.patch.object(sys, "argv", ["live_app_generation_acceptance.py", "--case-set", "all"]):
            all_args = live_acceptance.parse_args()
        with mock.patch.object(sys, "argv", ["live_app_generation_acceptance.py", "--case-set", "broad"]):
            broad_args = live_acceptance.parse_args()

        self.assertEqual([item["name"] for item in live_acceptance._case_sets(generic_args.case_set)], [item["name"] for item in live_acceptance.GENERIC_CUSTOM_CASES])
        all_names = [item["name"] for item in live_acceptance._case_sets(all_args.case_set)]
        self.assertIn("idea_scorer", all_names)
        self.assertIn("habit_tracker", all_names)
        self.assertNotIn("tattoo_studio_crm", all_names)
        broad_cases = live_acceptance._case_sets(broad_args.case_set)
        self.assertEqual(len(broad_cases), 10)
        self.assertIn("tattoo_studio_crm", [item["name"] for item in broad_cases])
        self.assertTrue(all(item.get("contract") == "universal_app_contract_v1" for item in broad_cases))
        self.assertTrue(all(not item.get("shape") for item in broad_cases))

    def test_live_acceptance_max_cases_limits_selected_cases(self) -> None:
        with mock.patch.object(sys, "argv", ["live_app_generation_acceptance.py", "--case-set", "broad", "--max-cases", "5"]):
            args = live_acceptance.parse_args()

        selected = live_acceptance._selected_cases(args.case_set, args.max_cases)

        self.assertEqual(args.max_cases, 5)
        self.assertEqual(len(selected), 5)
        self.assertEqual(selected[0]["name"], "tattoo_studio_crm")
        self.assertEqual(selected[-1]["name"], "meal_planner")

    def test_live_acceptance_generic_shape_uses_universal_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ("index.html", "app.js", "README.md", "TEST_PLAN.md"):
                (base / name).write_text("", encoding="utf-8")
            with mock.patch.object(live_acceptance, "static_app_shape_verification_checks", side_effect=AssertionError("canonical verifier should not run")), \
                 mock.patch.object(
                     live_acceptance,
                     "universal_app_contract_verification_checks",
                     return_value=[{"name": "universal app: marker", "status": "pass", "message": "ok", "path": str(base / "index.html")}],
                 ) as universal:
                result = live_acceptance._shape_result("", base, project_text="Track habits locally.", generic=True)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["contract"], "universal_app_contract_v1")
        self.assertFalse(result["canonical_shape_applied"])
        universal.assert_called_once()

    def test_live_acceptance_broad_shape_rejects_canonical_inference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ("index.html", "app.js", "README.md", "TEST_PLAN.md"):
                (base / name).write_text("", encoding="utf-8")
            with mock.patch.object(live_acceptance, "infer_static_app_shape", return_value="budget_calculator"), \
                 mock.patch.object(
                     live_acceptance,
                     "universal_app_contract_verification_checks",
                     return_value=[{"name": "universal app: marker", "status": "pass", "message": "ok", "path": str(base / "index.html")}],
                 ):
                result = live_acceptance._shape_result("", base, project_text="Create a local meal planner.", generic=True)

        self.assertFalse(result["ok"])
        self.assertEqual(result["contract"], "universal_app_contract_v1")
        self.assertTrue(result["canonical_shape_applied"])
        self.assertEqual(result["inferred_canonical_shape"], "budget_calculator")
        self.assertTrue(any("incorrectly inferred as canonical" in item["message"] for item in result["failures"]))

    def test_live_acceptance_broad_shape_does_not_treat_prompt_keyword_as_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ("index.html", "app.js", "README.md", "TEST_PLAN.md"):
                (base / name).write_text("", encoding="utf-8")
            with mock.patch.object(
                live_acceptance,
                "universal_app_contract_verification_checks",
                return_value=[{"name": "universal app: marker", "status": "pass", "message": "ok", "path": str(base / "index.html")}],
            ):
                result = live_acceptance._shape_result(
                    "",
                    base,
                    project_text="Create a local event planner with budget notes.",
                    generic=True,
                    include_project_text_for_inference=False,
                )

        self.assertTrue(result["ok"], result)
        self.assertFalse(result["canonical_shape_applied"])

    def test_live_acceptance_canonical_shape_uses_canonical_verifier(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ("index.html", "app.js", "README.md", "TEST_PLAN.md"):
                (base / name).write_text("", encoding="utf-8")
            with mock.patch.object(live_acceptance, "universal_app_contract_verification_checks", side_effect=AssertionError("universal verifier should not run")), \
                 mock.patch.object(
                     live_acceptance,
                     "static_app_shape_verification_checks",
                     return_value=[{"name": "business idea scorer: marker", "status": "pass", "message": "ok", "path": str(base / "index.html")}],
                 ) as canonical:
                result = live_acceptance._shape_result("business_idea_scorer", base, generic=False)

        self.assertTrue(result["ok"], result)
        self.assertEqual(result["contract"], "canonical_app_shape_v1")
        canonical.assert_called_once()

    def test_live_acceptance_report_redacts_unsafe_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            payload = {
                "ok": False,
                "generated_at": "2026-05-09T00:00:00",
                "provider": "openai",
                "model": "test-model",
                "case_set": "generic",
                "run_root": str(run_root),
                "raw_prompt": "Create a secret app with sk-live-unsafe1234567890",
                "raw_provider_response": "Authorization: Bearer unsafe-token",
                "cases": [
                    {
                        "name": "habit_tracker",
                        "display_name": "Habit Tracker",
                        "contract": "universal_app_contract_v1",
                        "case_summary": "Safe local habit tracker summary.",
                        "ok": False,
                        "ai": {"used_ai": True},
                        "files": {"ok": True},
                        "preview": {"ok": True},
                        "package": {"ok": True},
                        "safety": {"ok": False},
                        "intent_blueprint": {"ok": True},
                        "shape_checks": {"ok": True},
                        "quality_observation": "broken",
                        "safe_failure_types": ["safety issue"],
                        "failure_reasons": ["Authorization: Bearer unsafe-token sk-live-unsafe1234567890"],
                    }
                ],
                "failure_reasons": ["sk-live-unsafe1234567890"],
            }

            live_acceptance._write_reports(run_root, payload)
            report_json = json.loads((run_root / "live-app-generation-acceptance.json").read_text(encoding="utf-8"))
            report_md = (run_root / "live-app-generation-acceptance.md").read_text(encoding="utf-8")

        self.assertEqual(report_json["raw_prompt"], "[redacted]")
        self.assertEqual(report_json["raw_provider_response"], "[redacted]")
        self.assertIn("Safe local habit tracker summary.", report_md)
        self.assertIn("Quality: broken", report_md)
        self.assertIn("Safe failure type: safety issue", report_md)
        self.assertNotIn("sk-live-unsafe1234567890", report_md)
        self.assertNotIn("unsafe-token", report_md)

    def test_live_acceptance_intent_blueprint_summary_is_redacted_metadata_only(self) -> None:
        project = {
            "sprint": {
                "_app_intent_review": live_acceptance.sprintos.review_app_intent(
                    "Create a local booking tracker for a barber to manage client names, service type, appointment time, status, and daily schedule."
                )
            }
        }

        result = live_acceptance._intent_blueprint_result(project, live_acceptance.BROAD_ARBITRARY_CASES[1])

        self.assertTrue(result["ok"], result)
        self.assertTrue(result["brief_available"])
        self.assertIn("app_blueprint", result["summary"])
        self.assertNotIn("raw_idea", result["summary"])

    def test_live_acceptance_generation_failure_keeps_safe_diagnostic_and_failure_type(self) -> None:
        case = live_acceptance.BROAD_ARBITRARY_CASES[0]
        project = {
            "id": "project-1",
            "sprint": {
                "_app_intent_review": live_acceptance.sprintos.review_app_intent(case["raw_idea"])
            },
        }
        diagnostic = {"used_ai": True, "provider": "openai", "fallback_reason": "app_shape_validation_failed"}

        with mock.patch.object(live_acceptance, "_diagnostic_for_project", return_value=diagnostic):
            result = live_acceptance._case_generation_failure(
                case,
                project,
                RuntimeError("Generic/custom app generation did not create app files: app_shape_validation_failed"),
            )

        self.assertFalse(result["ok"])
        self.assertTrue(result["ai"]["used_ai"])
        self.assertIn("provider output issue", result["safe_failure_types"])
        self.assertIn("generic verification issue", result["safe_failure_types"])
        self.assertNotIn("provider variance", result["safe_failure_types"])

    def test_readiness_script_runs_offline(self) -> None:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = readiness.run_readiness_check()
        self.assertTrue(result["ok"])
        self.assertTrue(result["project_id"])
        self.assertTrue(result["project_title"])
        self.assertTrue(result["workspace_path"])
        self.assertTrue(result["release_path"])

    def test_launcher_and_stop_scripts_exist(self) -> None:
        root = Path(__file__).resolve().parent.parent
        self.assertTrue((root / "scripts" / "launch.py").exists())
        self.assertTrue((root / "scripts" / "stop.py").exists())
        self.assertTrue((root / "run_sprintos.command").exists())
        self.assertTrue((root / "run_sprintos.sh").exists())
        self.assertTrue((root / "run_sprintos.ps1").exists())

    def test_launch_script_does_not_use_shell_true(self) -> None:
        root = Path(__file__).resolve().parent.parent
        launch_source = (root / "scripts" / "launch.py").read_text(encoding="utf-8")
        self.assertNotIn("shell=True", launch_source)

    def test_stop_script_does_not_kill_processes(self) -> None:
        root = Path(__file__).resolve().parent.parent
        stop_source = (root / "scripts" / "stop.py").read_text(encoding="utf-8")
        self.assertNotIn(".kill(", stop_source)
        self.assertNotIn(".terminate(", stop_source)

    def test_readme_mentions_launcher_and_stop_commands(self) -> None:
        root = Path(__file__).resolve().parent.parent
        readme = (root / "README.md").read_text(encoding="utf-8")
        self.assertIn("python3 scripts/launch.py", readme)
        self.assertIn("python3 sprintos.py", readme)
        self.assertIn("python3 scripts/stop.py", readme)
        self.assertIn("run_sprintos.command", readme)

    def test_launch_script_handles_already_running_server(self) -> None:
        status = {
            "ok": True,
            "app": "SprintOS",
            "url": "http://127.0.0.1:8844",
            "pid": 1234,
            "data_dir": "/tmp/data",
            "exports_dir": "/tmp/exports",
            "workspaces_dir": "/tmp/workspaces",
            "backups_dir": "/tmp/backups",
        }
        with mock.patch.object(launch, "is_server_healthy", return_value=True), \
             mock.patch.object(launch, "fetch_server_status", return_value=status), \
             mock.patch.object(launch, "open_browser") as open_browser, \
             mock.patch.object(launch, "print_runtime_status") as print_status:
            result = launch.run_launcher()
        self.assertEqual(result, 0)
        open_browser.assert_called_once_with("http://127.0.0.1:8844")
        print_status.assert_called_once_with(status, already_running=True)
