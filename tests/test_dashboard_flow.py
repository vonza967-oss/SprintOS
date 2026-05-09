import io
import json
import os
import urllib.error
import zipfile
from pathlib import Path

import sprintos
from sprintos_core.ai_provider import fake_provider_result

from tests.test_support import SprintOSTestCase


class DashboardFlowTests(SprintOSTestCase):
    def test_setup_doctor_endpoint_returns_expected_structure(self) -> None:
        server = self.start_server()
        payload = json.loads(self.http_get(server, "/api/setup_doctor").decode("utf-8"))
        self.assertIn(payload["status"], {"ok", "warning", "blocked"})
        self.assertIsInstance(payload["score"], int)
        self.assertIn("checks", payload)
        self.assertIn("recommended_action", payload)
        self.assertIn("sections", payload)
        self.assertIn("runtime", payload["sections"])
        self.assertIn("storage", payload["sections"])
        self.assertIn("database", payload["sections"])

    def test_setup_doctor_sections_include_expected_checks(self) -> None:
        payload = sprintos.run_setup_doctor()
        check_ids = {item["id"] for item in payload["checks"]}
        self.assertIn("runtime_server_responds", check_ids)
        self.assertIn("runtime_launchers_exist", check_ids)
        self.assertIn("storage_data_dir", check_ids)
        self.assertIn("storage_safe_write_test", check_ids)
        self.assertIn("database_core_tables", check_ids)
        self.assertIn("backup_latest_exists", check_ids)
        self.assertIn("ai_status_loads", check_ids)

    def test_setup_doctor_warns_when_no_backup_exists(self) -> None:
        payload = sprintos.run_setup_doctor()
        self.assertEqual(payload["status"], "warning")
        self.assertTrue(any("No local backup exists yet." in item for item in payload["warnings"]))
        self.assertEqual(payload["recommended_action"]["action_id"], "create_backup")

    def test_setup_doctor_warns_when_ai_provider_enabled_but_key_missing(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = ""
        payload = sprintos.run_setup_doctor()
        self.assertTrue(payload["sections"]["ai"]["provider_missing_key_warning"])
        self.assertEqual(payload["recommended_action"]["action_id"], "create_backup")
        self.create_local_backup("doctor")
        verified = self.verify_local_backup()
        self.assertTrue(verified["verified"])
        payload = sprintos.run_setup_doctor()
        self.assertEqual(payload["recommended_action"]["action_id"], "switch_ai_offline_or_add_key")

    def test_setup_doctor_warns_when_app_generation_budget_is_low(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-test-present"
        os.environ["SPRINTOS_AI_TIMEOUT_SECONDS"] = "30"
        os.environ["SPRINTOS_AI_MAX_OUTPUT_TOKENS"] = "3000"

        payload = sprintos.run_setup_doctor()
        check_map = {item["id"]: item for item in payload["checks"]}

        self.assertEqual(check_map["ai_app_generation_timeout_budget"]["status"], "warn")
        self.assertEqual(check_map["ai_app_generation_token_budget"]["status"], "warn")
        self.assertIn("below 90 seconds", check_map["ai_app_generation_timeout_budget"]["message"])
        self.assertIn("below 6000", check_map["ai_app_generation_token_budget"]["message"])

    def test_setup_doctor_budget_warning_disappears_at_app_generation_recommendation(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-test-present"
        os.environ["SPRINTOS_AI_TIMEOUT_SECONDS"] = "90"
        os.environ["SPRINTOS_AI_MAX_OUTPUT_TOKENS"] = "6000"

        payload = sprintos.run_setup_doctor()
        check_map = {item["id"]: item for item in payload["checks"]}

        self.assertEqual(check_map["ai_app_generation_timeout_budget"]["status"], "pass")
        self.assertEqual(check_map["ai_app_generation_token_budget"]["status"], "pass")

    def test_setup_doctor_explains_ai_only_mode(self) -> None:
        os.environ["SPRINTOS_APP_GENERATION_FALLBACK_MODE"] = "report_only"

        payload = sprintos.run_setup_doctor()
        ai_section = payload["sections"]["ai"]
        check_map = {item["id"]: item for item in payload["checks"]}

        self.assertTrue(ai_section["ai_only_mode_enabled"])
        self.assertEqual(ai_section["app_generation_fallback_mode"], "report_only")
        self.assertIn("AI-only mode is enabled", check_map["ai_app_generation_fallback_mode"]["message"])

    def test_setup_doctor_warns_when_recent_app_generation_failed(self) -> None:
        sprintos.record_ai_diagnostic(
            "app_file_generation",
            fake_provider_result(ok=False, provider="deepseek", used_ai=False, fallback_reason="deepseek_invalid_json"),
        )

        payload = sprintos.run_setup_doctor()
        check_map = {item["id"]: item for item in payload["checks"]}

        self.assertEqual(check_map["ai_app_generation_recent_result"]["status"], "warn")
        self.assertIn("invalid_json", check_map["ai_app_generation_recent_result"]["message"])

    def test_setup_doctor_never_exposes_fake_openai_key(self) -> None:
        fake_key = "sk-fake-openai-doctor-secret"
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = fake_key
        encoded = json.dumps(sprintos.run_setup_doctor())
        self.assertNotIn(fake_key, encoded)

    def test_setup_doctor_never_exposes_fake_deepseek_key(self) -> None:
        fake_key = "sk-fake-deepseek-doctor-secret"
        os.environ["SPRINTOS_AI_PROVIDER"] = "deepseek"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["DEEPSEEK_API_KEY"] = fake_key
        encoded = json.dumps(sprintos.run_setup_doctor())
        self.assertNotIn(fake_key, encoded)

    def test_setup_doctor_export_returns_markdown(self) -> None:
        server = self.start_server()
        markdown = self.http_get(server, "/api/setup_doctor_export").decode("utf-8")
        self.assertIn("# Setup Doctor", markdown)
        self.assertIn("## Runtime", markdown)
        self.assertIn("## Recommended Action", markdown)

    def test_run_setup_doctor_action_create_backup_creates_backup_and_activity(self) -> None:
        server = self.start_server()
        payload = self.http_post_json(server, "/api/run_setup_doctor_action", {})
        self.assertTrue(payload["ran"])
        self.assertEqual(payload["action_id"], "create_backup")
        self.assertTrue(payload["backup"]["backup_id"])
        event_types = [item["event_type"] for item in self.list_activity(limit=20)]
        self.assertIn("setup_doctor_backup_created", event_types)
        self.assertIn("setup_doctor_action_run", event_types)

    def test_run_setup_doctor_action_verify_backup_verifies_latest_backup(self) -> None:
        backup = self.create_local_backup("doctor-verify")
        server = self.start_server()
        payload = self.http_post_json(server, "/api/run_setup_doctor_action", {"action_id": "verify_backup"})
        self.assertTrue(payload["ran"])
        self.assertEqual(payload["action_id"], "verify_backup")
        self.assertEqual(payload["backup"]["backup_id"], backup["backup_id"])
        self.assertTrue(payload["backup"]["verified"])

    def test_run_setup_doctor_action_does_not_edit_ai_settings(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = ""
        self.create_local_backup("doctor-ai")
        self.verify_local_backup()
        server = self.start_server()
        payload = self.http_post_json(server, "/api/run_setup_doctor_action", {"action_id": "switch_ai_offline_or_add_key"})
        self.assertFalse(payload["ran"])
        self.assertEqual(os.environ["SPRINTOS_AI_PROVIDER"], "openai")
        self.assertEqual(os.environ["SPRINTOS_AI_ENABLED"], "true")

    def test_activity_events_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertIn("activity_events", tables)

    def test_demo_runs_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertIn("demo_runs", tables)

    def test_record_activity_event_persists_event(self) -> None:
        project = self.create_project()
        event = sprintos.record_activity_event(
            project["id"],
            "manual_note",
            "Manual note",
            "Captured one small manual status note.",
            event_status="info",
            actor="user",
            related_type="project",
            related_id=project["id"],
            next_tiny_action="Open the project and continue.",
        )
        self.assertIsNotNone(event)
        events = self.list_activity(project["id"])
        self.assertEqual(events[0]["title"], "Manual note")
        self.assertEqual(events[0]["actor"], "user")

    def test_record_activity_event_redacts_fake_openai_key(self) -> None:
        project = self.create_project()
        secret = "sk-fake-openai-activity-secret"
        sprintos.record_activity_event(
            project["id"],
            "manual_note",
            f"Leaked {secret}",
            f"OPENAI_API_KEY={secret}",
            metadata={"note": f"Authorization: Bearer {secret}", "openai_api_key": secret},
        )
        encoded = json.dumps(self.list_activity(project["id"]))
        self.assertNotIn(secret, encoded)
        self.assertIn("[redacted]", encoded)

    def test_record_activity_event_redacts_fake_deepseek_key(self) -> None:
        project = self.create_project()
        secret = "sk-fake-deepseek-activity-secret"
        sprintos.record_activity_event(
            project["id"],
            "manual_note",
            "DeepSeek key test",
            f"DEEPSEEK_API_KEY={secret}",
            metadata={"deepseek_api_key": secret, "headers": {"Authorization": f"Bearer {secret}"}},
        )
        encoded = json.dumps(self.list_activity(project["id"]))
        self.assertNotIn(secret, encoded)
        self.assertIn("[redacted]", encoded)

    def test_project_hydration_includes_recent_activity_events(self) -> None:
        project = self.create_project()
        sprintos.add_progress_note(project["id"], "Captured a progress checkpoint.")
        refreshed = sprintos.get_project(project["id"])
        self.assertIsNotNone(refreshed)
        self.assertTrue(refreshed["recent_activity_events"])
        self.assertEqual(refreshed["latest_activity_event"]["event_type"], "progress_note_added")

    def test_activity_timeline_endpoint_returns_events(self) -> None:
        project = self.create_project()
        sprintos.add_progress_note(project["id"], "Timeline endpoint note.")
        server = self.start_server()
        payload = json.loads(self.http_get(server, f"/api/project_timeline?project_id={project['id']}&limit=5").decode("utf-8"))
        self.assertEqual(payload["project_id"], project["id"])
        self.assertGreaterEqual(payload["count"], 1)
        self.assertEqual(payload["events"][0]["event_type"], "progress_note_added")

    def test_global_activity_endpoint_returns_events(self) -> None:
        project = self.create_project()
        sprintos.add_progress_note(project["id"], "Global timeline note.")
        server = self.start_server()
        payload = json.loads(self.http_get(server, "/api/global_activity?limit=5").decode("utf-8"))
        self.assertGreaterEqual(payload["count"], 1)
        self.assertEqual(payload["events"][0]["project_id"], project["id"])

    def test_manual_activity_note_endpoint_validates_required_fields(self) -> None:
        server = self.start_server()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.http_post_json(server, "/api/add_activity_event", {"project_id": "", "title": "", "summary": ""})
        self.assertEqual(cm.exception.code, 400)

    def test_manual_activity_note_endpoint_rejects_invalid_status(self) -> None:
        project = self.create_project()
        server = self.start_server()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.http_post_json(
                server,
                "/api/add_activity_event",
                {"project_id": project["id"], "title": "Bad status", "summary": "This should fail.", "event_status": "mystery"},
            )
        self.assertEqual(cm.exception.code, 400)

    def test_project_creation_records_activity(self) -> None:
        project = self.create_project()
        event_types = [item["event_type"] for item in self.list_activity(project["id"], limit=10)]
        self.assertIn("project_created", event_types)
        self.assertIn("sprint_generated", event_types)

    def test_major_project_flows_record_activity(self) -> None:
        project = self.create_project()
        focus_session = self.start_focus_session(project, action_id="generate_prototype")
        sprintos.complete_focus_session(focus_session["focus_session_id"], outcome="Completed the first focused step.")
        prototype = self.generate_prototype(project, "landing_page")
        sprintos.add_feedback_entry(project["id"], prototype_id=prototype["id"], tester_label="Flow tester", source="manual")
        summary = sprintos.build_iteration_summary(sprintos.get_project(project["id"]), prototype["id"])
        sprintos.save_iteration_snapshot(project["id"], prototype["id"], summary)
        deploy_pack = self.generate_deploy_pack(project, prototype, "static")
        build_pack = self.generate_build_pack(project, prototype, deploy_pack=deploy_pack, build_target="static_app")
        pipeline_run = self.generate_pipeline(project)
        self.run_verification(project, verification_scope="pipeline", pipeline_run_id=pipeline_run["pipeline_run_id"])
        workspace = self.export_workspace(project, build_pack)
        snapshot = self.create_workspace_snapshot(project, workspace)
        workspace_path = Path(workspace["path"])
        app_path = workspace_path / "src" / "app.js"
        original_text = app_path.read_text(encoding="utf-8")
        app_path.write_text(original_text + "\nconsole.log('activity test');\n", encoding="utf-8")
        self.restore_workspace_snapshot(snapshot)
        self.sync_workspace(project, workspace)
        self.run_verification(project, verification_scope="build_pack", build_pack_id=build_pack["id"])
        self.create_workspace_release(project, workspace, release_label="activity-rc", run_checks=True)
        event_types = {item["event_type"] for item in self.list_activity(project["id"], limit=50)}
        expected = {
            "focus_session_started",
            "focus_session_completed",
            "prototype_generated",
            "feedback_added",
            "iteration_brief_generated",
            "deploy_pack_generated",
            "build_pack_generated",
            "pipeline_run_completed",
            "verification_run_completed",
            "workspace_exported",
            "workspace_snapshot_created",
            "workspace_restored",
            "workspace_synced",
            "workspace_release_pack_created",
        }
        self.assertTrue(expected.issubset(event_types))

    def test_guided_demo_records_activity_events(self) -> None:
        demo_run = self.run_guided_demo("quick")
        global_event_types = [item["event_type"] for item in self.list_activity(limit=20)]
        project_event_types = [item["event_type"] for item in self.list_activity(demo_run["project_id"], limit=20)]
        self.assertIn("guided_demo_started", global_event_types)
        self.assertIn("guided_demo_completed", project_event_types)

    def test_flashcard_idea_proves_basic_app_creation_chain(self) -> None:
        quick_launch = self.generate_quick_launch(
            raw_idea="I want a simple app where users paste study notes and get flashcards.",
            end_output="a local testable flashcard prototype",
            generation_mode="offline",
        )
        project = sprintos.get_project(quick_launch["project_id"])
        self.assertIsNotNone(project)
        self.assertTrue(project["sprint"])
        self.assertIsNotNone(project["latest_prototype"])
        self.assertIsNotNone(project["latest_build_pack"])

        workspace = sprintos.write_workspace_export(project, project["latest_build_pack"])
        self.assertTrue(Path(workspace["path"]).exists())

        sprintos.run_workspace_sync(project["id"], workspace_id=workspace["workspace_id"], run_checks=True, allow_git=False)
        verification = sprintos.run_project_verification(project["id"], verification_scope="all_latest")
        self.assertIn(verification["status"], {"passed", "passed_with_warnings", "partial"})

        release_pack = sprintos.create_workspace_release_pack(
            project["id"],
            workspace_id=workspace["workspace_id"],
            release_label="readiness-proof",
            run_checks=True,
        )
        self.assertTrue(Path(release_pack["path"]).exists())

        command_center = sprintos.build_project_command_summary(sprintos.get_project(project["id"]) or project)
        self.assertTrue(command_center["recommended_action"]["action_id"])
        self.assertTrue(command_center["next_tiny_action"])

        artifact_history = sprintos.get_project_artifact_history(project["id"], limit_per_type=10)
        self.assertGreaterEqual(int(artifact_history["total_count"]), 1)

        backup = self.create_local_backup("readiness-proof")
        self.assertTrue(Path(backup["backup_path"]).exists())

    def test_run_guided_demo_quick_creates_project_and_core_artifacts(self) -> None:
        demo_run = self.run_guided_demo("quick")
        project = sprintos.get_project(demo_run["project_id"])
        self.assertIsNotNone(project)
        self.assertEqual(project["title"], "AI Study Flashcard Helper")
        self.assertEqual(demo_run["demo_mode"], "quick")
        self.assertIn(demo_run["run_status"], {"completed", "completed_with_warnings", "partial"})
        self.assertIsNotNone(project["latest_prototype"])
        self.assertIsNotNone(project["latest_build_pack"])
        self.assertIsNone(project["latest_workspace"])
        self.assertTrue(Path(demo_run["report_path"]).exists())

    def test_run_guided_demo_full_creates_workspace_release_feedback_and_iteration(self) -> None:
        demo_run = self.run_guided_demo("full")
        project = sprintos.get_project(demo_run["project_id"])
        self.assertIsNotNone(project)
        self.assertEqual(demo_run["demo_mode"], "full")
        self.assertTrue(project["latest_workspace"])
        self.assertTrue(project["latest_workspace_snapshot"])
        self.assertTrue(project["latest_workspace_sync"])
        self.assertTrue(project["latest_verification_run"])
        self.assertTrue(project["latest_workspace_release_pack"])
        self.assertGreater(project["release_feedback"]["feedback_count"], 0)
        self.assertTrue(project["recent_release_feedback"])
        self.assertTrue(project["latest_release_iteration"])

    def test_demo_run_report_folder_includes_required_files(self) -> None:
        demo_run = self.run_guided_demo("quick")
        report_dir = Path(demo_run["report_path"])
        for name in sprintos.GUIDED_DEMO_REPORT_FILES:
            self.assertTrue((report_dir / name).exists(), name)

    def test_demo_run_zip_includes_report_files(self) -> None:
        demo_run = self.run_guided_demo("full")
        zip_name, payload = sprintos.build_demo_run_zip(demo_run)
        self.assertTrue(zip_name.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
        self.assertTrue(set(sprintos.GUIDED_DEMO_REPORT_FILES).issubset(names))

    def test_demo_run_api_endpoints_return_expected_payload(self) -> None:
        server = self.start_server()
        created = self.http_post_json(server, "/api/run_guided_demo", {"demo_mode": "quick"})
        self.assertIn("demo_run_id", created)
        self.assertEqual(created["demo_mode"], "quick")
        fetched = json.loads(self.http_get(server, f"/api/demo_run?id={created['demo_run_id']}").decode("utf-8"))
        self.assertEqual(fetched["demo_run_id"], created["demo_run_id"])
        report = self.http_get(server, f"/api/demo_run_file?id={created['demo_run_id']}&file=demo-report.md").decode("utf-8")
        self.assertIn("# Guided Demo Report", report)

    def test_demo_run_file_endpoint_blocks_path_traversal(self) -> None:
        server = self.start_server()
        created = self.http_post_json(server, "/api/run_guided_demo", {"demo_mode": "quick"})
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.http_get(server, f"/api/demo_run_file?id={created['demo_run_id']}&file=../.env")
        self.assertEqual(cm.exception.code, 400)

    def test_setup_doctor_mentions_guided_demo_as_secondary_action_when_no_projects_exist(self) -> None:
        self.create_local_backup("doctor-guided-demo")
        self.verify_local_backup()
        payload = sprintos.run_setup_doctor()
        self.assertEqual(payload["secondary_action"]["action_id"], "run_guided_demo")
        self.assertEqual(payload["secondary_action"]["button_label"], "Create Sample Project")

    def test_setup_doctor_action_can_run_guided_demo(self) -> None:
        self.create_local_backup("doctor-guided-demo-action")
        self.verify_local_backup()
        server = self.start_server()
        payload = self.http_post_json(server, "/api/run_setup_doctor_action", {"action_id": "run_guided_demo"})
        self.assertTrue(payload["ran"])
        self.assertEqual(payload["action_id"], "run_guided_demo")
        self.assertIn("demo_run", payload)
        self.assertTrue(payload["demo_run"]["project_id"])

    def test_today_dashboard_first_run_includes_guided_demo_action(self) -> None:
        summary = sprintos.build_today_dashboard_summary()
        self.assertTrue(summary["first_run_onboarding"]["show"])
        self.assertEqual(summary["first_run_onboarding"]["secondary_cta_action"], "run_guided_demo")

    def test_guided_demo_project_appears_in_normal_project_list_and_command_center_works(self) -> None:
        demo_run = self.run_guided_demo("quick")
        projects = sprintos.list_projects("all")
        self.assertIn(demo_run["project_id"], [item["id"] for item in projects])
        server = self.start_server()
        payload = json.loads(self.http_get(server, f"/api/project_command_center?project_id={demo_run['project_id']}").decode("utf-8"))
        self.assertIn("recommended_action", payload["command_center"])

    def test_guided_demo_reports_and_zip_do_not_expose_fake_keys(self) -> None:
        fake_openai = "sk-fake-openai-demo-secret"
        fake_deepseek = "sk-fake-deepseek-demo-secret"
        os.environ["OPENAI_API_KEY"] = fake_openai
        os.environ["DEEPSEEK_API_KEY"] = fake_deepseek
        demo_run = self.run_guided_demo("full")
        report_text = (Path(demo_run["report_path"]) / "demo-report.md").read_text(encoding="utf-8")
        summary_text = (Path(demo_run["report_path"]) / "demo-summary.json").read_text(encoding="utf-8")
        self.assertNotIn(fake_openai, report_text + summary_text)
        self.assertNotIn(fake_deepseek, report_text + summary_text)
        _, payload = sprintos.build_demo_run_zip(demo_run)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            combined = "\n".join(zf.read(name).decode("utf-8") for name in zf.namelist())
        self.assertNotIn(fake_openai, combined)
        self.assertNotIn(fake_deepseek, combined)

    def test_quick_launch_records_activity(self) -> None:
        quick_launch = self.generate_quick_launch()
        event_types = {item["event_type"] for item in self.list_activity(quick_launch["project_id"], limit=20)}
        self.assertIn("quick_launch_completed", event_types)

    def test_ai_route_preset_records_global_activity(self) -> None:
        sprintos.apply_ai_route_preset("offline_only")
        events = self.list_activity(limit=10)
        self.assertIn("ai_route_preset_applied", [item["event_type"] for item in events])

    def test_today_dashboard_recent_projects_can_use_latest_activity_for_recency(self) -> None:
        older = self.create_project(raw_idea="Older project")
        newer = self.create_project(raw_idea="Newer project")
        old_timestamp = "2024-01-01T00:00:00"
        with sprintos.db() as conn:
            conn.execute("UPDATE projects SET updated_at = ? WHERE id IN (?, ?)", (old_timestamp, older["id"], newer["id"]))
            conn.commit()
        sprintos.record_activity_event(older["id"], "manual_note", "Fresh activity", "This older project became active again.")
        with sprintos.db() as conn:
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (old_timestamp, older["id"]))
            conn.commit()
        summary = sprintos.build_today_dashboard_summary()
        self.assertEqual(summary["recent_projects"][0]["project_id"], older["id"])

    def test_today_dashboard_export_includes_recent_activity(self) -> None:
        project = self.create_project()
        sprintos.add_progress_note(project["id"], "Dashboard export note.")
        markdown = sprintos.today_dashboard_export_markdown(sprintos.build_today_dashboard_summary())
        self.assertIn("## Recent Global Activity", markdown)
        self.assertIn("Dashboard export note", markdown)

    def test_command_center_includes_latest_activity(self) -> None:
        project = self.create_project()
        sprintos.add_progress_note(project["id"], "Command center activity note.")
        refreshed = sprintos.get_project(project["id"])
        summary = sprintos.build_project_command_summary(refreshed)
        self.assertTrue(summary["latest_activity_event"])
        self.assertIn("Command center activity note", summary["last_happened"])
        self.assertIn("artifact_history_count", summary)
        self.assertIn("latest_artifact_type", summary)

    def test_project_markdown_and_zip_exports_include_activity_timeline(self) -> None:
        project = self.create_project()
        sprintos.add_progress_note(project["id"], "Export activity note.")
        refreshed = sprintos.get_project(project["id"])
        markdown_name, markdown = sprintos.write_markdown_export(refreshed)
        self.assertTrue(markdown_name.endswith(".md"))
        self.assertIn("## Activity Timeline", markdown)
        filename, payload = sprintos.build_zip_export(refreshed)
        self.assertTrue(filename.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertIn("activity-timeline.md", set(zf.namelist()))
            self.assertIn("artifact-history.md", set(zf.namelist()))

    def test_artifact_history_endpoint_requires_project_id(self) -> None:
        server = self.start_server()
        with self.assertRaises(urllib.error.HTTPError) as cm:
            self.http_get(server, "/api/project_artifact_history")
        self.assertEqual(cm.exception.code, 400)

    def test_artifact_history_endpoint_returns_empty_groups_for_project_with_no_generated_artifacts(self) -> None:
        project = self.create_project()
        server = self.start_server()
        payload = json.loads(self.http_get(server, f"/api/project_artifact_history?project_id={project['id']}&limit=10").decode("utf-8"))
        self.assertEqual(payload["project_id"], project["id"])
        self.assertEqual(payload["groups"]["prototypes"], [])
        self.assertEqual(payload["groups"]["deploy_packs"], [])
        self.assertEqual(payload["groups"]["build_packs"], [])
        self.assertTrue(payload["groups"]["activity_events"])

    def test_artifact_history_tracks_generated_artifacts_and_export(self) -> None:
        project = self.create_project()
        focus_session = self.start_focus_session(project, action_id="generate_prototype")
        sprintos.complete_focus_session(focus_session["focus_session_id"], outcome="Prepared the next shippable step.")
        prototype = self.generate_prototype(project, "landing_page")
        deploy_pack = self.generate_deploy_pack(project, prototype, "static")
        build_pack = self.generate_build_pack(project, prototype, deploy_pack=deploy_pack, build_target="static_app")
        workspace = self.export_workspace(project, build_pack)
        snapshot = self.create_workspace_snapshot(project, workspace)
        self.sync_workspace(project, workspace)
        verification = self.run_verification(project, verification_scope="build_pack", build_pack_id=build_pack["id"])
        release_pack = self.create_workspace_release(project, workspace, release_label="history-rc", run_checks=True)
        sprintos.add_release_feedback(project["id"], release_pack_id=release_pack["release_pack_id"], tester_label="History tester", source="manual")
        sprintos.save_release_iteration_snapshot(
            project["id"],
            release_pack["release_pack_id"],
            {
                "decision": "iterate",
                "summary": "Clarify the first-run steps.",
                "iteration_brief": "Do one tight polish pass on onboarding copy.",
                "codex_prompt": "Tighten setup instructions and preserve scope.",
                "next_tiny_action": "Rewrite the first-run instructions.",
                "feedback_count": 1,
            },
        )
        refreshed = sprintos.get_project(project["id"])
        history = refreshed["artifact_history"]
        self.assertEqual(history["groups"]["prototypes"][0]["id"], prototype["id"])
        self.assertEqual(history["groups"]["deploy_packs"][0]["id"], deploy_pack["id"])
        self.assertEqual(history["groups"]["build_packs"][0]["id"], build_pack["id"])
        self.assertEqual(history["groups"]["workspaces"][0]["id"], workspace["workspace_id"])
        self.assertEqual(history["groups"]["workspace_snapshots"][0]["id"], snapshot["snapshot_id"])
        self.assertEqual(history["groups"]["verification_runs"][0]["id"], verification["verification_run_id"])
        self.assertEqual(history["groups"]["workspace_release_packs"][0]["id"], release_pack["release_pack_id"])
        self.assertEqual(history["groups"]["focus_sessions"][0]["id"], focus_session["focus_session_id"])
        self.assertEqual(history["groups"]["release_feedback_iterations"][0]["status"], "iterate")

        server = self.start_server()
        payload = json.loads(self.http_get(server, f"/api/project_artifact_history?project_id={project['id']}&limit=999").decode("utf-8"))
        self.assertLessEqual(len(payload["groups"]["prototypes"]), 50)
        self.assertLessEqual(len(payload["groups"]["activity_events"]), 10)
        markdown = self.http_get(server, f"/api/project_artifact_history_export?project_id={project['id']}").decode("utf-8")
        self.assertIn("# Artifact History", markdown)
        self.assertIn("## Prototypes", markdown)

    def test_artifact_history_redacts_fake_api_keys(self) -> None:
        project = self.create_project()
        secret = "sk-fake-artifact-history-secret"
        sprintos.record_activity_event(
            project["id"],
            "manual_note",
            "History secret check",
            f"Authorization: Bearer {secret}",
            metadata={"openai_api_key": secret},
        )
        encoded = json.dumps(sprintos.get_project(project["id"])["artifact_history"])
        self.assertNotIn(secret, encoded)
        self.assertIn("[redacted]", encoded)

    def test_activity_timeline_ui_strings_render_in_index(self) -> None:
        self.assertIn("Activity Timeline", sprintos.INDEX_HTML)
        self.assertIn("Today Details", sprintos.INDEX_HTML)
        self.assertIn("Older Outputs", sprintos.INDEX_HTML)
        self.assertIn("Launches", sprintos.INDEX_HTML)
        self.assertIn("Build chain", sprintos.INDEX_HTML)
        self.assertIn("App Workspace", sprintos.INDEX_HTML)
        self.assertIn("Verification", sprintos.INDEX_HTML)
        self.assertIn("Release", sprintos.INDEX_HTML)
        self.assertIn("Focus", sprintos.INDEX_HTML)

    def test_command_center_summary_for_project_with_only_sprint(self) -> None:
        project = self.create_project()
        summary = sprintos.build_project_command_summary(project)
        self.assertEqual(summary["stage"], "sprint_ready")
        self.assertIn("sprint", summary["assets"])
        self.assertIn("prototype", summary["missing"])
        self.assertEqual(summary["project_id"], project["id"])

    def test_command_center_recommends_generate_prototype_when_no_prototype(self) -> None:
        project = self.create_project()
        summary = sprintos.build_project_command_summary(project)
        self.assertEqual(summary["recommended_action"]["action_id"], "start_focus_session")
        self.assertEqual(summary["recommended_action"]["source_action_id"], "generate_prototype")

    def test_command_center_recommends_run_pipeline_when_prototype_exists_but_no_build_pack(self) -> None:
        project = self.create_project()
        self.generate_prototype(project, "landing_page")
        refreshed = sprintos.get_project(project["id"])
        summary = sprintos.build_project_command_summary(refreshed)
        self.assertEqual(summary["recommended_action"]["action_id"], "start_focus_session")
        self.assertEqual(summary["recommended_action"]["source_action_id"], "run_pipeline")

    def test_command_center_recommends_export_workspace_when_build_pack_exists_but_no_workspace(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        build_pack = self.generate_build_pack(project, prototype, build_target="static_app")
        refreshed = sprintos.get_project(build_pack["project_id"])
        summary = sprintos.build_project_command_summary(refreshed)
        self.assertEqual(summary["stage_label"], "App Draft Ready")
        self.assertEqual(summary["app_state_summary"]["label"], "App Draft Ready")
        self.assertEqual(summary["recommended_action"]["action_id"], "start_focus_session")
        self.assertEqual(summary["recommended_action"]["source_action_id"], "export_workspace")
        self.assertEqual(summary["base_recommended_action"]["label"], "Prepare App for Codex")
        self.assertIn("Your app draft exists", summary["base_recommended_action"]["reason"])
        self.assertIn("App Draft Ready", summary["status_summary"])

    def test_app_state_summary_for_static_app_draft_prefers_preview(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        self.generate_build_pack(project, prototype, build_target="static_app")
        refreshed = sprintos.get_project(project["id"])
        app_state = refreshed["app_state_summary"]
        self.assertEqual(app_state["state"], "app_draft_ready")
        self.assertEqual(app_state["label"], "App Draft Ready")
        self.assertTrue(app_state["preview_url"])
        self.assertEqual(app_state["primary_action"]["label"], "Open App Preview")
        self.assertIn("Prepare App for Codex", [item["label"] for item in app_state["secondary_actions"]])

    def test_app_state_summary_shows_local_template_status_for_offline_mode(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page", generation_mode="offline")
        self.generate_build_pack(project, prototype, build_target="static_app")

        app_state = sprintos.get_project(project["id"])["app_state_summary"]

        self.assertEqual(app_state["app_generation_status"]["mode"], "local_template")
        self.assertIn("Using local template", app_state["app_generation_status"]["summary"])

    def test_app_state_summary_shows_fallback_banner_data_when_ai_falls_back(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = ""
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page", generation_mode="ai")
        self.generate_build_pack(project, prototype, build_target="static_app")

        app_state = sprintos.get_project(project["id"])["app_state_summary"]
        generation_status = app_state["app_generation_status"]

        self.assertTrue(generation_status["fallback_happened"])
        self.assertEqual(
            generation_status["fallback_message"],
            "AI app generation was unavailable, so SprintOS used the local template.",
        )
        self.assertEqual(generation_status["fallback_reason"], "offline template selected")
        self.assertEqual(generation_status["technical_fallback_reason"], "missing_openai_key")
        self.assertIn("Check AI readiness", generation_status["safe_next_actions"])
        self.assertIn("AI app generation was unavailable, so SprintOS used the local template.", sprintos.INDEX_HTML)

    def test_draft_level_test_app_is_enabled_when_artifacts_exist(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        self.generate_build_pack(project, prototype, build_target="static_app")

        app_state = sprintos.get_project(project["id"])["app_state_summary"]
        test_action = app_state["actions"]["test_app"]

        self.assertTrue(test_action["enabled"])
        self.assertEqual(test_action["label"], "Test App")
        self.assertFalse(app_state["what_exists"]["codex_workspace_available"])
        self.assertIn("Run local pass/fail checks against the latest app draft or workspace.", sprintos.INDEX_HTML)
        self.assertIn("Draft testable", sprintos.INDEX_HTML)

    def test_draft_level_verification_treats_missing_quick_launch_as_warning(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        self.generate_build_pack(project, prototype, build_target="static_app")

        verification = sprintos.run_project_verification(project["id"], verification_scope="all_latest")

        self.assertIn(verification["status"], {"partial", "passed_with_warnings", "passed"})
        self.assertTrue(any("quick launch report" in item.lower() for item in verification["warnings"]))
        self.assertFalse(any("quick launch report" in item.lower() for item in verification["blockers"]))

    def test_app_state_summary_for_python_build_pack_prefers_codex_prep(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        self.generate_build_pack(project, prototype, build_target="python_stdlib_app")
        refreshed = sprintos.get_project(project["id"])
        app_state = refreshed["app_state_summary"]
        self.assertEqual(app_state["state"], "app_draft_ready")
        self.assertEqual(app_state["primary_action"]["label"], "Prepare App for Codex")
        self.assertFalse(app_state["preview_url"])
        self.assertTrue(app_state["run_command"])
        self.assertTrue(app_state["test_command"])

    def test_command_center_recommends_create_workspace_snapshot_when_workspace_exists(self) -> None:
        project, _, _, _, _, _, _ = self.create_command_center_workspace_context(create_snapshot=False)
        summary = sprintos.build_project_command_summary(project)
        self.assertEqual(summary["recommended_action"]["action_id"], "start_focus_session")
        self.assertEqual(summary["recommended_action"]["source_action_id"], "create_workspace_snapshot")

    def test_command_center_recommends_sync_workspace_when_workspace_exists_without_sync(self) -> None:
        project, _, _, _, _, _, _ = self.create_command_center_workspace_context(create_snapshot=True, run_sync=False)
        summary = sprintos.build_project_command_summary(project)
        self.assertEqual(summary["recommended_action"]["action_id"], "start_focus_session")
        self.assertEqual(summary["recommended_action"]["source_action_id"], "sync_workspace")

    def test_command_center_recommends_run_verification_when_sync_exists_without_current_verification(self) -> None:
        project, _, _, _, _, _, _ = self.create_command_center_workspace_context(create_snapshot=True, run_sync=True, run_verification=False)
        summary = sprintos.build_project_command_summary(project)
        self.assertEqual(summary["recommended_action"]["action_id"], "start_focus_session")
        self.assertEqual(summary["recommended_action"]["source_action_id"], "run_verification")

    def test_command_center_recommends_create_release_pack_when_verification_passes(self) -> None:
        project, _, _, _, _, _, _ = self.create_command_center_workspace_context(create_snapshot=True, run_sync=True, run_verification=True)
        summary = sprintos.build_project_command_summary(project)
        self.assertEqual(summary["recommended_action"]["action_id"], "start_focus_session")
        self.assertEqual(summary["recommended_action"]["source_action_id"], "create_release_pack")

    def test_command_center_recommends_share_with_testers_when_release_is_ready(self) -> None:
        project, _, _, workspace, _, _, _ = self.create_command_center_workspace_context(create_snapshot=True, run_sync=True, run_verification=True)
        release_pack = self.create_workspace_release(project, workspace, release_label="cc-ready", run_checks=True)
        self.assertIn(release_pack["release_status"], {"ready", "ready_with_warnings"})
        refreshed = sprintos.get_project(project["id"])
        summary = sprintos.build_project_command_summary(refreshed)
        self.assertEqual(summary["recommended_action"]["action_id"], "start_focus_session")
        self.assertEqual(summary["recommended_action"]["source_action_id"], "share_with_testers")

    def test_command_center_recommends_restore_snapshot_when_verification_has_blockers(self) -> None:
        project, _, _, workspace, snapshot, _, _ = self.create_command_center_workspace_context(create_snapshot=True, run_sync=False, run_verification=False)
        self.assertIsNotNone(snapshot)
        workspace_path = Path(workspace["path"])
        (workspace_path / ".env").write_text("OPENAI_API_KEY=local-only\n", encoding="utf-8")
        self.sync_workspace(project, workspace)
        verification = self.run_verification(project, verification_scope="all_latest")
        self.assertEqual(verification["status"], "failed")
        refreshed = sprintos.get_project(project["id"])
        summary = sprintos.build_project_command_summary(refreshed)
        self.assertEqual(summary["recommended_action"]["action_id"], "start_focus_session")
        self.assertEqual(summary["recommended_action"]["source_action_id"], "restore_snapshot")

    def test_project_command_center_endpoint_returns_expected_structure(self) -> None:
        project = self.create_project()
        server = self.start_server()
        payload = json.loads(self.http_get(server, f"/api/project_command_center?project_id={project['id']}").decode("utf-8"))
        summary = payload["command_center"]
        self.assertEqual(summary["project_id"], project["id"])
        self.assertIn("recommended_action", summary)
        self.assertIn("completion_percent", summary)
        self.assertIn("chain", summary)

    def test_run_recommended_action_runs_generate_prototype_safely(self) -> None:
        project = self.create_project()
        server = self.start_server()
        payload = self.http_post_json(server, "/api/run_recommended_action", {"project_id": project["id"]})
        self.assertTrue(payload["ran"])
        self.assertEqual(payload["action_id"], "start_focus_session")
        refreshed = sprintos.get_project(project["id"])
        self.assertIsNotNone(refreshed["active_focus_session"])
        self.assertEqual(refreshed["active_focus_session"]["source_action_id"], "generate_prototype")

    def test_run_recommended_action_runs_export_workspace_safely_when_appropriate(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        self.generate_build_pack(project, prototype, build_target="static_app")
        server = self.start_server()
        payload = self.http_post_json(server, "/api/run_recommended_action", {"project_id": project["id"]})
        self.assertTrue(payload["ran"])
        self.assertEqual(payload["action_id"], "start_focus_session")
        refreshed = sprintos.get_project(project["id"])
        self.assertIsNotNone(refreshed["active_focus_session"])
        self.assertEqual(refreshed["active_focus_session"]["source_action_id"], "export_workspace")

    def test_run_recommended_action_does_not_run_non_runnable_actions(self) -> None:
        project, _, _, workspace, _, _, _ = self.create_command_center_workspace_context(create_snapshot=True, run_sync=False, run_verification=False)
        workspace_path = Path(workspace["path"])
        (workspace_path / ".env").write_text("OPENAI_API_KEY=local-only\n", encoding="utf-8")
        self.sync_workspace(project, workspace)
        self.run_verification(project, verification_scope="all_latest")
        server = self.start_server()
        payload = self.http_post_json(server, "/api/run_recommended_action", {"project_id": project["id"]})
        self.assertTrue(payload["ran"])
        self.assertEqual(payload["action_id"], "start_focus_session")
        refreshed = sprintos.get_project(project["id"])
        self.assertIsNotNone(refreshed["active_focus_session"])
        self.assertEqual(refreshed["active_focus_session"]["source_action_id"], "restore_snapshot")

    def test_project_markdown_export_includes_command_center_context(self) -> None:
        project = self.create_project()
        markdown_name, markdown = sprintos.write_markdown_export(project)
        self.assertTrue(markdown_name.endswith(".md"))
        self.assertIn("## Project Command Center", markdown)
        self.assertIn("Recommended action", markdown)

    def test_project_zip_export_includes_command_center_file(self) -> None:
        project = self.create_project()
        zip_name, payload = sprintos.build_zip_export(project)
        self.assertTrue(zip_name.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertIn("command-center.md", set(zf.namelist()))
            self.assertIn("Project Command Center", zf.read("command-center.md").decode("utf-8"))

    def test_quick_launch_endpoint_returns_command_center_summary(self) -> None:
        server = self.start_server()
        payload = self.http_post_json(
            server,
            "/api/quick_launch",
            {
                "raw_idea": "Turn one rough idea into a local testable chain.",
                "launch_goal": "codex_build_ready",
                "timebox_minutes": 120,
                "end_output": "a local testable package",
                "generation_mode": "offline",
            },
        )
        self.assertIn("command_center", payload)
        self.assertIn("current_stage", payload)
        self.assertIn("recommended_action", payload)
        self.assertIn("next_tiny_action", payload)

    def test_today_dashboard_returns_empty_state_when_no_projects_exist(self) -> None:
        summary = sprintos.build_today_dashboard_summary()
        self.assertEqual(summary["stats"]["total_projects"], 0)
        self.assertIsNone(summary["active_focus_session"])
        self.assertIsNone(summary["recommended_project"])
        self.assertEqual(summary["global_recommended_action"]["action_id"], "none")
        self.assertTrue(summary["first_run_onboarding"]["show"])
        self.assertEqual(summary["first_run_onboarding"]["secondary_cta_action"], "run_guided_demo")
        self.assertEqual(summary["setup_doctor"]["recommended_action"]["action_id"], "create_backup")

    def test_today_dashboard_detects_active_focus_session(self) -> None:
        project = self.create_project()
        focus_session = self.start_focus_session(project, action_id="generate_prototype")
        summary = sprintos.build_today_dashboard_summary()
        self.assertEqual(summary["active_focus_session"]["focus_session_id"], focus_session["focus_session_id"])
        self.assertEqual(summary["active_focus_session"]["project_id"], project["id"])

    def test_active_focus_session_becomes_top_today_dashboard_recommendation(self) -> None:
        release_project, _, _, workspace, _, _, _ = self.create_command_center_workspace_context(create_snapshot=True, run_sync=True, run_verification=True)
        self.create_workspace_release(release_project, workspace, release_label="today-rc", run_checks=True)
        focus_project = self.create_project(raw_idea="Focus on the smallest current project first.")
        self.start_focus_session(focus_project, action_id="generate_prototype")
        summary = sprintos.build_today_dashboard_summary()
        self.assertEqual(summary["recommended_project"]["project_id"], focus_project["id"])
        self.assertEqual(summary["global_recommended_action"]["action_id"], "continue_focus_session")

    def test_release_ready_project_appears_in_today_dashboard(self) -> None:
        project, _, _, workspace, _, _, _ = self.create_command_center_workspace_context(create_snapshot=True, run_sync=True, run_verification=True)
        release_pack = self.create_workspace_release(project, workspace, release_label="today-ready", run_checks=True)
        self.assertIn(release_pack["release_status"], {"ready", "ready_with_warnings"})
        summary = sprintos.build_today_dashboard_summary()
        self.assertIn(project["id"], [item["project_id"] for item in summary["release_ready_projects"]])

    def test_today_dashboard_uses_app_focused_labels(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        self.generate_build_pack(project, prototype, build_target="static_app")
        summary = sprintos.build_today_dashboard_summary()
        recommended = summary["recommended_project"]
        self.assertEqual(recommended["stage_label"], "App Draft Ready")
        self.assertIn("Prepare for Codex", [item["label"] for item in recommended["badges"]])
        self.assertEqual(summary["global_recommended_action"]["action_id"], "export_workspace")
        self.assertEqual(summary["global_recommended_action"]["label"], "Prepare App for Codex")

    def test_blocked_project_appears_in_today_dashboard(self) -> None:
        project, _, _, workspace, _, _, _ = self.create_command_center_workspace_context(create_snapshot=True, run_sync=False, run_verification=False)
        workspace_path = Path(workspace["path"])
        (workspace_path / ".env").write_text("OPENAI_API_KEY=local-only\n", encoding="utf-8")
        self.sync_workspace(project, workspace)
        self.run_verification(project, verification_scope="all_latest")
        summary = sprintos.build_today_dashboard_summary()
        self.assertIn(project["id"], [item["project_id"] for item in summary["blocked_projects"]])

    def test_recent_projects_list_is_populated(self) -> None:
        first = self.create_project(raw_idea="First recent project.")
        second = self.create_project(raw_idea="Second recent project.")
        with sprintos.db() as conn:
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", ("2099-01-01T00:00:00", second["id"]))
            conn.commit()
        summary = sprintos.build_today_dashboard_summary()
        recent_ids = [item["project_id"] for item in summary["recent_projects"]]
        self.assertIn(first["id"], recent_ids)
        self.assertEqual(recent_ids[0], second["id"])

    def test_stale_active_project_appears_in_today_dashboard(self) -> None:
        project = self.create_project(raw_idea="A stale active project.")
        stale_at = "2026-04-20T09:00:00"
        with sprintos.db() as conn:
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (stale_at, project["id"]))
            conn.commit()
        summary = sprintos.build_today_dashboard_summary()
        self.assertIn(project["id"], [item["project_id"] for item in summary["stale_projects"]])

    def test_done_and_abandoned_projects_are_not_top_recommendation_unless_active_focus_exists(self) -> None:
        active_project = self.create_project(raw_idea="Keep this active.")
        done_project = self.create_project(raw_idea="Done project.")
        abandoned_project = self.create_project(raw_idea="Abandoned project.")
        sprintos.update_project_status(done_project["id"], "done")
        sprintos.update_project_status(abandoned_project["id"], "abandoned")
        summary = sprintos.build_today_dashboard_summary()
        self.assertEqual(summary["recommended_project"]["project_id"], active_project["id"])
        self.start_focus_session(sprintos.get_project(abandoned_project["id"]), action_id="generate_prototype")
        summary = sprintos.build_today_dashboard_summary()
        self.assertEqual(summary["recommended_project"]["project_id"], abandoned_project["id"])
        self.assertEqual(summary["global_recommended_action"]["action_id"], "continue_focus_session")

    def test_today_dashboard_global_recommended_action_has_expected_shape(self) -> None:
        project = self.create_project()
        summary = sprintos.build_today_dashboard_summary()
        action = summary["global_recommended_action"]
        self.assertEqual(action["project_id"], project["id"])
        for key in ("action_id", "project_title", "label", "description", "button_label", "safe_to_run", "can_run", "expected_output", "reason"):
            self.assertIn(key, action)

    def test_today_dashboard_endpoint_returns_expected_structure(self) -> None:
        self.create_project()
        server = self.start_server()
        payload = json.loads(self.http_get(server, "/api/today_dashboard").decode("utf-8"))
        self.assertIn("generated_at", payload)
        self.assertIn("global_recommended_action", payload)
        self.assertIn("stats", payload)
        self.assertIn("recent_projects", payload)
        self.assertIn("setup_doctor", payload)
        self.assertIn("first_run_onboarding", payload)
        self.assertIn("latest_demo_run", payload)

    def test_run_today_action_delegates_safe_project_action(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        self.generate_build_pack(project, prototype, build_target="static_app")
        server = self.start_server()
        payload = self.http_post_json(server, "/api/run_today_action", {})
        self.assertTrue(payload["ran"])
        self.assertEqual(payload["action_id"], "export_workspace")
        refreshed = sprintos.get_project(project["id"])
        self.assertIsNotNone(refreshed["latest_workspace"])

    def test_run_today_action_does_not_run_non_runnable_actions(self) -> None:
        project, _, _, workspace, _, _, _ = self.create_command_center_workspace_context(create_snapshot=True, run_sync=True, run_verification=True)
        self.create_workspace_release(project, workspace, release_label="today-share", run_checks=True)
        server = self.start_server()
        payload = self.http_post_json(server, "/api/run_today_action", {})
        self.assertFalse(payload["ran"])
        self.assertEqual(payload["action_id"], "share_with_testers")
        self.assertIn("copy_text", payload)

    def test_today_dashboard_export_returns_markdown(self) -> None:
        self.create_project()
        server = self.start_server()
        payload = self.http_get(server, "/api/today_dashboard_export").decode("utf-8")
        self.assertIn("# Today Dashboard", payload)
        self.assertIn("## Global Action", payload)

    def test_project_list_badges_render_without_breaking_page(self) -> None:
        project = self.create_project()
        self.start_focus_session(project, action_id="generate_prototype")
        server = self.start_server()
        projects_payload = json.loads(self.http_get(server, "/api/projects?status=all").decode("utf-8"))
        page_html = self.http_get(server, "/").decode("utf-8")
        self.assertIn("Today / Continue", page_html)
        badges = projects_payload["projects"][0]["badges"]
        self.assertIn("active_focus", [item["id"] for item in badges])

    def test_main_page_renders_simplified_first_open_lane(self) -> None:
        server = self.start_server()
        page_html = self.http_get(server, "/").decode("utf-8")
        self.assertIn("Today / Continue", page_html)
        self.assertIn("Create App", page_html)
        self.assertIn("Advanced / Plan Only", page_html)
        self.assertIn("Projects", page_html)
        self.assertNotIn('<h3 style="margin:0">AI Status</h3>', page_html)
        self.assertIn("Start with one raw idea", page_html)
        self.assertIn("Create Sample App", page_html)
        self.assertIn("Create your first app", page_html)
        self.assertIn("homeQuickLaunchIdea", page_html)
        self.assertIn("runQuickLaunch('home')", page_html)
        self.assertIn("Create App preflight", page_html)
        self.assertNotIn("Continue an app or create one new app. Keep the first result ugly and usable.", page_html)
        self.assertNotIn("Quick Launch", page_html)

    def test_home_renderer_has_recommended_app_continue_hero_contract(self) -> None:
        project, prototype, deploy_pack, build_pack = self.create_project_with_build_pack(raw_idea="Build a tiny habit tracker app.")
        summary = sprintos.build_today_dashboard_summary()
        recommended = summary["recommended_project"]
        app_state = recommended["app_state_summary"]
        self.assertEqual(recommended["project_id"], project["id"])
        self.assertEqual(app_state["label"], "App Draft Ready")
        html = sprintos.INDEX_HTML
        self.assertIn("function renderHomeContinueHero", html)
        self.assertIn("id=\"home-continue-app\"", html)
        self.assertIn("Why SprintOS recommends it", html)
        self.assertIn("Expected output", html)
        self.assertIn("Continue This App</button>", html)
        self.assertIn("openRecommendedProject()", html)
        self.assertIn("Open App Preview", html)

    def test_home_renderer_has_first_app_create_contract(self) -> None:
        summary = sprintos.build_today_dashboard_summary()
        self.assertEqual(summary["stats"]["total_projects"], 0)
        html = sprintos.INDEX_HTML
        self.assertIn("Create your first app", html)
        self.assertIn("Paste an idea and SprintOS will create a local testable app draft.", html)
        self.assertIn('id="homeQuickLaunchIdea"', html)
        self.assertIn('class="large-idea"', html)
        self.assertIn("Create App preflight", html)
        self.assertIn("Generation mode", html)
        self.assertIn("App type", html)
        self.assertIn("Target output", html)

    def test_home_renderer_has_choose_or_create_contract_when_no_recommendation(self) -> None:
        html = sprintos.INDEX_HTML
        self.assertIn("function renderHomeCanvas", html)
        self.assertIn("if (recommended && recommended.project_id)", html)
        self.assertIn("Choose or create an app", html)
        self.assertIn("Select a project from the left or create a new app.", html)
        self.assertIn("renderHomeProjectList(projects)", html)

    def test_selected_project_main_lane_still_contains_app_command_and_focus(self) -> None:
        project, prototype, deploy_pack, build_pack = self.create_project_with_build_pack(raw_idea="Build a small selected app.")
        server = self.start_server()
        payload = json.loads(self.http_get(server, f"/api/project?id={project['id']}").decode("utf-8"))
        self.assertIn("app_state_summary", payload["project"])
        html = sprintos.INDEX_HTML
        self.assertIn("function renderAppDraftHero", html)
        self.assertIn("Project Command Center", html)
        self.assertIn("Focus Session", html)
        self.assertIn("${quickLaunchOutcomePanel}", html)
        self.assertIn("${appDraftHero}", html)

    def test_first_run_card_de_emphasizes_when_projects_exist(self) -> None:
        self.create_project()
        payload = sprintos.build_today_dashboard_summary()
        self.assertFalse(payload["first_run_onboarding"]["show"])

    def test_today_dashboard_includes_setup_doctor_status_and_ai_warning(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = ""
        payload = sprintos.build_today_dashboard_summary()
        self.assertIn("setup_doctor", payload)
        self.assertIn("status", payload["setup_doctor"])
        self.assertIn("OPENAI_API_KEY is missing", payload["ai_provider_warning"])

    def test_ui_clarity_sections_nav_and_order_render_in_main_bundle(self) -> None:
        html = sprintos.INDEX_HTML
        self.assertLess(html.index("Project Command Center"), html.index("Prepare App for Codex"))
        self.assertLess(html.index("Project Command Center"), html.index("Add Feedback"))
        self.assertLess(html.index("Project Command Center"), html.index("Test App"))
        self.assertLess(html.index("Project Command Center"), html.index("Start Focus Session"))
        for label in ("Execute", "Advanced Build Controls", "App Workspace", "Feedback", "Technical Details", "AI"):
            self.assertIn(label, html)
        for label in ("AI Provider", "AI Routing", "Create Testing Package", "Add Feedback", "Test App"):
            self.assertIn(label, html)

    def test_command_center_primary_button_uses_do_next_step_label(self) -> None:
        self.assertIn('onclick="runRecommendedAction()">Do Next Step</button>', sprintos.INDEX_HTML)

    def test_workspace_tools_use_simplified_labels(self) -> None:
        html = sprintos.INDEX_HTML
        self.assertIn("Prepare App for Codex", html)
        self.assertIn("Check App Changes", html)
        self.assertIn("Test App", html)
        self.assertIn("Older Outputs", html)

    def test_advanced_ui_still_keeps_ai_controls_and_collapsed_utilities(self) -> None:
        html = sprintos.INDEX_HTML
        self.assertIn("AI Provider", html)
        self.assertIn("AI Routing", html)
        self.assertIn("Reports And Exports", html)
        self.assertIn("function renderDetailsBlock", html)

    def test_quick_launch_updates_today_dashboard(self) -> None:
        quick_launch = self.generate_quick_launch(raw_idea="Quick launch a new dashboard-aware project.")
        summary = sprintos.build_today_dashboard_summary()
        self.assertEqual(summary["stats"]["quick_launch_count"], 1)
        self.assertIn(quick_launch["project_id"], [item["project_id"] for item in summary["recent_projects"]])

    def test_focus_session_updates_today_dashboard(self) -> None:
        project = self.create_project(raw_idea="Focus sessions should appear globally.")
        self.start_focus_session(project, action_id="generate_prototype")
        summary = sprintos.build_today_dashboard_summary()
        self.assertEqual(summary["active_focus_session"]["project_id"], project["id"])
