import io
import importlib.util
import json
import os
import subprocess
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional
from unittest import mock

import scripts.health as health
import sprintos
from sprintos_core.ai_costs import estimate_ai_cost, estimate_tokens_from_chars
from sprintos_core.ai_provider import (
    DEFAULT_DEEPSEEK_BASE_URL,
    DEFAULT_DEEPSEEK_MODEL,
    DEFAULT_OPENAI_MODEL,
    ai_enabled,
    call_deepseek_chat_completions,
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


class _MovedDashboardFlowTests:
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmpdir.name)
        self.servers = []
        self.original_paths = (
            sprintos.DATA_DIR,
            sprintos.EXPORT_DIR,
            sprintos.WORKFLOW_DIR,
            sprintos.DB_PATH,
            sprintos.WORKSPACE_DIR,
        )
        self.original_cwd = Path.cwd()
        self.original_env = {
            "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
            "DEEPSEEK_API_KEY": os.environ.get("DEEPSEEK_API_KEY"),
            "DEEPSEEK_BASE_URL": os.environ.get("DEEPSEEK_BASE_URL"),
            "SPRINTOS_AI_PROVIDER": os.environ.get("SPRINTOS_AI_PROVIDER"),
            "SPRINTOS_AI_ENABLED": os.environ.get("SPRINTOS_AI_ENABLED"),
            "SPRINTOS_MODEL": os.environ.get("SPRINTOS_MODEL"),
            "SPRINTOS_AI_TIMEOUT_SECONDS": os.environ.get("SPRINTOS_AI_TIMEOUT_SECONDS"),
            "SPRINTOS_AI_MAX_OUTPUT_TOKENS": os.environ.get("SPRINTOS_AI_MAX_OUTPUT_TOKENS"),
            "SPRINTOS_OPENAI_INPUT_COST_PER_1M": os.environ.get("SPRINTOS_OPENAI_INPUT_COST_PER_1M"),
            "SPRINTOS_OPENAI_OUTPUT_COST_PER_1M": os.environ.get("SPRINTOS_OPENAI_OUTPUT_COST_PER_1M"),
            "SPRINTOS_DEEPSEEK_INPUT_COST_PER_1M": os.environ.get("SPRINTOS_DEEPSEEK_INPUT_COST_PER_1M"),
            "SPRINTOS_DEEPSEEK_OUTPUT_COST_PER_1M": os.environ.get("SPRINTOS_DEEPSEEK_OUTPUT_COST_PER_1M"),
        }

        sprintos.DATA_DIR = self.root / "data"
        sprintos.EXPORT_DIR = self.root / "exports"
        sprintos.WORKFLOW_DIR = self.root / "workflows"
        sprintos.DB_PATH = sprintos.DATA_DIR / "sprintos.sqlite"
        sprintos.WORKSPACE_DIR = self.root / "workspaces"
        os.chdir(self.root)
        os.environ["OPENAI_API_KEY"] = ""
        os.environ["DEEPSEEK_API_KEY"] = ""
        os.environ["DEEPSEEK_BASE_URL"] = DEFAULT_DEEPSEEK_BASE_URL
        os.environ["SPRINTOS_AI_PROVIDER"] = "offline"
        os.environ["SPRINTOS_AI_ENABLED"] = "false"
        os.environ["SPRINTOS_MODEL"] = DEFAULT_OPENAI_MODEL
        os.environ["SPRINTOS_AI_TIMEOUT_SECONDS"] = "20"
        os.environ["SPRINTOS_AI_MAX_OUTPUT_TOKENS"] = "2000"
        os.environ.pop("SPRINTOS_OPENAI_INPUT_COST_PER_1M", None)
        os.environ.pop("SPRINTOS_OPENAI_OUTPUT_COST_PER_1M", None)
        os.environ.pop("SPRINTOS_DEEPSEEK_INPUT_COST_PER_1M", None)
        os.environ.pop("SPRINTOS_DEEPSEEK_OUTPUT_COST_PER_1M", None)

        sprintos.ensure_dirs()
        sprintos.write_default_workflows()
        sprintos.init_db()

    def tearDown(self) -> None:
        for server in self.servers:
            server.shutdown()
            server.server_close()
        sprintos.DATA_DIR, sprintos.EXPORT_DIR, sprintos.WORKFLOW_DIR, sprintos.DB_PATH, sprintos.WORKSPACE_DIR = self.original_paths
        os.chdir(self.original_cwd)
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmpdir.cleanup()

    def create_project(
        self,
        raw_idea: str = "Build a local tool that turns messy notes into a small execution sprint.",
        workflow: str = "software_mvp",
        timebox: int = 120,
        energy: str = "high",
        desired_output: str = "a local working prototype",
    ):
        sprint = sprintos.generate_sprint(raw_idea, workflow, timebox, energy, desired_output)
        pid = sprintos.save_project(raw_idea, sprint["_workflow_id"], timebox, energy, desired_output, sprint)
        project = sprintos.get_project(pid)
        self.assertIsNotNone(project)
        return project

    def generate_prototype(self, project=None, prototype_type: str = "landing_page", generation_mode: str = "auto"):
        project = project or self.create_project()
        prototype = sprintos.write_prototype_package(project, prototype_type, generation_mode=generation_mode)
        self.assertIsNotNone(prototype)
        return prototype

    def generate_deploy_pack(self, project=None, prototype=None, hosting_target: str = "static"):
        project = project or self.create_project()
        prototype = prototype or self.generate_prototype(project)
        deploy_pack = sprintos.write_deploy_pack(project, prototype, hosting_target)
        self.assertIsNotNone(deploy_pack)
        return deploy_pack

    def generate_build_pack(self, project=None, prototype=None, deploy_pack=None, build_target: str = "static_app"):
        project = project or self.create_project()
        prototype = prototype or self.generate_prototype(project)
        build_pack = sprintos.write_build_pack(project, prototype, build_target, deploy_pack=deploy_pack)
        self.assertIsNotNone(build_pack)
        return build_pack

    def export_workspace(self, project=None, build_pack=None):
        build_pack = build_pack or self.generate_build_pack(project)
        project = project or sprintos.get_project(build_pack["project_id"]) or self.create_project()
        workspace = sprintos.write_workspace_export(project, build_pack)
        self.assertIsNotNone(workspace)
        return workspace

    def sync_workspace(self, project=None, workspace=None, run_checks: bool = True):
        workspace = workspace or self.export_workspace(project)
        project = project or sprintos.get_project(workspace["project_id"]) or self.create_project()
        workspace_sync = sprintos.run_workspace_sync(
            project["id"],
            workspace_id=workspace["workspace_id"],
            run_checks=run_checks,
        )
        self.assertIsNotNone(workspace_sync)
        return workspace_sync

    def create_workspace_release(self, project=None, workspace=None, release_label: str = "rc-1", run_checks: bool = True):
        workspace = workspace or self.export_workspace(project)
        project = project or sprintos.get_project(workspace["project_id"]) or self.create_project()
        release_pack = sprintos.create_workspace_release_pack(
            project["id"],
            workspace_id=workspace["workspace_id"],
            release_label=release_label,
            run_checks=run_checks,
        )
        self.assertIsNotNone(release_pack)
        return release_pack

    def create_workspace_snapshot(self, project=None, workspace=None, snapshot_label: str = "manual-snapshot"):
        workspace = workspace or self.export_workspace(project)
        project = project or sprintos.get_project(workspace["project_id"]) or self.create_project()
        snapshot = sprintos.create_workspace_snapshot(
            project["id"],
            workspace_id=workspace["workspace_id"],
            snapshot_label=snapshot_label,
        )
        self.assertIsNotNone(snapshot)
        return snapshot

    def restore_workspace_snapshot(self, snapshot=None):
        snapshot = snapshot or self.create_workspace_snapshot()
        restore = sprintos.restore_workspace_snapshot(snapshot["snapshot_id"])
        self.assertIsNotNone(restore)
        return restore

    def compare_workspace_snapshot(self, workspace=None, snapshot=None):
        snapshot = snapshot or self.create_workspace_snapshot(workspace=workspace)
        workspace = workspace or sprintos.get_workspace(snapshot["workspace_id"], include_prompt=True)
        comparison = sprintos.compare_workspace_to_snapshot(workspace["workspace_id"], snapshot["snapshot_id"])
        self.assertIsNotNone(comparison)
        return comparison

    def generate_pipeline(
        self,
        project=None,
        pipeline_goal: str = "codex_build_ready",
        prototype_type: str = "",
        hosting_target: str = "",
        build_target: str = "",
        generation_mode: str = "auto",
    ):
        project = project or self.create_project()
        pipeline_run = sprintos.run_testable_pipeline(
            project_id=project["id"],
            pipeline_goal=pipeline_goal,
            prototype_type=prototype_type,
            hosting_target=hosting_target,
            build_target=build_target,
            generation_mode=generation_mode,
        )
        self.assertIsNotNone(pipeline_run)
        return pipeline_run

    def generate_quick_launch(
        self,
        raw_idea: str = "Build a local tool that turns one messy idea into a testable package fast.",
        launch_goal: str = "codex_build_ready",
        timebox_minutes: int = 120,
        energy_level: str = "medium",
        end_output: str = "a testable local package",
        prototype_type: str = "auto",
        hosting_target: str = "static",
        build_target: str = "auto",
        generation_mode: str = "auto",
    ):
        quick_launch = sprintos.run_quick_launch(
            raw_idea=raw_idea,
            launch_goal=launch_goal,
            timebox_minutes=timebox_minutes,
            energy_level=energy_level,
            end_output=end_output,
            prototype_type=prototype_type,
            hosting_target=hosting_target,
            build_target=build_target,
            generation_mode=generation_mode,
        )
        self.assertIsNotNone(quick_launch)
        return quick_launch

    def run_verification(
        self,
        project=None,
        verification_scope: str = "all_latest",
        **ids,
    ):
        project = project or self.create_project()
        verification = sprintos.run_project_verification(
            project["id"],
            verification_scope=verification_scope,
            prototype_id=ids.get("prototype_id"),
            deploy_pack_id=ids.get("deploy_pack_id"),
            build_pack_id=ids.get("build_pack_id"),
            pipeline_run_id=ids.get("pipeline_run_id"),
            quick_launch_id=ids.get("quick_launch_id"),
        )
        self.assertIsNotNone(verification)
        return verification

    def start_focus_session(self, project=None, timebox_minutes: int = 30, action_id=None):
        project = project or self.create_project()
        focus_session = sprintos.create_focus_session(project["id"], timebox_minutes, action_id=action_id)
        self.assertIsNotNone(focus_session)
        return focus_session

    def list_activity(self, project_id: Optional[str] = None, limit: int = 50):
        if project_id:
            return sprintos.get_project_timeline(project_id, limit=limit)
        return sprintos.get_global_activity(limit=limit)

    def generate_full_chain(self):
        project = self.create_project()
        project = sprintos.generate_and_store_resume_plan(project["id"])
        prototype = self.generate_prototype(project, "landing_page")
        sprintos.add_feedback_entry(
            project["id"],
            prototype_id=prototype["id"],
            tester_label="Fixture tester",
            source="manual",
            rating=4,
            pain_level=3,
            would_use="yes",
            would_pay="maybe",
            confusing_parts="The first action is slightly unclear.",
            missing_features="A tighter result summary.",
            favorite_part="The small, local-first scope.",
            freeform_feedback="This is enough to catch obvious regressions.",
        )
        project = sprintos.get_project(project["id"])
        self.assertIsNotNone(project)
        summary = sprintos.build_iteration_summary(project, prototype["id"])
        iteration = sprintos.save_iteration_snapshot(project["id"], prototype["id"], summary)
        project = sprintos.get_project(project["id"])
        self.assertIsNotNone(project)
        deploy_pack = self.generate_deploy_pack(project, prototype, "static")
        build_pack = self.generate_build_pack(project, prototype, deploy_pack=deploy_pack, build_target="static_app")
        pipeline_run = self.generate_pipeline(project, pipeline_goal="codex_build_ready")
        verification = self.run_verification(project, verification_scope="pipeline", pipeline_run_id=pipeline_run["pipeline_run_id"])
        markdown_name, markdown = sprintos.write_markdown_export(project)
        zip_name, zip_payload = sprintos.build_zip_export(project)
        quick_launch = self.generate_quick_launch(
            raw_idea="Turn one rough local product idea into a testable package with a clear next Codex step.",
            launch_goal="codex_build_ready",
            prototype_type="auto",
            hosting_target="static",
            build_target="auto",
        )
        quick_launch_project = sprintos.get_project(quick_launch["project_id"])
        self.assertIsNotNone(quick_launch_project)
        quick_launch_verification = self.run_verification(quick_launch_project, verification_scope="all_latest")
        return {
            "project": project,
            "prototype": prototype,
            "iteration": iteration,
            "deploy_pack": deploy_pack,
            "build_pack": build_pack,
            "pipeline_run": pipeline_run,
            "verification": verification,
            "quick_launch_project": quick_launch_project,
            "quick_launch_verification": quick_launch_verification,
            "markdown_name": markdown_name,
            "markdown": markdown,
            "zip_name": zip_name,
            "zip_payload": zip_payload,
            "quick_launch": quick_launch,
        }

    def sample_feedback_payload(self, project, prototype=None, **overrides):
        prototype = prototype or project.get("latest_prototype")
        payload = {
            "project_id": project["id"],
            "prototype_id": prototype["id"] if prototype else None,
            "tester_label": "Tester 1",
            "source": "manual",
            "rating": 4,
            "pain_level": 4,
            "would_use": "yes",
            "would_pay": "maybe",
            "confusing_parts": "The first step is not obvious.",
            "missing_features": "A clearer result preview.",
            "favorite_part": "The focused scope.",
            "freeform_feedback": "Promising, but the main CTA needs to be clearer.",
            "raw_json": "",
        }
        payload.update(overrides)
        return payload

    def sample_release_feedback_payload(self, project, release_pack=None, **overrides):
        release_pack = release_pack or project.get("latest_workspace_release_pack")
        payload = {
            "project_id": project["id"],
            "release_pack_id": release_pack["release_pack_id"] if release_pack else None,
            "tester_label": "Release Tester 1",
            "source": "manual",
            "rating": 4,
            "would_use": "yes",
            "would_pay": "maybe",
            "confusing_parts": "The first screen needs a clearer starting point.",
            "missing_features": "A stronger result summary.",
            "favorite_part": "The local-only workflow.",
            "bug_report": "",
            "freeform_feedback": "Feels close; one more pass would help.",
            "raw_json": "",
        }
        payload.update(overrides)
        return payload

    def create_command_center_workspace_context(
        self,
        *,
        build_target: str = "static_app",
        prototype_type: str = "landing_page",
        create_snapshot: bool = False,
        run_sync: bool = False,
        run_verification: bool = False,
    ):
        project = self.create_project()
        prototype = self.generate_prototype(project, prototype_type)
        deploy_pack = self.generate_deploy_pack(project, prototype, "static") if build_target == "static_app" else None
        build_pack = self.generate_build_pack(project, prototype, deploy_pack=deploy_pack, build_target=build_target)
        workspace = self.export_workspace(project, build_pack)
        snapshot = self.create_workspace_snapshot(project, workspace) if create_snapshot else None
        workspace_sync = self.sync_workspace(project, workspace) if run_sync else None
        verification = self.run_verification(project, verification_scope="build_pack", build_pack_id=build_pack["id"]) if run_verification else None
        refreshed = sprintos.get_project(project["id"])
        self.assertIsNotNone(refreshed)
        return refreshed, prototype, build_pack, workspace, snapshot, workspace_sync, verification

    def test_activity_events_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertIn("activity_events", tables)

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

    def test_activity_timeline_ui_strings_render_in_index(self) -> None:
        self.assertIn("Activity Timeline", sprintos.INDEX_HTML)
        self.assertIn("Today Details", sprintos.INDEX_HTML)
        self.assertIn("Older Outputs", sprintos.INDEX_HTML)

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
        self.assertEqual(summary["recommended_action"]["action_id"], "start_focus_session")
        self.assertEqual(summary["recommended_action"]["source_action_id"], "export_workspace")
        self.assertEqual(summary["base_recommended_action"]["label"], "Prepare App for Codex")
        self.assertIn("Your app draft exists", summary["base_recommended_action"]["reason"])

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
        self.assertIn("Create your first app", page_html)
        self.assertIn("homeQuickLaunchIdea", page_html)
        self.assertIn("runQuickLaunch('home')", page_html)
        self.assertIn("Create App preflight", page_html)
        self.assertNotIn("Continue an app or create one new app. Keep the first result ugly and usable.", page_html)
        self.assertNotIn('<h3 style="margin:0">AI Status</h3>', page_html)
        self.assertNotIn("Quick Launch", page_html)

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

    def start_server(self):
        server = sprintos.ThreadingHTTPServer(("127.0.0.1", 0), sprintos.SprintOSHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append(server)
        return server

    def ai_fixture_dir(self) -> Path:
        return Path(__file__).resolve().parent / "fixtures" / "ai_quality"

    def read_ai_fixture_text(self, name: str) -> str:
        return (self.ai_fixture_dir() / name).read_text(encoding="utf-8").strip()

    def read_ai_fixture_json(self, name: str):
        return json.loads((self.ai_fixture_dir() / name).read_text(encoding="utf-8"))

    def http_get(self, server, path: str) -> bytes:
        url = f"http://127.0.0.1:{server.server_address[1]}{path}"
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.read()

    def http_post_json(self, server, path: str, payload):
        url = f"http://127.0.0.1:{server.server_address[1]}{path}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))


class _MovedCoreHelperTests:
    def test_safe_slug_generation_is_stable(self) -> None:
        self.assertEqual(sprintos.slugify("  Hello, SprintOS!  "), "hello-sprintos")
        self.assertEqual(sprintos.slugify("///", default="fallback"), "fallback")

    def test_filename_sanitization_blocks_path_segments_and_bad_suffixes(self) -> None:
        self.assertEqual(sprintos.sanitize_filename("../Bad Name!!.md"), "bad-name.md")
        self.assertEqual(sprintos.sanitize_filename("nested/folder/Project Plan.EXE"), "project-plan.exe")


class _MovedAIProviderTests:
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
            input_text="Return {\"status\":\"ok\"}",
            instructions="Return JSON only.",
            config=config,
            response_format={"type": "json_object"},
            transport=transport,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.parsed_json, {"status": "ok"})
        self.assertEqual(result.provider, "deepseek")

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
        self.assertIn("missing required fields", provider.error.lower())

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


class _MovedAIQualityLayerTests:
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
            os.environ["SPRINTOS_MODEL"] = DEFAULT_OPENAI_MODEL

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
            model_name = str(getattr(config, "model", os.environ.get("SPRINTOS_MODEL", DEFAULT_OPENAI_MODEL)) or DEFAULT_OPENAI_MODEL)
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


class _MovedAIProviderSecurityAndOfflineTests:
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
        self.assertEqual(payload["provider"], "openai")

    def test_ai_status_endpoint_never_returns_deepseek_api_key(self) -> None:
        secret = "sk" + "-deepseek-secret-value"
        os.environ["SPRINTOS_AI_PROVIDER"] = "deepseek"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["DEEPSEEK_API_KEY"] = secret
        server = self.start_server()

        payload = json.loads(self.http_get(server, "/api/ai_status").decode("utf-8"))

        encoded = json.dumps(payload)
        self.assertNotIn(secret, encoded)
        self.assertEqual(payload["provider"], "deepseek")
        self.assertEqual(payload["base_url"], DEFAULT_DEEPSEEK_BASE_URL)
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
            ),
        ):
            payload = self.http_post_json(server, "/api/test_ai_provider", {})

        encoded = json.dumps(payload)
        self.assertNotIn("OPENAI_API_KEY", encoded)
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
        secret = "sk" + "-test-export-secret"
        os.environ["OPENAI_API_KEY"] = secret
        project = self.create_project()

        _, markdown = sprintos.write_markdown_export(project)
        _, payload = sprintos.build_zip_export(project)

        self.assertNotIn(secret, markdown)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for name in zf.namelist():
                text = zf.read(name).decode("utf-8", errors="ignore")
                self.assertNotIn(secret, text, name)

    def test_exports_do_not_contain_fake_deepseek_key_values(self) -> None:
        secret = "sk" + "-test-deepseek-export-secret"
        os.environ["DEEPSEEK_API_KEY"] = secret
        project = self.create_project()

        _, markdown = sprintos.write_markdown_export(project)
        _, payload = sprintos.build_zip_export(project)

        self.assertNotIn(secret, markdown)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for name in zf.namelist():
                text = zf.read(name).decode("utf-8", errors="ignore")
                self.assertNotIn(secret, text, name)

    def test_health_secret_scan_catches_obvious_hardcoded_key_patterns(self) -> None:
        secret = "sk" + "-test-secret"
        export_secret = "sk" + "-export-ignore"
        root = self.root / "health_root"
        (root / "scripts").mkdir(parents=True)
        (root / "docs").mkdir(parents=True)
        (root / "tests").mkdir(parents=True)
        (root / "sprintos_core").mkdir(parents=True)
        (root / "exports").mkdir(parents=True)
        (root / "data").mkdir(parents=True)
        for path in (
            root / "AGENTS.md",
            root / "docs" / "ARCHITECTURE.md",
            root / "docs" / "CODEX_TASKS.md",
            root / "docs" / "CODE_REVIEW.md",
            root / "sprintos.py",
            root / "tests" / "test_sprintos.py",
            root / "scripts" / "smoke.py",
        ):
            path.write_text("placeholder\n", encoding="utf-8")
        (root / "sprintos_core" / "ai_provider.py").write_text(f'OPENAI_API_KEY="{secret}"\n', encoding="utf-8")
        (root / "exports" / "ignored.py").write_text(f'OPENAI_API_KEY="{export_secret}"\n', encoding="utf-8")

        with mock.patch.object(health, "ROOT", root):
            findings = health.scan_for_secrets()

        self.assertTrue(any("sprintos_core/ai_provider.py" in item for item in findings))
        self.assertFalse(any("exports/ignored.py" in item for item in findings))

    def test_health_secret_scan_ignores_blank_env_example(self) -> None:
        root = self.root / "health_blank_env"
        (root / "scripts").mkdir(parents=True)
        (root / "docs").mkdir(parents=True)
        (root / "tests").mkdir(parents=True)
        (root / "sprintos_core").mkdir(parents=True)
        (root / "exports").mkdir(parents=True)
        (root / "data").mkdir(parents=True)
        for path in (
            root / "AGENTS.md",
            root / "docs" / "ARCHITECTURE.md",
            root / "docs" / "CODEX_TASKS.md",
            root / "docs" / "CODE_REVIEW.md",
            root / "sprintos.py",
            root / "tests" / "test_sprintos.py",
            root / "scripts" / "smoke.py",
        ):
            path.write_text("placeholder\n", encoding="utf-8")
        (root / ".env.example").write_text("OPENAI_API_KEY=\nDEEPSEEK_API_KEY=\n", encoding="utf-8")

        with mock.patch.object(health, "ROOT", root):
            findings = health.scan_for_secrets()

        self.assertEqual(findings, [])

    def test_health_secret_scan_catches_obvious_hardcoded_deepseek_key_pattern(self) -> None:
        secret = "sk" + "-test-deepseek-secret"
        root = self.root / "health_deepseek_root"
        (root / "scripts").mkdir(parents=True)
        (root / "docs").mkdir(parents=True)
        (root / "tests").mkdir(parents=True)
        (root / "sprintos_core").mkdir(parents=True)
        (root / "exports").mkdir(parents=True)
        (root / "data").mkdir(parents=True)
        for path in (
            root / "AGENTS.md",
            root / "docs" / "ARCHITECTURE.md",
            root / "docs" / "CODEX_TASKS.md",
            root / "docs" / "CODE_REVIEW.md",
            root / "sprintos.py",
            root / "tests" / "test_sprintos.py",
            root / "scripts" / "smoke.py",
        ):
            path.write_text("placeholder\n", encoding="utf-8")
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
        payload = build_zip_from_pairs(
            [
                ("a.txt", "alpha"),
                ("folder/b.txt", "beta"),
            ]
        )

        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertEqual(set(zf.namelist()), {"a.txt", "folder/b.txt"})
            self.assertEqual(zf.read("folder/b.txt").decode("utf-8"), "beta")

    def test_external_network_marker_detection_ignores_localhost_and_flags_remote_urls(self) -> None:
        markers = external_network_markers(
            "app.js",
            'fetch("https://example.com/api");\nconst ok = "http://127.0.0.1:8000";\n',
        )

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
        self.assertEqual(
            safe_flat_file_path(first, "report.md", ("report.md",), "Invalid report file").read_text(encoding="utf-8"),
            "ok",
        )
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


class _MovedAIRoutingTests:
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
            self.http_post_json(
                server,
                "/api/ai_route",
                {"task_name": "bad_task", "generation_mode": "ai", "provider": "openai", "enabled": True},
            )

    def test_post_ai_route_rejects_invalid_provider(self) -> None:
        server = self.start_server()
        with self.assertRaises(urllib.error.HTTPError):
            self.http_post_json(
                server,
                "/api/ai_route",
                {"task_name": "sprint_generation", "generation_mode": "ai", "provider": "weird", "enabled": True},
            )

    def test_post_ai_route_rejects_invalid_generation_mode(self) -> None:
        server = self.start_server()
        with self.assertRaises(urllib.error.HTTPError):
            self.http_post_json(
                server,
                "/api/ai_route",
                {"task_name": "sprint_generation", "generation_mode": "sometimes", "provider": "openai", "enabled": True},
            )

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
        self.assertEqual(resolution["resolved_model"], DEFAULT_OPENAI_MODEL)

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
        self.assertEqual(item["resolved_provider"], "openai")
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
        self.assertEqual(sprint["resolved_model"], "deepseek-v4-flash")

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
        self.assertEqual(prototype["metadata"]["resolved_model"], "deepseek-v4-flash")

    def test_quick_launch_summary_metadata_includes_resolved_route_fields(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "offline"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["DEEPSEEK_API_KEY"] = "sk-route-deepseek"
        sprintos.save_ai_route("quick_launch_summary", "ai", "deepseek", model="deepseek-v4-flash", enabled=True)

        with mock.patch("sprintos_core.ai_provider.call_deepseek_chat_completions", side_effect=self.provider_side_effect()):
            quick_launch = self.generate_quick_launch(generation_mode="auto")

        self.assertTrue(quick_launch["metadata"]["route_used"])
        self.assertEqual(quick_launch["metadata"]["resolved_provider"], "deepseek")
        self.assertEqual(quick_launch["metadata"]["resolved_model"], "deepseek-v4-flash")

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
        self.assertIn("generation_mode_requested", item)

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


class _MovedAIProviderComparisonTests:
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
                "task_name": "codex_handoff",
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
                "metadata": {"note": secret},
            }
        )
        project = self.create_project()
        _, markdown = sprintos.write_markdown_export(project)
        zip_name, payload = sprintos.build_zip_export(project)
        self.assertNotIn(secret, markdown)
        self.assertTrue(zip_name.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("ai-provider-evals.md", names)
            self.assertIn("ai-route-recommendations.md", names)
            self.assertNotIn(secret, zf.read("ai-provider-evals.md").decode("utf-8"))
            self.assertNotIn(secret, zf.read("ai-route-recommendations.md").decode("utf-8"))


class _MovedCodexHandoffTests:
    def test_codex_handoff_generation_is_specific_and_repo_aware(self) -> None:
        project = self.create_project()
        handoff = project["sprint"]["codex_handoff"]

        self.assertEqual(handoff["filename"], "codex-task.md")
        self.assertIn("## Objective", handoff["content"])
        self.assertIn("## Context", handoff["content"])
        self.assertIn("## Constraints", handoff["content"])
        self.assertIn("## Files Likely Touched", handoff["content"])
        self.assertIn("## Acceptance Criteria", handoff["content"])
        self.assertIn("## Verification Commands", handoff["content"])
        self.assertIn("## Review Checklist", handoff["content"])
        self.assertIn("## Risks / Non-Goals", handoff["content"])
        self.assertIn("Project status: active", handoff["content"])
        self.assertIn("Next tiny action:", handoff["content"])
        self.assertIn("Do not overbuild.", handoff["content"])
        self.assertIn("Preserve existing behavior", handoff["content"])
        self.assertIn("python3 -m unittest", handoff["content"])
        self.assertIn("python3 scripts/smoke.py", handoff["content"])

        artifact_names = [artifact["filename"] for artifact in project["sprint"]["artifacts"]]
        self.assertIn("codex-task.md", artifact_names)

    def test_markdown_export_includes_codex_handoff(self) -> None:
        project = self.create_project()
        filename, markdown = sprintos.write_markdown_export(project)

        self.assertTrue((sprintos.EXPORT_DIR / filename).exists())
        self.assertIn("**Status:** active", markdown)
        self.assertIn("## Resume Mode", markdown)
        self.assertIn("## Codex Handoff", markdown)
        self.assertIn("`codex-task.md`", markdown)
        self.assertIn("python3 -m unittest", markdown)
        self.assertIn("# Artifacts", markdown)

    def test_zip_export_contains_handoff_and_sanitized_artifacts(self) -> None:
        project = self.create_project()
        project["sprint"]["artifacts"][0]["filename"] = "../Bad Name!!.md"

        filename, payload = sprintos.build_zip_export(project)

        self.assertTrue(filename.endswith(".zip"))
        self.assertTrue((sprintos.EXPORT_DIR / filename).exists())

        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("sprint.md", names)
            self.assertIn("codex-task.md", names)
            self.assertIn("resume.md", names)
            self.assertIn("bad-name.md", names)
            self.assertNotIn("../Bad Name!!.md", names)
            handoff_text = zf.read("codex-task.md").decode("utf-8")
            self.assertIn("Codex Task Brief", handoff_text)
            resume_text = zf.read("resume.md").decode("utf-8")
            self.assertIn("Resume Mode", resume_text)

    def test_existing_sprint_generation_still_returns_primary_artifacts(self) -> None:
        project = self.create_project(
            raw_idea="I want to validate a small landing page offer for a local AI sprint planning service.",
            workflow="business_validation",
            timebox=60,
            energy="medium",
            desired_output="one simple offer page",
        )

        sprint = project["sprint"]
        self.assertTrue(sprint["sprint_plan"])
        self.assertTrue(sprint["done_definition"])
        regular = sprintos.regular_artifacts(sprint)
        self.assertGreaterEqual(len(regular), 2)
        self.assertIn("validation-plan.md", [artifact["filename"] for artifact in regular])


class _MovedProjectStateTests:
    def test_existing_projects_without_status_default_to_active(self) -> None:
        sprint = sprintos.generate_sprint(
            "Resume a half-finished local prototype without losing context.",
            "resume_project",
            60,
            "medium",
            "a clear restart path",
        )
        project_id = "legacy-project"
        created_at = sprintos.now_iso()

        with sprintos.db() as conn:
            conn.execute("DROP TABLE projects")
            conn.execute(
                """
                CREATE TABLE projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    raw_idea TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    timebox_minutes INTEGER NOT NULL,
                    energy TEXT NOT NULL,
                    desired_output TEXT,
                    sprint_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                INSERT INTO projects (id, title, raw_idea, workflow_id, timebox_minutes, energy, desired_output, sprint_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    sprint["title"],
                    "Resume a half-finished local prototype without losing context.",
                    sprint["_workflow_id"],
                    60,
                    "medium",
                    "a clear restart path",
                    json.dumps(sprint),
                    created_at,
                    created_at,
                ),
            )
            conn.commit()

        sprintos.init_db()
        project = sprintos.get_project(project_id)
        self.assertIsNotNone(project)
        self.assertEqual(project["status"], "active")
        self.assertEqual(sprintos.list_projects()[0]["status"], "active")

    def test_new_projects_persist_status(self) -> None:
        project = self.create_project()
        self.assertEqual(project["status"], "active")
        with sprintos.db() as conn:
            row = conn.execute("SELECT status FROM projects WHERE id = ?", (project["id"],)).fetchone()
        self.assertEqual(row["status"], "active")

    def test_status_can_be_changed_and_reloaded(self) -> None:
        project = self.create_project()
        updated = sprintos.update_project_state(project["id"], status="parked")
        self.assertEqual(updated["status"], "parked")
        reloaded = sprintos.get_project(project["id"])
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["status"], "parked")
        filtered = sprintos.list_projects("parked")
        self.assertEqual([item["id"] for item in filtered], [project["id"]])


class _MovedResumeModeTests:
    def test_resume_plan_generation_contains_required_sections(self) -> None:
        project = self.create_project()
        updated = sprintos.generate_and_store_resume_plan(project["id"])
        plan = updated["sprint"]["resume_plan"]

        self.assertTrue(plan["recap"])
        self.assertTrue(plan["next_tiny_action"])
        self.assertTrue(plan["restart_15"])
        self.assertTrue(plan["restart_30"])
        self.assertTrue(plan["not_to_do"])
        self.assertTrue(plan["done_definition"])
        self.assertIn("Minute 0-5", plan["restart_15"])
        self.assertIn("Minute 0-10", plan["restart_30"])

    def test_markdown_export_includes_resume_context(self) -> None:
        project = self.create_project()
        sprintos.add_progress_note(project["id"], "Stopped after drafting the first artifact.")
        updated = sprintos.generate_and_store_resume_plan(project["id"])
        _, markdown = sprintos.write_markdown_export(updated)

        self.assertIn("## Resume Mode", markdown)
        self.assertIn("Resume summary", markdown)
        self.assertIn("Current blocker", markdown)
        self.assertIn("Next tiny action", markdown)
        self.assertIn("Stopped after drafting the first artifact.", markdown)
        self.assertIn("## Codex Handoff", markdown)

    def test_zip_export_includes_resume_markdown(self) -> None:
        project = self.create_project()
        updated = sprintos.generate_and_store_resume_plan(project["id"])
        _, payload = sprintos.build_zip_export(updated)

        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("resume.md", names)
            resume_text = zf.read("resume.md").decode("utf-8")
            self.assertIn("Suggested Restart Sprint", resume_text)


class _MovedFocusSessionTests:
    def test_focus_sessions_table_creation(self) -> None:
        with sprintos.db() as conn:
            tables = {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
        self.assertIn("focus_sessions", tables)

    def test_start_focus_session_from_command_center_recommended_action(self) -> None:
        project = self.create_project()
        focus_session = self.start_focus_session(project, 30)
        self.assertEqual(focus_session["source_action_id"], "generate_prototype")

    def test_start_focus_session_rejects_invalid_timebox(self) -> None:
        project = self.create_project()
        with self.assertRaises(ValueError):
            sprintos.create_focus_session(project["id"], 45)

    def test_start_focus_session_persists_active_status(self) -> None:
        project = self.create_project()
        focus_session = self.start_focus_session(project, 15)
        with sprintos.db() as conn:
            row = conn.execute("SELECT session_status, timebox_minutes FROM focus_sessions WHERE id = ?", (focus_session["focus_session_id"],)).fetchone()
        self.assertEqual(row["session_status"], "active")
        self.assertEqual(row["timebox_minutes"], 15)

    def test_project_hydration_includes_active_focus_session(self) -> None:
        project = self.create_project()
        focus_session = self.start_focus_session(project)
        refreshed = sprintos.get_project(project["id"])
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed["active_focus_session"]["focus_session_id"], focus_session["focus_session_id"])
        self.assertEqual(refreshed["latest_focus_session"]["focus_session_id"], focus_session["focus_session_id"])

    def test_update_focus_session_saves_progress_note(self) -> None:
        focus_session = self.start_focus_session()
        updated = sprintos.update_focus_session(focus_session["focus_session_id"], progress_note="Created the first local package.")
        self.assertEqual(updated["progress_note"], "Created the first local package.")

    def test_complete_focus_session_marks_completed_and_sets_ended_at(self) -> None:
        focus_session = self.start_focus_session()
        completed = sprintos.complete_focus_session(focus_session["focus_session_id"], "Prototype package was generated.", "Saved the package and checked the files.")
        self.assertEqual(completed["session_status"], "completed")
        self.assertTrue(completed["ended_at"])

    def test_complete_focus_session_generates_report_folder(self) -> None:
        focus_session = self.start_focus_session()
        completed = sprintos.complete_focus_session(focus_session["focus_session_id"], "Workspace export finished.", "Verified CODEX_START_HERE.md exists.")
        report_dir = Path(completed["report_path"])
        self.assertTrue(report_dir.exists())
        self.assertEqual(set(path.name for path in report_dir.iterdir()), set(sprintos.FOCUS_SESSION_REPORT_FILES))

    def test_complete_focus_session_appends_progress_note_to_project(self) -> None:
        project = self.create_project()
        focus_session = self.start_focus_session(project)
        sprintos.complete_focus_session(focus_session["focus_session_id"], "Finished the prototype package.", "Stopped after checking the preview.")
        refreshed = sprintos.get_project(project["id"])
        self.assertIsNotNone(refreshed)
        self.assertIn("Focus Session Completed", refreshed["last_progress_note"])

    def test_stop_focus_session_marks_stopped_and_generates_resume_note(self) -> None:
        focus_session = self.start_focus_session()
        stopped = sprintos.stop_focus_session(focus_session["focus_session_id"], "Hit a blocker in verification.", "Stopped after the first failing check.")
        self.assertEqual(stopped["session_status"], "stopped")
        resume_note = (Path(stopped["report_path"]) / "resume-note.md").read_text(encoding="utf-8")
        self.assertIn("where i stopped", resume_note.lower())
        self.assertIn("next tiny action", resume_note.lower())

    def test_focus_session_report_contains_done_definition_and_not_to_do(self) -> None:
        focus_session = self.start_focus_session()
        completed = sprintos.complete_focus_session(focus_session["focus_session_id"], "Prototype package done.", "Saved the local package.")
        report_text = (Path(completed["report_path"]) / "focus-session-report.md").read_text(encoding="utf-8")
        self.assertIn("## Done Definition", report_text)
        self.assertIn("## Not To Do", report_text)

    def test_focus_session_zip_includes_report_files(self) -> None:
        focus_session = self.start_focus_session()
        completed = sprintos.complete_focus_session(focus_session["focus_session_id"], "Workspace sync finished.", "Read the changed files summary.")
        zip_name, payload = sprintos.build_focus_session_zip(completed)
        self.assertTrue(zip_name.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertEqual(set(zf.namelist()), set(sprintos.FOCUS_SESSION_REPORT_FILES))

    def test_focus_session_file_serving_blocks_path_traversal(self) -> None:
        focus_session = self.start_focus_session()
        completed = sprintos.complete_focus_session(focus_session["focus_session_id"], "Completed session.", "Saved progress.")
        server = self.start_server()
        report_text = self.http_get(server, f"/api/focus_session_report?id={completed['focus_session_id']}&file=focus-session-report.md").decode("utf-8")
        self.assertIn("Focus Session Report", report_text)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/focus_session_report?id={completed['focus_session_id']}&file=../sprintos.py")
        self.assertEqual(exc.exception.code, 400)

    def test_command_center_detects_active_focus_session(self) -> None:
        project = self.create_project()
        self.start_focus_session(project, 30)
        refreshed = sprintos.get_project(project["id"])
        summary = sprintos.build_project_command_summary(refreshed)
        self.assertEqual(summary["recommended_action"]["action_id"], "continue_focus_session")
        self.assertIn("Active focus session", summary["status_summary"])

    def test_run_recommended_action_can_start_default_focus_session(self) -> None:
        project = self.create_project()
        server = self.start_server()
        payload = self.http_post_json(server, "/api/run_recommended_action", {"project_id": project["id"]})
        self.assertEqual(payload["action_id"], "start_focus_session")
        focus_session = sprintos.get_project(project["id"])["active_focus_session"]
        self.assertEqual(focus_session["timebox_minutes"], 30)

    def test_run_recommended_action_does_not_complete_active_session_without_explicit_outcome(self) -> None:
        project = self.create_project()
        focus_session = self.start_focus_session(project, 30)
        with sprintos.db() as conn:
            conn.execute("UPDATE focus_sessions SET started_at = ?, updated_at = ? WHERE id = ?", ("2000-01-01T00:00:00", "2000-01-01T00:00:00", focus_session["focus_session_id"]))
            conn.commit()
        server = self.start_server()
        payload = self.http_post_json(server, "/api/run_recommended_action", {"project_id": project["id"]})
        self.assertFalse(payload["ran"])
        self.assertEqual(payload["action_id"], "complete_focus_session")
        refreshed = sprintos.get_focus_session(focus_session["focus_session_id"])
        self.assertEqual(refreshed["session_status"], "active")

    def test_project_markdown_export_includes_focus_session_context(self) -> None:
        project = self.create_project()
        focus_session = self.start_focus_session(project)
        sprintos.complete_focus_session(focus_session["focus_session_id"], "Finished exporting the workspace.", "Saved the workspace prompt.")
        refreshed = sprintos.get_project(project["id"])
        _, markdown = sprintos.write_markdown_export(refreshed)
        self.assertIn("## Focus Session", markdown)
        self.assertIn("Done definition", markdown)

    def test_project_zip_export_includes_focus_session_files(self) -> None:
        project = self.create_project()
        focus_session = self.start_focus_session(project)
        sprintos.complete_focus_session(focus_session["focus_session_id"], "Finished workspace sync.", "Saved a restart note.")
        refreshed = sprintos.get_project(project["id"])
        _, payload = sprintos.build_zip_export(refreshed)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("focus-session.md", names)
            self.assertIn("focus-session-codex-next-prompt.md", names)
            self.assertIn("focus-session-resume-note.md", names)


class _MovedFeedbackLoopTests:
    def test_feedback_tables_are_created(self) -> None:
        with sprintos.db() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }

        self.assertIn("prototype_feedback", tables)
        self.assertIn("prototype_iterations", tables)

    def test_manual_feedback_persists_and_reloads(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")

        created = sprintos.add_feedback_entry(**self.sample_feedback_payload(project, prototype))
        reloaded = sprintos.get_project(project["id"])

        self.assertTrue(created["feedback_id"])
        self.assertEqual(created["feedback_count"], 1)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["feedback"]["count"], 1)
        self.assertEqual(reloaded["feedback"]["recent"][0]["tester_label"], "Tester 1")
        self.assertEqual(reloaded["feedback"]["recent"][0]["would_use"], "yes")

    def test_add_feedback_endpoint_and_feedback_list_endpoint_work(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        server = self.start_server()

        created = self.http_post_json(server, "/api/add_feedback", self.sample_feedback_payload(project, prototype))
        entries = self.http_get(
            server,
            f"/api/feedback?project_id={project['id']}&prototype_id={prototype['id']}",
        )
        payload = json.loads(entries.decode("utf-8"))

        self.assertIn("feedback_id", created)
        self.assertEqual(created["feedback_count"], 1)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["entries"][0]["tester_label"], "Tester 1")

    def test_import_feedback_json_persists_valid_payload(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        server = self.start_server()
        exported = {
            "prototype_id": prototype["id"],
            "prototype_type": prototype["prototype_type"],
            "project_title": project["title"],
            "timestamp": sprintos.now_iso(),
            "tester_label": "Imported tester",
            "source": "local_preview",
            "rating": 5,
            "pain_level": 3,
            "would_use": "yes",
            "would_pay": "yes",
            "confusing_parts": "The CTA text is a little soft.",
            "missing_features": "A stronger proof section.",
            "favorite_part": "The simple framing.",
            "freeform_feedback": "Would test this again after one more iteration.",
        }

        payload = self.http_post_json(
            server,
            "/api/import_feedback_json",
            {"project_id": project["id"], "prototype_id": prototype["id"], "json_text": json.dumps(exported)},
        )
        reloaded = sprintos.get_project(project["id"])

        self.assertIn("feedback_id", payload)
        self.assertEqual(payload["feedback_count"], 1)
        self.assertEqual(payload["warnings"], [])
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["feedback"]["recent"][0]["tester_label"], "Imported tester")
        self.assertEqual(reloaded["feedback"]["recent"][0]["source"], "local_preview")

    def test_malformed_feedback_json_returns_graceful_error(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        server = self.start_server()

        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_post_json(
                server,
                "/api/import_feedback_json",
                {"project_id": project["id"], "prototype_id": prototype["id"], "json_text": "{not valid json"},
            )

        self.assertEqual(exc.exception.code, 400)
        body = exc.exception.read().decode("utf-8")
        self.assertIn("Malformed feedback JSON", body)

    def test_feedback_summary_handles_zero_and_small_samples(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")

        empty_summary = sprintos.build_iteration_summary(project, prototype["id"])
        self.assertEqual(empty_summary["decision"], "test with more people")
        self.assertIn("No stored prototype feedback yet", empty_summary["summary"])

        sprintos.add_feedback_entry(**self.sample_feedback_payload(project, prototype, tester_label="Tester A"))
        sprintos.add_feedback_entry(**self.sample_feedback_payload(project, prototype, tester_label="Tester B", would_use="maybe"))

        small_sample_summary = sprintos.build_iteration_summary(sprintos.get_project(project["id"]), prototype["id"])
        self.assertEqual(small_sample_summary["decision"], "test with more people")
        self.assertIn("directional feedback from a small sample", small_sample_summary["summary"].lower())

    def test_feedback_summary_handles_positive_and_negative_signals(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")

        for idx in range(3):
            sprintos.add_feedback_entry(
                **self.sample_feedback_payload(
                    project,
                    prototype,
                    tester_label=f"Positive {idx}",
                    rating=4,
                    pain_level=4,
                    would_use="yes",
                    would_pay="maybe",
                )
            )
        positive_summary = sprintos.build_iteration_summary(sprintos.get_project(project["id"]), prototype["id"])
        self.assertEqual(positive_summary["decision"], "iterate")
        self.assertIn("Average rating: 4.0/5.", positive_summary["summary"])

        project_2 = self.create_project(raw_idea="Build a second prototype for negative feedback testing.")
        prototype_2 = self.generate_prototype(project_2, "landing_page")
        for idx in range(4):
            sprintos.add_feedback_entry(
                **self.sample_feedback_payload(
                    project_2,
                    prototype_2,
                    tester_label=f"Negative {idx}",
                    rating=1,
                    pain_level=2,
                    would_use="no",
                    would_pay="no",
                    confusing_parts="The value proposition is weak.",
                    missing_features="A believable result.",
                    favorite_part="Nothing stood out.",
                )
            )
        negative_summary = sprintos.build_iteration_summary(sprintos.get_project(project_2["id"]), prototype_2["id"])
        self.assertIn(negative_summary["decision"], {"pivot", "park"})
        self.assertIn("Mostly no", negative_summary["signals"]["willingness_to_use"])

    def test_iteration_brief_and_codex_prompt_include_required_sections(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        for idx in range(3):
            sprintos.add_feedback_entry(
                **self.sample_feedback_payload(
                    project,
                    prototype,
                    tester_label=f"Tester {idx}",
                    confusing_parts="The first step is not obvious.",
                    missing_features="A clearer result preview.",
                )
            )

        summary = sprintos.build_iteration_summary(sprintos.get_project(project["id"]), prototype["id"])
        brief = summary["iteration_brief"]
        prompt = summary["codex_prompt"]

        self.assertIn("## Feedback Summary", brief)
        self.assertIn("## Decision", brief)
        self.assertIn("## Next Iteration Objective", brief)
        self.assertIn("## Top 3 Changes To Make", brief)
        self.assertIn("## Acceptance Criteria", brief)
        self.assertIn("## Updated Done Definition", brief)

        self.assertIn("Read AGENTS.md first if present", prompt)
        self.assertIn("## Feedback Summary", prompt)
        self.assertIn("## Constraints", prompt)
        self.assertIn("## Verification Commands", prompt)
        self.assertIn("## Non-Goals", prompt)
        self.assertIn("Do not overbuild", prompt)

    def test_generate_iteration_brief_endpoint_persists_latest_iteration(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        for idx in range(3):
            sprintos.add_feedback_entry(**self.sample_feedback_payload(project, prototype, tester_label=f"Tester {idx}"))
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/generate_iteration_brief",
            {"project_id": project["id"], "prototype_id": prototype["id"]},
        )
        reloaded = sprintos.get_project(project["id"])

        self.assertIn("iteration_brief", payload)
        self.assertIn("codex_prompt", payload)
        self.assertTrue(payload["suggested_next_tiny_action"])
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded["feedback"]["latest_iteration"]["feedback_count"], 3)


class _MovedReleaseFeedbackLoopTests:
    def create_release_feedback_context(self):
        project, _, _, workspace, _, _, _ = self.create_command_center_workspace_context(
            create_snapshot=True,
            run_sync=True,
            run_verification=True,
        )
        release_pack = self.create_workspace_release(project, workspace, release_label="release-feedback", run_checks=True)
        refreshed = sprintos.get_project(project["id"])
        self.assertIsNotNone(refreshed)
        return refreshed, workspace, release_pack

    def test_release_feedback_tables_are_created(self) -> None:
        with sprintos.db() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
        self.assertIn("workspace_release_feedback", tables)
        self.assertIn("workspace_release_iterations", tables)

    def test_add_release_feedback_persists_and_reloads(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()

        created = sprintos.add_release_feedback(**self.sample_release_feedback_payload(project, release_pack))
        reloaded = sprintos.get_project(project["id"])

        self.assertTrue(created["feedback_id"])
        self.assertEqual(created["feedback_count"], 1)
        self.assertEqual(reloaded["latest_release_feedback_count"], 1)
        self.assertEqual(reloaded["recent_release_feedback"][0]["tester_label"], "Release Tester 1")

    def test_add_release_feedback_defaults_to_latest_release_pack(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()

        created = sprintos.add_release_feedback(project["id"], tester_label="Default release feedback")

        self.assertEqual(created["release_pack_id"], release_pack["release_pack_id"])

    def test_add_release_feedback_endpoint_and_list_endpoint_work(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        server = self.start_server()

        created = self.http_post_json(server, "/api/add_release_feedback", self.sample_release_feedback_payload(project, release_pack))
        entries = self.http_get(
            server,
            f"/api/release_feedback?project_id={project['id']}&release_pack_id={release_pack['release_pack_id']}",
        )
        payload = json.loads(entries.decode("utf-8"))

        self.assertIn("feedback_id", created)
        self.assertEqual(created["feedback_count"], 1)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["entries"][0]["tester_label"], "Release Tester 1")

    def test_import_release_feedback_json_persists_valid_payload(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        server = self.start_server()
        exported = {
            "tester_label": "Imported release tester",
            "source": "local_preview",
            "rating": 5,
            "would_use": "yes",
            "would_pay": "yes",
            "confusing_parts": "The start state still needs a slightly stronger label.",
            "missing_features": "A more obvious end-state summary.",
            "favorite_part": "The local packaging.",
            "bug_report": "",
            "freeform_feedback": "Would share this with one more teammate.",
        }

        payload = self.http_post_json(
            server,
            "/api/import_release_feedback_json",
            {"project_id": project["id"], "release_pack_id": release_pack["release_pack_id"], "json_text": json.dumps(exported)},
        )
        reloaded = sprintos.get_project(project["id"])

        self.assertIn("feedback_id", payload)
        self.assertEqual(payload["feedback_count"], 1)
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(reloaded["recent_release_feedback"][0]["tester_label"], "Imported release tester")

    def test_import_release_feedback_json_accepts_lists(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        server = self.start_server()
        items = [
            {"tester_label": "List tester 1", "rating": 4, "would_use": "yes"},
            {"tester_label": "List tester 2", "rating": 3, "would_use": "maybe"},
        ]

        payload = self.http_post_json(
            server,
            "/api/import_release_feedback_json",
            {"project_id": project["id"], "release_pack_id": release_pack["release_pack_id"], "json_text": json.dumps(items)},
        )

        self.assertEqual(payload["feedback_count"], 2)
        self.assertEqual(len(payload["feedback_ids"]), 2)

    def test_malformed_release_feedback_json_returns_graceful_error(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        server = self.start_server()

        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_post_json(
                server,
                "/api/import_release_feedback_json",
                {"project_id": project["id"], "release_pack_id": release_pack["release_pack_id"], "json_text": "{not valid json"},
            )

        self.assertEqual(exc.exception.code, 400)
        body = exc.exception.read().decode("utf-8")
        self.assertIn("Malformed release feedback JSON", body)

    def test_release_feedback_raw_json_is_redacted(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        secret = "sk-live-release-feedback-secret"

        sprintos.add_release_feedback(
            **self.sample_release_feedback_payload(
                project,
                release_pack,
                raw_json=json.dumps({"api_key": secret, "Authorization": f"Bearer {secret}", "note": secret}),
            )
        )

        entries = sprintos.list_release_feedback(project["id"], release_pack["release_pack_id"])
        self.assertNotIn(secret, entries[0]["raw_json"])
        self.assertIn("[redacted]", entries[0]["raw_json"])

    def test_generate_release_iteration_handles_zero_and_small_samples(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()

        empty_summary = sprintos.build_release_iteration_summary(project, release_pack["release_pack_id"])
        self.assertEqual(empty_summary["decision"], "test_more")
        self.assertIn("No stored release feedback yet", empty_summary["summary"])

        sprintos.add_release_feedback(**self.sample_release_feedback_payload(project, release_pack, tester_label="Release A"))
        sprintos.add_release_feedback(**self.sample_release_feedback_payload(project, release_pack, tester_label="Release B", would_use="maybe"))
        small_summary = sprintos.build_release_iteration_summary(sprintos.get_project(project["id"]), release_pack["release_pack_id"])

        self.assertEqual(small_summary["decision"], "test_more")
        self.assertIn("directional feedback from a small sample", small_summary["summary"].lower())

    def test_generate_release_iteration_detects_repeated_bugs(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        for idx in range(3):
            sprintos.add_release_feedback(
                **self.sample_release_feedback_payload(
                    project,
                    release_pack,
                    tester_label=f"Bug tester {idx}",
                    rating=2,
                    would_use="no",
                    would_pay="no",
                    bug_report="The app fails after the first click.",
                )
            )

        summary = sprintos.build_release_iteration_summary(sprintos.get_project(project["id"]), release_pack["release_pack_id"])
        self.assertEqual(summary["decision"], "fix_blockers")

    def test_generate_release_iteration_handles_positive_feedback(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        for idx in range(4):
            sprintos.add_release_feedback(
                **self.sample_release_feedback_payload(
                    project,
                    release_pack,
                    tester_label=f"Positive release {idx}",
                    rating=5,
                    would_use="yes",
                    would_pay="maybe",
                    confusing_parts="",
                    missing_features="",
                    bug_report="",
                    freeform_feedback="Clean and clear.",
                )
            )

        summary = sprintos.build_release_iteration_summary(sprintos.get_project(project["id"]), release_pack["release_pack_id"])
        self.assertIn(summary["decision"], {"iterate", "release_ready"})

    def test_release_iteration_prompt_contains_required_sections(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        for idx in range(3):
            sprintos.add_release_feedback(
                **self.sample_release_feedback_payload(
                    project,
                    release_pack,
                    tester_label=f"Prompt release {idx}",
                    confusing_parts="The first action is unclear.",
                    missing_features="A clearer result summary.",
                )
            )

        summary = sprintos.build_release_iteration_summary(sprintos.get_project(project["id"]), release_pack["release_pack_id"])
        prompt = summary["codex_prompt"]

        self.assertIn("Read AGENTS.md first.", prompt)
        self.assertIn("## Feedback Summary", prompt)
        self.assertIn("## Acceptance Criteria", prompt)
        self.assertIn("## Verification Commands", prompt)
        self.assertIn("## Non-Goals", prompt)
        self.assertIn("Do not overbuild.", prompt)

    def test_generate_release_iteration_endpoint_persists_latest_iteration(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        for idx in range(3):
            sprintos.add_release_feedback(**self.sample_release_feedback_payload(project, release_pack, tester_label=f"Endpoint release {idx}"))
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/generate_release_iteration",
            {"project_id": project["id"], "release_pack_id": release_pack["release_pack_id"]},
        )
        reloaded = sprintos.get_project(project["id"])

        self.assertIn("release_iteration_id", payload)
        self.assertTrue(payload["next_tiny_action"])
        self.assertIsNotNone(reloaded["latest_release_iteration"])
        self.assertEqual(reloaded["latest_release_iteration"]["feedback_count"], 3)

    def test_release_feedback_ui_renders_in_index(self) -> None:
        self.assertIn("Release Feedback", sprintos.INDEX_HTML)
        self.assertIn("Generate Release Iteration", sprintos.INDEX_HTML)

    def test_release_feedback_activity_events_are_recorded(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        sprintos.add_release_feedback(**self.sample_release_feedback_payload(project, release_pack))
        sprintos.import_release_feedback_json(project["id"], json.dumps({"tester_label": "Imported release"}), release_pack_id=release_pack["release_pack_id"])
        summary = sprintos.build_release_iteration_summary(sprintos.get_project(project["id"]), release_pack["release_pack_id"])
        sprintos.save_release_iteration_snapshot(project["id"], release_pack["release_pack_id"], summary)

        events = self.list_activity(project["id"])
        event_types = [item["event_type"] for item in events]
        self.assertIn("release_feedback_added", event_types)
        self.assertIn("release_feedback_imported", event_types)
        self.assertIn("release_iteration_generated", event_types)

    def test_release_pack_docs_include_release_feedback_return_instructions(self) -> None:
        _, _, release_pack = self.create_release_feedback_context()
        tester_instructions = (Path(release_pack["path"]) / "TESTER_INSTRUCTIONS.md").read_text(encoding="utf-8")
        deploy_or_share = (Path(release_pack["path"]) / "DEPLOY_OR_SHARE.md").read_text(encoding="utf-8")

        self.assertIn("Rate the release 1-5", tester_instructions)
        self.assertIn("Bug report", tester_instructions)
        self.assertIn("Bring Feedback Back Into SprintOS", deploy_or_share)
        self.assertIn("Do not collect sensitive personal data", deploy_or_share)

    def test_today_dashboard_recommends_generate_release_iteration_when_feedback_exists_without_iteration(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        sprintos.add_release_feedback(**self.sample_release_feedback_payload(project, release_pack))

        summary = sprintos.build_today_dashboard_summary()
        recommended = summary["global_recommended_action"]
        self.assertEqual(recommended["action_id"], "generate_release_iteration")
        self.assertEqual(recommended["project_id"], project["id"])

    def test_command_center_includes_release_feedback_and_iteration_state(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        sprintos.add_release_feedback(**self.sample_release_feedback_payload(project, release_pack))
        refreshed = sprintos.get_project(project["id"])
        summary = sprintos.build_project_command_summary(refreshed)

        self.assertIn("release_feedback", summary["assets"])
        self.assertIn("release_iteration", summary["missing"])
        self.assertEqual(summary["recommended_action"]["source_action_id"], "generate_release_iteration")

    def test_project_markdown_export_includes_release_feedback_context(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        for idx in range(3):
            sprintos.add_release_feedback(**self.sample_release_feedback_payload(project, release_pack, tester_label=f"Markdown release {idx}"))
        summary = sprintos.build_release_iteration_summary(sprintos.get_project(project["id"]), release_pack["release_pack_id"])
        sprintos.save_release_iteration_snapshot(project["id"], release_pack["release_pack_id"], summary)

        _, markdown = sprintos.write_markdown_export(sprintos.get_project(project["id"]))

        self.assertIn("## Release Feedback", markdown)
        self.assertIn("Latest release decision", markdown)
        self.assertIn("Latest release feedback summary", markdown)

    def test_project_zip_export_includes_release_feedback_and_iteration_files(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        for idx in range(3):
            sprintos.add_release_feedback(**self.sample_release_feedback_payload(project, release_pack, tester_label=f"ZIP release {idx}"))
        summary = sprintos.build_release_iteration_summary(sprintos.get_project(project["id"]), release_pack["release_pack_id"])
        sprintos.save_release_iteration_snapshot(project["id"], release_pack["release_pack_id"], summary)

        _, payload = sprintos.build_zip_export(sprintos.get_project(project["id"]))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("release-feedback.md", names)
            self.assertIn("release-iteration-brief.md", names)
            self.assertIn("release-iteration-codex-prompt.md", names)

    def test_release_feedback_exports_do_not_include_fake_api_keys(self) -> None:
        project, _, release_pack = self.create_release_feedback_context()
        secret = "sk-release-feedback-export-secret"
        sprintos.add_release_feedback(
            **self.sample_release_feedback_payload(
                project,
                release_pack,
                bug_report=f"Authorization: Bearer {secret}",
                raw_json=json.dumps({"note": secret}),
            )
        )
        summary = sprintos.build_release_iteration_summary(sprintos.get_project(project["id"]), release_pack["release_pack_id"])
        sprintos.save_release_iteration_snapshot(project["id"], release_pack["release_pack_id"], summary)

        _, markdown = sprintos.write_markdown_export(sprintos.get_project(project["id"]))
        _, payload = sprintos.build_zip_export(sprintos.get_project(project["id"]))

        self.assertNotIn(secret, markdown)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for name in zf.namelist():
                self.assertNotIn(secret, zf.read(name).decode("utf-8"))


class PrototypeBuilderTests(SprintOSTestCase):
    def app_file_generation_payload(self, title: str = "Business Idea Scoreboard") -> dict:
        safe_title = title.replace('"', "").strip() or "Business Idea Scoreboard"
        return {
            "app_name": safe_title,
            "app_type": "static_app",
            "short_description": "Paste a business idea, score it, and show the smallest next test.",
            "user_flow": [
                "Paste the business idea into the textarea.",
                "Click Score Idea.",
                "Review the score, risks, smallest test, and next action.",
            ],
            "files": [
                {
                    "filename": "index.html",
                    "content": f"""<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" /><title>{safe_title}</title><link rel=\"stylesheet\" href=\"style.css\" /></head><body><main class=\"shell\" data-app-shape=\"business_idea_scorer\"><h1>{safe_title}</h1><p>Paste a rough idea and get a deterministic first-pass score.</p><textarea id=\"idea-input\" class=\"app-main-input\" data-template-marker=\"main-input\" placeholder=\"Describe the business idea\"></textarea><button id=\"score-idea\" data-template-marker=\"primary-action\">Score Idea</button><section id=\"result\" class=\"result\" data-template-marker=\"result-output\"><div id=\"idea-score\" class=\"app-output\">0</div><ul id=\"idea-risks\" data-template-marker=\"risk_breakdown\"><li>No score yet.</li></ul><div id=\"idea-smallest-test\" data-template-marker=\"smallest-testable-version\">No score yet.</div><div id=\"idea-next-action\" data-template-marker=\"next-action\">No score yet.</div></section></main><script src=\"app.js\"></script></body></html>""",
                },
                {
                    "filename": "style.css",
                    "content": "body{font-family:sans-serif;background:#f6f1e8;color:#1e1b18;margin:0;padding:24px;} .shell{max-width:860px;margin:0 auto;} textarea{width:100%;min-height:180px;padding:12px;} button{margin-top:12px;padding:12px 16px;} .result{margin-top:18px;padding:16px;border:1px solid #c7b8a8;background:#fff;white-space:pre-wrap;}",
                },
                {
                    "filename": "app.js",
                    "content": "const scoreNode=document.getElementById('idea-score');const risksNode=document.getElementById('idea-risks');const smallestNode=document.getElementById('idea-smallest-test');const nextNode=document.getElementById('idea-next-action');function scoreIdea(){const raw=document.getElementById('idea-input').value.trim();const words=raw.split(/\\s+/).filter(Boolean).length;const score=Math.max(1, Math.min(10, Math.ceil(words/5)));const demandRisk=score >= 7 ? 'Low' : 'Medium';const executionRisk=score >= 8 ? 'Medium' : 'High';const smallest=score >= 7 ? 'Interview 3 target users this week.' : 'Rewrite the offer into one sentence and test it with one person.';const next=score >= 7 ? 'Build the smallest clickable flow.' : 'Tighten the problem statement first.';scoreNode.textContent=String(score);risksNode.innerHTML='<li>Demand risk: '+demandRisk+'</li><li>Execution risk: '+executionRisk+'</li>';smallestNode.textContent='Smallest testable version: '+smallest;nextNode.textContent='Next action: '+next;}document.getElementById('score-idea').addEventListener('click', scoreIdea);",
                },
                {
                    "filename": "README.md",
                    "content": f"# {safe_title}\n\nRun `python3 -m http.server 8080` and open `index.html`.\n\nThis is a local prototype with deterministic scoring logic only.",
                },
                {
                    "filename": "TEST_PLAN.md",
                    "content": "# Test Plan\n\n- Open the app.\n- Paste a business idea.\n- Click Score Idea.\n- Confirm the visible result updates with a score, risks, smallest testable version, and next action.",
                },
            ],
            "run_instructions": "Run `python3 -m http.server 8080` and open `index.html`.",
            "test_instructions": "Paste a business idea, click Score Idea, and confirm the visible result changes locally.",
            "codex_next_prompt": "Preserve the working app flow, improve one small part only, run the included tests, and do not add dependencies.",
            "limitations": ["This is a local prototype, not a production app."],
            "mocked_parts": ["The scoring logic is deterministic and intentionally simple."],
        }

    def test_prototype_package_generation_creates_required_files(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        package_dir = Path(prototype["path"])

        self.assertTrue(package_dir.exists())
        self.assertEqual(set(path.name for path in package_dir.iterdir()), set(sprintos.PROTOTYPE_FILES))
        index_html = (package_dir / "index.html").read_text(encoding="utf-8")
        readme = (package_dir / "README.md").read_text(encoding="utf-8")
        app_js = (package_dir / "app.js").read_text(encoding="utf-8")
        test_plan = (package_dir / "test-plan.md").read_text(encoding="utf-8")
        import_instructions = (package_dir / "feedback-import-instructions.md").read_text(encoding="utf-8")
        metadata = json.loads((package_dir / "prototype.json").read_text(encoding="utf-8"))

        self.assertIn('href="style.css"', index_html)
        self.assertIn('src="app.js"', index_html)
        self.assertIn("SprintOS prototype", index_html)
        self.assertIn("Tester Feedback", index_html)
        self.assertIn("Save Feedback Locally", index_html)
        self.assertIn("Export Feedback JSON", index_html)
        self.assertIn("python3 -m http.server 8080", readme)
        self.assertIn("Save tester feedback locally", test_plan)
        self.assertIn("feedbackStorageKey", app_js)
        self.assertIn("localStorage.setItem", app_js)
        self.assertIn("exportFeedbackJson", app_js)
        self.assertIn("verify no external calls are required", test_plan.lower())
        self.assertIn("Import into SprintOS", import_instructions)
        self.assertEqual(metadata["project_id"], project["id"])
        self.assertEqual(metadata["prototype_id"], prototype["id"])
        self.assertEqual(metadata["prototype_type"], "landing_page")
        self.assertEqual(set(metadata["files_generated"]), set(sprintos.PROTOTYPE_FILES))

    def test_offline_fallback_still_generates_previewable_app(self) -> None:
        project = self.create_project(raw_idea="Build a business idea scoring app that feels like a real local tool.")
        prototype = self.generate_prototype(project, "landing_page", generation_mode="ai")
        package_dir = Path(prototype["path"])
        metadata = json.loads((package_dir / "prototype.json").read_text(encoding="utf-8"))

        self.assertFalse(metadata["used_ai"])
        self.assertTrue(prototype["preview_url"].endswith("/index.html"))
        self.assertIn('href="style.css"', (package_dir / "index.html").read_text(encoding="utf-8"))
        self.assertTrue((package_dir / "app.js").read_text(encoding="utf-8").strip())

    def test_offline_app_templates_generate_shape_specific_apps(self) -> None:
        cases = [
            {
                "idea": "Build a business idea scorer that evaluates startup ideas.",
                "prototype_type": "landing_page",
                "name": "Idea Scorecard",
                "html": ["Idea Scorecard", "Score Idea", "Smallest testable version", "Risks", 'data-app-shape="business_idea_scorer"', 'data-template-marker="risk_breakdown"'],
                "js": ["scoreIdea", "Demand risk", "smallestNode"],
                "readme": ["Idea Scorecard scores", "The score is deterministic", "score, risks, smallest testable version", "No OpenAI, DeepSeek"],
                "test_plan": ["Test Plan — Idea Scorecard", "score, risks, smallest testable version, and next action"],
                "codex": ["Codex Build Prompt — Idea Scorecard", "Improve Idea Scorecard", "`idea-input`", "`app.js`"],
            },
            {
                "idea": "Build a personal budget calculator for income, expenses, and monthly savings.",
                "prototype_type": "calculator",
                "name": "Budget Snapshot",
                "html": ["Budget Snapshot", "Monthly inputs", "Calculate Budget", "Monthly savings", "spending breakdown", 'data-app-shape="budget_calculator"', 'data-template-marker="spending-breakdown"'],
                "js": ["calculateBudget", "budget-savings", "Recommendation"],
                "readme": ["Budget Snapshot calculates", "Budget output is deterministic arithmetic", "savings, breakdown, and recommendation", "No OpenAI, DeepSeek"],
                "test_plan": ["Test Plan — Budget Snapshot", "monthly savings, spending breakdown, and recommendation"],
                "codex": ["Codex Build Prompt — Budget Snapshot", "Improve Budget Snapshot", "`budget-income`", "`budget-breakdown`"],
            },
            {
                "idea": "Build a study flashcard helper where students paste notes and get cards.",
                "prototype_type": "ai_text_tool",
                "name": "Study Card Builder",
                "html": ["Study Card Builder", "Study notes", "Build Flashcards", "Question / answer cards", "Local/mocked limitation", 'data-app-shape="flashcard_helper"', 'data-template-marker="flashcard-cards"'],
                "js": ["sentenceCards", "buildCards", "question"],
                "readme": ["Study Card Builder turns", "This is not live AI generation", "question/answer cards", "No OpenAI, DeepSeek"],
                "test_plan": ["Test Plan — Study Card Builder", "question/answer cards appear with the local/mocked limitation note visible"],
                "codex": ["Codex Build Prompt — Study Card Builder", "Improve Study Card Builder", "`notes-input`", "`card-output`"],
            },
            {
                "idea": "Build a simple quiz recommender that suggests the best next option.",
                "prototype_type": "quiz_funnel",
                "name": "Quiz Recommender",
                "html": ["Show Recommendation", "Recommendation", "deterministic recommendation"],
                "js": ["showRecommendation", "Local score", "quiz-recommendation"],
                "readme": ["small deterministic score", "recommendation"],
                "test_plan": ["Test Plan"],
                "codex": ["Codex Build Prompt", "Improve the recommendation clarity"],
            },
            {
                "idea": "Build a simple landing waitlist page for early access signups.",
                "prototype_type": "landing_page",
                "name": "Waitlist Launch Page",
                "html": ["Join waitlist", "waitlist", "Mock CTA only"],
                "js": ["waitlist-submit", "local-only", "Mock signup"],
                "readme": ["waitlist confirmation is a mock local state change", "fill the mock CTA"],
                "test_plan": ["Test Plan"],
                "codex": ["Codex Build Prompt", "Improve the local CTA confirmation"],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                project = self.create_project(raw_idea=case["idea"])
                prototype = self.generate_prototype(project, case["prototype_type"], generation_mode="offline")
                package_dir = Path(prototype["path"])
                metadata = json.loads((package_dir / "prototype.json").read_text(encoding="utf-8"))
                index_html = (package_dir / "index.html").read_text(encoding="utf-8")
                app_js = (package_dir / "app.js").read_text(encoding="utf-8")
                readme = (package_dir / "README.md").read_text(encoding="utf-8")
                test_plan = (package_dir / "TEST_PLAN.md").read_text(encoding="utf-8")
                codex_prompt = (package_dir / "codex-build-prompt.md").read_text(encoding="utf-8")

                self.assertEqual(metadata["app_name"], case["name"])
                self.assertIn(case["name"], prototype["title"])
                self.assertLessEqual(len(metadata["app_name"].split()), 4)
                self.assertNotIn("Build a", metadata["app_name"])
                self.assertNotIn("where students paste", metadata["app_name"])
                self.assertNotIn("income, expenses", metadata["app_name"])
                self.assertTrue((package_dir / "test-plan.md").exists())
                for marker in case["html"]:
                    self.assertIn(marker, index_html)
                for marker in case["js"]:
                    self.assertIn(marker, app_js)
                for marker in case["readme"]:
                    self.assertIn(marker, readme)
                for marker in case["test_plan"]:
                    self.assertIn(marker, test_plan)
                for marker in case["codex"]:
                    self.assertIn(marker, codex_prompt)
                self.assertIn("Verify no external calls are required", test_plan)

    def test_app_file_generation_prompt_includes_shape_contracts(self) -> None:
        cases = {
            "business_idea_scorer": [
                "Business idea scorer contract",
                "exact id `idea-input`",
                "`data-template-marker=\"main-input\"`",
                "exact id `score-idea`",
                "`data-template-marker=\"primary-action\"`",
                "exact id `idea-score`",
                "exact id `idea-risks`",
                "`data-template-marker=\"risk_breakdown\"`",
                "exact id `idea-smallest-test`",
                "`data-template-marker=\"smallest-testable-version\"`",
                "exact id `idea-next-action`",
                "`data-template-marker=\"next-action\"`",
            ],
            "budget_calculator": [
                "Budget calculator contract",
                "exact id `budget-income`",
                "`type=\"number\"`",
                "`data-template-marker=\"main-input\"`",
                "exact id `budget-run`",
                "`data-template-marker=\"primary-action\"`",
                "exact id `budget-savings`",
                "exact id `budget-breakdown`",
                "`data-template-marker=\"spending-breakdown\"`",
                "exact id `budget-recommendation`",
                "`data-template-marker=\"recommendation\"`",
                "read `document.getElementById(\"budget-income\").value`",
                "read at least one expense-like numeric input value",
                "handle blank/invalid numbers as 0",
                "calculate savings/surplus/deficit",
                "visible local/demo limitation note",
            ],
            "flashcard_helper": ["Flashcard helper contract", "question/answer cards"],
            "quiz_recommender": ["Quiz/recommender contract", "Show Recommendation"],
            "waitlist_page": ["Landing page contract", "local-only confirmation"],
        }
        for shape, markers in cases.items():
            with self.subTest(shape=shape):
                prompt = sprintos.app_file_generation_instructions(shape)
                self.assertIn("app_name must be concise", prompt)
                self.assertIn("short_description must be one short sentence", prompt)
                for marker in markers:
                    self.assertIn(marker, prompt)

    def test_fake_openai_app_generation_writes_actual_app_files(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-app-test"
        payload = self.app_file_generation_payload()
        project = self.create_project(raw_idea="Build a business idea scoring app that feels like a real local tool.")
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
            prototype = self.generate_prototype(project, "landing_page", generation_mode="auto")
        package_dir = Path(prototype["path"])
        metadata = json.loads((package_dir / "prototype.json").read_text(encoding="utf-8"))

        self.assertTrue(metadata["used_ai"])
        self.assertEqual(metadata["app_type"], "static_app")
        self.assertEqual(metadata["provider"], "openai")
        self.assertIn("Business Idea Scoreboard", (package_dir / "index.html").read_text(encoding="utf-8"))
        self.assertIn("score-idea", (package_dir / "app.js").read_text(encoding="utf-8"))
        self.assertIn("TEST_PLAN.md", metadata["generated_files"])

    def test_fake_provider_app_generation_accepts_shape_contracts(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-shape-contract-test"
        cases = [
            (
                "Build a business idea scorer that evaluates startup ideas.",
                "landing_page",
                "business_idea_scorer",
                ["idea-score", "idea-risks", "idea-smallest-test", "idea-next-action"],
            ),
            (
                "Build a personal budget calculator for income, expenses, and savings.",
                "calculator",
                "budget_calculator",
                ["budget-income", "budget-breakdown", "budget-recommendation", "calculateBudget"],
            ),
            (
                "Build a study flashcard helper where students paste notes and get cards.",
                "ai_text_tool",
                "flashcard_helper",
                ["notes-input", "build-cards", "card-output", "sentenceCards"],
            ),
        ]

        for raw_idea, prototype_type, shape, markers in cases:
            with self.subTest(shape=shape):
                project = self.create_project(raw_idea=raw_idea)
                ctx = sprintos.prototype_context_offline(project, prototype_type, prototype_id="fake-provider-shape")
                payload = sprintos.prototype_offline_app_file_generation_payload(project, prototype_type, "fake-provider-shape", ctx=ctx)
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
                    prototype = self.generate_prototype(project, prototype_type, generation_mode="auto")
                package_dir = Path(prototype["path"])
                metadata = json.loads((package_dir / "prototype.json").read_text(encoding="utf-8"))
                combined = (package_dir / "index.html").read_text(encoding="utf-8") + "\n" + (package_dir / "app.js").read_text(encoding="utf-8")

                self.assertTrue(metadata["used_ai"])
                self.assertEqual(metadata["offline_template_shape"], shape)
                for marker in markers:
                    self.assertIn(marker, combined)

    def test_fake_deepseek_app_generation_writes_actual_app_files(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "deepseek"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["DEEPSEEK_API_KEY"] = "sk-deepseek-app-test"
        payload = self.app_file_generation_payload(title="DeepSeek Idea Scoreboard")
        project = self.create_project(raw_idea="Build a business idea scoring app that feels like a real local tool.")
        with mock.patch(
            "sprintos_core.ai_provider.call_deepseek_chat_completions",
            return_value=fake_provider_result(
                text=json.dumps(payload),
                parsed_json=payload,
                provider="deepseek",
                model=DEFAULT_DEEPSEEK_MODEL,
                task_name="app_file_generation",
            ),
        ):
            prototype = self.generate_prototype(project, "landing_page", generation_mode="auto")
        package_dir = Path(prototype["path"])
        metadata = json.loads((package_dir / "prototype.json").read_text(encoding="utf-8"))

        self.assertTrue(metadata["used_ai"])
        self.assertEqual(metadata["provider"], "deepseek")
        self.assertIn("DeepSeek Idea Scoreboard", (package_dir / "README.md").read_text(encoding="utf-8"))
        self.assertIn("score-idea", (package_dir / "app.js").read_text(encoding="utf-8"))

    def test_malformed_ai_app_generation_falls_back_offline(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-app-test"
        project = self.create_project(raw_idea="Build a business idea scoring app that feels like a real local tool.")
        with mock.patch(
            "sprintos_core.ai_provider.call_openai_responses",
            return_value=fake_provider_result(text="not-json", parsed_json=None, provider="openai", model=DEFAULT_OPENAI_MODEL, task_name="app_file_generation"),
        ):
            prototype = self.generate_prototype(project, "landing_page", generation_mode="auto")
        metadata = json.loads((Path(prototype["path"]) / "prototype.json").read_text(encoding="utf-8"))

        self.assertFalse(metadata["used_ai"])
        self.assertTrue(metadata["fallback_reason"])

    def test_missing_file_ai_app_generation_falls_back_offline(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-app-test"
        payload = self.app_file_generation_payload()
        payload["files"] = [item for item in payload["files"] if item["filename"] != "app.js"]
        project = self.create_project(raw_idea="Build a business idea scoring app that feels like a real local tool.")
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
            prototype = self.generate_prototype(project, "landing_page", generation_mode="auto")
        package_dir = Path(prototype["path"])
        metadata = json.loads((package_dir / "prototype.json").read_text(encoding="utf-8"))

        self.assertFalse(metadata["used_ai"])
        self.assertIn("feedbackStorageKey", (package_dir / "app.js").read_text(encoding="utf-8"))

    def test_shape_incomplete_ai_app_generation_falls_back_offline(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-shape-fallback-test"
        project = self.create_project(raw_idea="Build a personal budget calculator for income, expenses, and monthly savings.")
        payload = self.app_file_generation_payload(title="Generic Score App")
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
            prototype = self.generate_prototype(project, "calculator", generation_mode="auto")
        package_dir = Path(prototype["path"])
        metadata = json.loads((package_dir / "prototype.json").read_text(encoding="utf-8"))

        self.assertFalse(metadata["used_ai"])
        self.assertEqual(metadata["offline_template_shape"], "budget_calculator")
        self.assertIn("budget-income", (package_dir / "index.html").read_text(encoding="utf-8"))
        self.assertIn("app_shape_validation_failed", metadata["fallback_reason"])

    def test_no_api_key_appears_in_prototype_metadata_or_zip(self) -> None:
        secret = "sk-openai-prototype-leak-test"
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = secret
        payload = self.app_file_generation_payload()
        project = self.create_project(raw_idea="Build a business idea scoring app that feels like a real local tool.")
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
            prototype = self.generate_prototype(project, "landing_page", generation_mode="auto")
        package_dir = Path(prototype["path"])
        _, zip_payload = sprintos.build_prototype_zip(prototype)

        self.assertNotIn(secret, (package_dir / "prototype.json").read_text(encoding="utf-8"))
        self.assertNotIn(secret, json.dumps(sprintos.get_project(project["id"])))
        with zipfile.ZipFile(io.BytesIO(zip_payload)) as zf:
            for name in zf.namelist():
                self.assertNotIn(secret, zf.read(name).decode("utf-8"))

    def test_app_package_zips_exclude_env_git_and_obvious_secrets(self) -> None:
        secret = "sk-prototype-zip-secret"
        project = self.create_project(raw_idea="Build a personal budget calculator for income, expenses, and monthly savings.")
        prototype = self.generate_prototype(project, "calculator", generation_mode="offline")
        prototype_dir = Path(prototype["path"])
        (prototype_dir / ".env").write_text(f"OPENAI_API_KEY={secret}\n", encoding="utf-8")
        (prototype_dir / ".env.local").write_text(f"DEEPSEEK_API_KEY={secret}\n", encoding="utf-8")
        (prototype_dir / ".git").mkdir()
        (prototype_dir / ".git" / "config").write_text(secret, encoding="utf-8")

        build_pack = self.generate_build_pack(project, prototype, build_target="static_app")
        build_dir = Path(build_pack["path"])
        (build_dir / ".env").write_text(f"OPENAI_API_KEY={secret}\n", encoding="utf-8")
        (build_dir / ".env.local").write_text(f"DEEPSEEK_API_KEY={secret}\n", encoding="utf-8")
        (build_dir / ".git").mkdir()
        (build_dir / ".git" / "config").write_text(secret, encoding="utf-8")

        for _, payload in (sprintos.build_prototype_zip(prototype), sprintos.build_build_pack_zip(build_pack)):
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                names = zf.namelist()
                self.assertFalse(any(Path(name).name.startswith(".env") for name in names))
                self.assertFalse(any(name == ".git" or name.startswith(".git/") or "/.git/" in name for name in names))
                for name in names:
                    self.assertNotIn(secret, zf.read(name).decode("utf-8", errors="ignore"))

    def test_prototype_paths_are_sanitized(self) -> None:
        project = self.create_project(raw_idea="../Bad Name!! prototype package for a weird local tool")
        prototype = self.generate_prototype(project, "calculator")
        path = Path(prototype["path"])

        self.assertEqual(path.parent, sprintos.EXPORT_DIR / "prototypes")
        self.assertNotIn("..", path.name)
        self.assertRegex(path.name, r"^[a-z0-9-]+$")

    def test_prototype_metadata_persists_and_reloads(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "ai_text_tool")

        reloaded = sprintos.get_project(project["id"])
        stored = sprintos.get_prototype(prototype["id"], include_prompt=True)

        self.assertIsNotNone(reloaded)
        self.assertIsNotNone(stored)
        self.assertEqual(reloaded["latest_prototype"]["id"], prototype["id"])
        self.assertEqual(stored["prototype_type"], "ai_text_tool")
        self.assertTrue(stored["codex_prompt"])
        self.assertIn("files_generated", stored["metadata"])

    def test_prototype_zip_endpoint_includes_all_files(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "quiz_funnel")
        server = self.start_server()

        payload = self.http_get(server, f"/api/prototype_zip?id={prototype['id']}")
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertEqual(set(zf.namelist()), set(sprintos.PROTOTYPE_FILES))
            self.assertIn("Codex Build Prompt", zf.read("codex-build-prompt.md").decode("utf-8"))

    def test_prototype_file_serving_blocks_path_traversal(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        server = self.start_server()

        preview = self.http_get(server, f"/prototype/{prototype['id']}/index.html").decode("utf-8")
        self.assertIn("SprintOS prototype", preview)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/prototype_file?id={prototype['id']}&file=../sprintos.py")
        self.assertEqual(exc.exception.code, 400)

    def test_each_prototype_type_generates_local_assets_without_external_dependencies(self) -> None:
        project = self.create_project()

        for prototype_type in sprintos.PROTOTYPE_TYPES:
            prototype = self.generate_prototype(project, prototype_type)
            package_dir = Path(prototype["path"])
            index_html = (package_dir / "index.html").read_text(encoding="utf-8")
            app_js = (package_dir / "app.js").read_text(encoding="utf-8")

            self.assertIn('href="style.css"', index_html)
            self.assertIn('src="app.js"', index_html)
            self.assertNotIn("https://", index_html)
            self.assertNotIn("http://", index_html)
            self.assertNotIn("fetch(", app_js)
            self.assertNotIn("openai", app_js.lower())

    def test_codex_build_prompt_contains_required_sections(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "codex_app_brief")
        prompt = (Path(prototype["path"]) / "codex-build-prompt.md").read_text(encoding="utf-8")

        self.assertIn("Read AGENTS.md first if present", prompt)
        self.assertIn("## Objective", prompt)
        self.assertIn("## Context", prompt)
        self.assertIn("## Current Prototype Files", prompt)
        self.assertIn("## Implementation Constraints", prompt)
        self.assertIn("## Acceptance Criteria", prompt)
        self.assertIn("## Verification Commands", prompt)
        self.assertIn("## Non-Goals", prompt)
        self.assertIn("## Data Model If Needed", prompt)
        self.assertIn("## API Routes If Needed", prompt)
        self.assertIn("## Tests", prompt)
        self.assertIn("Do not overbuild", prompt)

    def test_project_markdown_export_includes_feedback_and_iteration_context(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        for idx in range(3):
            sprintos.add_feedback_entry(**self.sample_feedback_payload(project, prototype, tester_label=f"Tester {idx}"))
        summary = sprintos.build_iteration_summary(sprintos.get_project(project["id"]), prototype["id"])
        sprintos.save_iteration_snapshot(project["id"], prototype["id"], summary)

        _, markdown = sprintos.write_markdown_export(sprintos.get_project(project["id"]))

        self.assertIn("## Feedback Loop", markdown)
        self.assertIn("Feedback count", markdown)
        self.assertIn("## Latest Iteration Brief", markdown)
        self.assertIn("## Latest Iteration Codex Prompt", markdown)

    def test_project_zip_export_includes_feedback_and_iteration_files(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        for idx in range(3):
            sprintos.add_feedback_entry(**self.sample_feedback_payload(project, prototype, tester_label=f"Tester {idx}"))
        summary = sprintos.build_iteration_summary(sprintos.get_project(project["id"]), prototype["id"])
        sprintos.save_iteration_snapshot(project["id"], prototype["id"], summary)

        _, payload = sprintos.build_zip_export(sprintos.get_project(project["id"]))

        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("feedback.md", names)
            self.assertIn("iteration-brief.md", names)
            self.assertIn("iteration-codex-prompt.md", names)
            self.assertIn("Feedback Loop", zf.read("feedback.md").decode("utf-8"))
            self.assertIn("Iteration Brief", zf.read("iteration-brief.md").decode("utf-8"))

    def test_generate_prototype_endpoint_returns_expected_fields(self) -> None:
        project = self.create_project()
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/generate_prototype",
            {"project_id": project["id"], "prototype_type": "landing_page"},
        )

        self.assertIn("prototype_id", payload)
        self.assertEqual(payload["prototype_type"], "landing_page")
        self.assertIn("/prototype/", payload["preview_url"])
        self.assertIn("/api/prototype_zip", payload["zip_url"])
        self.assertIn("Read AGENTS.md first if present", payload["codex_prompt"])
        self.assertEqual(set(payload["files_generated"]), set(sprintos.PROTOTYPE_FILES))
        self.assertEqual(payload["project"]["latest_prototype"]["prototype_type"], "landing_page")


class DeployPackTests(SprintOSTestCase):
    def test_deploy_packs_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }

        self.assertIn("deploy_packs", tables)

    def test_deploy_readiness_passes_for_generated_prototype(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")

        readiness = sprintos.check_deploy_readiness(prototype)

        self.assertTrue(readiness["ready"])
        self.assertEqual(readiness["blockers"], [])
        self.assertIn("index.html", readiness["checked_files"])
        self.assertIn("prototype.json", readiness["checked_files"])

    def test_deploy_readiness_catches_missing_index_html(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        (Path(prototype["path"]) / "index.html").unlink()

        readiness = sprintos.check_deploy_readiness(prototype)

        self.assertFalse(readiness["ready"])
        self.assertTrue(any("Missing required file: index.html" in item for item in readiness["blockers"]))

    def test_deploy_readiness_catches_external_network_markers(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        app_js = Path(prototype["path"]) / "app.js"
        app_js.write_text(app_js.read_text(encoding="utf-8") + '\nfetch("https://example.com/api");\n', encoding="utf-8")

        readiness = sprintos.check_deploy_readiness(prototype)

        self.assertFalse(readiness["ready"])
        self.assertTrue(any("fetch()" in item or "external URL" in item for item in readiness["blockers"]))

    def test_deploy_pack_generation_creates_required_files(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        deploy_pack = self.generate_deploy_pack(project, prototype, "static")
        package_dir = Path(deploy_pack["path"])

        self.assertTrue(package_dir.exists())
        self.assertEqual(set(path.name for path in package_dir.iterdir()), set(sprintos.DEPLOY_PACK_FILES))
        self.assertEqual((package_dir / "index.html").read_text(encoding="utf-8"), (Path(prototype["path"]) / "index.html").read_text(encoding="utf-8"))
        self.assertEqual((package_dir / "style.css").read_text(encoding="utf-8"), (Path(prototype["path"]) / "style.css").read_text(encoding="utf-8"))
        self.assertEqual((package_dir / "app.js").read_text(encoding="utf-8"), (Path(prototype["path"]) / "app.js").read_text(encoding="utf-8"))

    def test_github_pages_target_includes_nojekyll(self) -> None:
        deploy_pack = self.generate_deploy_pack(hosting_target="github_pages")
        package_dir = Path(deploy_pack["path"])

        self.assertTrue((package_dir / ".nojekyll").exists())
        deploy_md = (package_dir / "DEPLOY.md").read_text(encoding="utf-8")
        readme = (package_dir / "README.md").read_text(encoding="utf-8")
        self.assertIn("GitHub Pages", deploy_md)
        self.assertIn("main", deploy_md)
        self.assertIn("GitHub Pages Note", readme)

    def test_netlify_target_includes_netlify_toml(self) -> None:
        deploy_pack = self.generate_deploy_pack(hosting_target="netlify")
        package_dir = Path(deploy_pack["path"])

        self.assertTrue((package_dir / "netlify.toml").exists())
        self.assertIn('publish = "."', (package_dir / "netlify.toml").read_text(encoding="utf-8"))
        self.assertIn("drag-and-drop", (package_dir / "DEPLOY.md").read_text(encoding="utf-8"))

    def test_vercel_target_includes_vercel_json(self) -> None:
        deploy_pack = self.generate_deploy_pack(hosting_target="vercel")
        package_dir = Path(deploy_pack["path"])

        self.assertTrue((package_dir / "vercel.json").exists())
        metadata = json.loads((package_dir / "vercel.json").read_text(encoding="utf-8"))
        self.assertIn("cleanUrls", metadata)
        self.assertIn("framework preset `Other`", (package_dir / "DEPLOY.md").read_text(encoding="utf-8"))

    def test_deploy_md_and_metadata_include_readiness_and_share_message(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        deploy_pack = self.generate_deploy_pack(project, prototype, "static")
        package_dir = Path(deploy_pack["path"])

        deploy_md = (package_dir / "DEPLOY.md").read_text(encoding="utf-8")
        metadata = json.loads((package_dir / "deploy-pack.json").read_text(encoding="utf-8"))

        self.assertIn("python3 -m http.server 8080", deploy_md)
        self.assertIn("Do not collect sensitive personal data in this prototype.", deploy_md)
        self.assertTrue(metadata["readiness"]["ready"])
        self.assertIn("rough prototype", metadata["suggested_share_message"])
        self.assertIn("suggested_feedback_instruction", metadata)

    def test_deploy_pack_zip_endpoint_includes_all_files(self) -> None:
        deploy_pack = self.generate_deploy_pack(hosting_target="static")
        server = self.start_server()

        payload = self.http_get(server, f"/api/deploy_pack_zip?id={deploy_pack['id']}")
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertEqual(set(zf.namelist()), set(sprintos.DEPLOY_PACK_FILES))
            self.assertIn("Deploy Pack", zf.read("DEPLOY.md").decode("utf-8"))

    def test_deploy_pack_file_serving_blocks_path_traversal(self) -> None:
        deploy_pack = self.generate_deploy_pack(hosting_target="static")
        server = self.start_server()

        preview = self.http_get(server, f"/deploy_pack/{deploy_pack['id']}/index.html").decode("utf-8")
        self.assertIn("SprintOS prototype", preview)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/deploy_pack_file?id={deploy_pack['id']}&file=../sprintos.py")
        self.assertEqual(exc.exception.code, 400)

    def test_project_hydration_and_exports_include_latest_deploy_pack(self) -> None:
        project = self.create_project()
        prototype_1 = self.generate_prototype(project, "landing_page")
        pack_1 = self.generate_deploy_pack(project, prototype_1, "static")
        prototype_2 = self.generate_prototype(sprintos.get_project(project["id"]), "landing_page")

        refreshed = sprintos.get_project(project["id"])
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed["latest_prototype"]["id"], prototype_2["id"])
        self.assertIsNone(refreshed["latest_deploy_pack"])

        pack_2 = self.generate_deploy_pack(refreshed, prototype_2, "netlify")
        refreshed = sprintos.get_project(project["id"])
        self.assertEqual(refreshed["latest_deploy_pack"]["id"], pack_2["id"])
        self.assertNotEqual(pack_1["id"], pack_2["id"])

        _, markdown = sprintos.write_markdown_export(refreshed)
        _, payload = sprintos.build_zip_export(refreshed)

        self.assertIn("## Latest Deploy Pack", markdown)
        self.assertIn(pack_2["path"], markdown)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertIn("deploy-pack.md", set(zf.namelist()))
            self.assertIn("Netlify", zf.read("deploy-pack.md").decode("utf-8"))

    def test_generate_deploy_pack_endpoint_returns_expected_fields_and_blocks_when_needed(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/generate_deploy_pack",
            {"project_id": project["id"], "prototype_id": prototype["id"], "hosting_target": "static"},
        )

        self.assertIn("deploy_pack_id", payload)
        self.assertEqual(payload["hosting_target"], "static")
        self.assertIn("/deploy_pack/", payload["preview_url"])
        self.assertIn("/api/deploy_pack_zip", payload["zip_url"])
        self.assertEqual(set(payload["files_generated"]), set(sprintos.DEPLOY_PACK_FILES))
        self.assertEqual(payload["project"]["latest_deploy_pack"]["hosting_target"], "static")

        broken_prototype = self.generate_prototype(sprintos.get_project(project["id"]), "landing_page")
        (Path(broken_prototype["path"]) / "index.html").unlink()
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_post_json(
                server,
                "/api/generate_deploy_pack",
                {"project_id": project["id"], "prototype_id": broken_prototype["id"], "hosting_target": "static"},
            )
        self.assertEqual(exc.exception.code, 400)
        body = json.loads(exc.exception.read().decode("utf-8"))
        self.assertIn("readiness", body)
        self.assertTrue(body["blockers"])


class BuildPackTests(SprintOSTestCase):
    def app_file_generation_payload(self) -> dict:
        return {
            "app_name": "Build Pack Source App",
            "app_type": "static_app",
            "short_description": "A deterministic scoring app with one working flow.",
            "user_flow": [
                "Paste the idea.",
                "Click Score Idea.",
                "Review the visible score, risks, smallest testable version, and next action.",
            ],
            "files": [
                {
                    "filename": "index.html",
                    "content": """<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" /><title>Build Pack Source App</title><link rel=\"stylesheet\" href=\"style.css\" /></head><body><main data-app-shape=\"business_idea_scorer\"><textarea id=\"idea-input\" data-template-marker=\"main-input\"></textarea><button id=\"score-idea\" data-template-marker=\"primary-action\">Score Idea</button><div id=\"result\" class=\"result\" data-template-marker=\"result-output\"><div id=\"idea-score\">0</div><ul id=\"idea-risks\" data-template-marker=\"risk_breakdown\"><li>No score yet.</li></ul><div id=\"idea-smallest-test\" data-template-marker=\"smallest-testable-version\">No score yet.</div><div id=\"idea-next-action\" data-template-marker=\"next-action\">No score yet.</div></div><script src=\"app.js\"></script></main></body></html>""",
                },
                {"filename": "style.css", "content": "body{font-family:sans-serif;padding:24px;}textarea{width:100%;min-height:120px;} .result{margin-top:16px;}"},
                {
                    "filename": "app.js",
                    "content": "function scoreIdea(){const idea=document.getElementById('idea-input').value.trim();const score=idea.length>20?'7':'4';document.getElementById('idea-score').textContent=score;document.getElementById('idea-risks').innerHTML='<li>Demand risk: medium</li><li>Execution risk: high</li>';document.getElementById('idea-smallest-test').textContent='Smallest testable version: interview 3 target users.';document.getElementById('idea-next-action').textContent='Next action: book one validation call.';}document.getElementById('score-idea').addEventListener('click', scoreIdea);",
                },
                {"filename": "README.md", "content": "# Build Pack Source App\n\nRun `python3 -m http.server 8080` and open `index.html`."},
                {"filename": "TEST_PLAN.md", "content": "# Test Plan\n\n- Open the app.\n- Click Score Idea.\n- Confirm the result updates with a score, risks, smallest testable version, and next action."},
            ],
            "run_instructions": "Run `python3 -m http.server 8080` and open `index.html`.",
            "test_instructions": "Click the main button and confirm the result changes locally.",
            "codex_next_prompt": "Preserve the working flow and improve one small part only.",
            "limitations": ["Prototype only."],
            "mocked_parts": ["The scoring logic is intentionally simple."],
        }

    def test_build_packs_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }

        self.assertIn("build_packs", tables)

    def test_static_app_build_pack_generation_creates_required_files(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        build_pack = self.generate_build_pack(project, prototype, build_target="static_app")
        package_dir = Path(build_pack["path"])

        self.assertEqual(set(path.relative_to(package_dir).as_posix() for path in package_dir.rglob("*") if path.is_file()), set(sprintos.build_pack_files_for_target("static_app")))
        self.assertIn("/build_pack/", build_pack["preview_url"] or "")
        self.assertIn('href="style.css"', (package_dir / "src" / "index.html").read_text(encoding="utf-8"))
        self.assertIn('src="app.js"', (package_dir / "src" / "index.html").read_text(encoding="utf-8"))

    def test_build_pack_preserves_ai_generated_files(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-build-pack-test"
        payload = self.app_file_generation_payload()
        project = self.create_project(raw_idea="Build a business idea scoring app that feels like a real local tool.")
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
            prototype = self.generate_prototype(project, "landing_page", generation_mode="auto")
        build_pack = self.generate_build_pack(project, prototype, build_target="static_app")
        prototype_dir = Path(prototype["path"])
        build_pack_dir = Path(build_pack["path"])
        prompt = (build_pack_dir / "CODEX_BUILD_PROMPT.md").read_text(encoding="utf-8")

        self.assertEqual((build_pack_dir / "src" / "index.html").read_text(encoding="utf-8"), (prototype_dir / "index.html").read_text(encoding="utf-8"))
        self.assertEqual((build_pack_dir / "src" / "style.css").read_text(encoding="utf-8"), (prototype_dir / "style.css").read_text(encoding="utf-8"))
        self.assertEqual((build_pack_dir / "src" / "app.js").read_text(encoding="utf-8"), (prototype_dir / "app.js").read_text(encoding="utf-8"))
        self.assertIn("AI-generated prototype: yes", prompt)
        self.assertIn("Improve one small part only", prompt)

    def test_python_stdlib_build_pack_generation_creates_required_files(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        build_pack = self.generate_build_pack(project, prototype, build_target="python_stdlib_app")
        package_dir = Path(build_pack["path"])

        self.assertEqual(set(path.relative_to(package_dir).as_posix() for path in package_dir.rglob("*") if path.is_file()), set(sprintos.build_pack_files_for_target("python_stdlib_app")))
        self.assertEqual(build_pack["run_command"], "python3 app.py")
        self.assertEqual(build_pack["test_command"], "python3 tests/smoke_app.py")
        self.assertIn("/static/style.css", (package_dir / "src" / "templates" / "index.html").read_text(encoding="utf-8"))

    def test_ai_tool_stub_build_pack_generation_includes_optional_ai_runtime_files_and_copy(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        build_pack = self.generate_build_pack(project, prototype, build_target="ai_tool_stub")
        package_dir = Path(build_pack["path"])
        env_example = (package_dir / ".env.example").read_text(encoding="utf-8")
        readme_text = (package_dir / "README.md").read_text(encoding="utf-8")
        app_text = (package_dir / "app.py").read_text(encoding="utf-8")
        frontend_text = (package_dir / "src" / "static" / "app.js").read_text(encoding="utf-8")
        html_text = (package_dir / "src" / "templates" / "index.html").read_text(encoding="utf-8")

        self.assertTrue((package_dir / ".env.example").exists())
        self.assertIn("AI_ENABLED=false", env_example)
        self.assertIn("AI_PROVIDER=openai", env_example)
        self.assertIn("OPENAI_API_KEY=", env_example)
        self.assertIn("MODEL=", env_example)
        self.assertIn("AI_TIMEOUT_SECONDS=20", env_example)
        self.assertIn("AI_MAX_OUTPUT_TOKENS=1200", env_example)
        self.assertIn("mocked/offline", readme_text.lower())
        self.assertIn("copy `.env.example` to `.env`", readme_text.lower())
        self.assertIn("do not commit `.env`", readme_text.lower())
        self.assertIn("deepseek runtime", readme_text.lower())
        self.assertIn("urllib.request", app_text)
        self.assertIn("OPENAI_API_KEY", app_text)
        self.assertIn("AI_ENABLED", app_text)
        self.assertIn("/api/generate", app_text)
        self.assertNotIn("sk-", app_text)
        self.assertIn("/api/generate", frontend_text)
        self.assertIn("/api/generate", html_text)

    def test_ai_tool_stub_build_pack_generated_app_uses_mocked_mode_without_api_key(self) -> None:
        build_pack = self.generate_build_pack(build_target="ai_tool_stub")
        package_dir = Path(build_pack["path"])

        os.environ["AI_ENABLED"] = "false"
        spec = importlib.util.spec_from_file_location("generated_ai_tool_app", package_dir / "app.py")
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        result = module.generate_output("Turn this messy note into one next step")

        self.assertTrue(result["ok"])
        self.assertFalse(result["used_ai"])
        self.assertTrue(result["output"])
        self.assertIn("disabled", result["fallback_reason"].lower())

    def test_ai_tool_stub_build_pack_agents_and_prompt_preserve_runtime_constraints(self) -> None:
        build_pack = self.generate_build_pack(build_target="ai_tool_stub")
        package_dir = Path(build_pack["path"])
        agents_text = (package_dir / "AGENTS.md").read_text(encoding="utf-8")
        prompt_text = (package_dir / "CODEX_BUILD_PROMPT.md").read_text(encoding="utf-8")

        self.assertIn("Preserve the mocked/offline fallback.", agents_text)
        self.assertIn("Never expose API keys", agents_text)
        self.assertIn("If you add DeepSeek later", agents_text)
        self.assertIn("Tests must pass without a real API key.", agents_text)
        self.assertIn("Keep the existing optional server-side OpenAI runtime narrow, explicit, and fully optional.", prompt_text)
        self.assertIn("DeepSeek runtime support as a separate follow-up task", prompt_text)
        self.assertIn("Do not add browser-side provider calls.", prompt_text)
        self.assertIn("Do not add external dependencies unless explicitly requested.", prompt_text)
        self.assertIn("Tests must pass without a real API key.", prompt_text)

    def test_ai_tool_stub_build_pack_metadata_includes_runtime_fields(self) -> None:
        build_pack = self.generate_build_pack(build_target="ai_tool_stub")
        metadata = json.loads((Path(build_pack["path"]) / "build-pack.json").read_text(encoding="utf-8"))

        self.assertTrue(metadata["ai_runtime_available"])
        self.assertEqual(metadata["ai_runtime_default_mode"], "mocked")
        self.assertEqual(metadata["ai_runtime_provider"], "openai")
        self.assertFalse(metadata["ai_runtime_requires_key"])
        self.assertEqual(metadata["ai_runtime_env_file"], ".env.example")
        self.assertEqual(metadata["api_endpoint"], "/api/generate")

    def test_codex_repo_brief_build_pack_generation_creates_reference_files(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "codex_app_brief")
        build_pack = self.generate_build_pack(project, prototype, build_target="codex_repo_brief")
        package_dir = Path(build_pack["path"])

        expected = set(sprintos.build_pack_files_for_target("codex_repo_brief"))
        self.assertEqual(set(path.relative_to(package_dir).as_posix() for path in package_dir.rglob("*") if path.is_file()), expected)
        self.assertIn("Prototype Reference", (package_dir / "prototype-reference.md").read_text(encoding="utf-8"))
        self.assertIn("Feedback Reference", (package_dir / "feedback-reference.md").read_text(encoding="utf-8"))
        self.assertIn("Deploy Reference", (package_dir / "deploy-reference.md").read_text(encoding="utf-8"))

    def test_build_pack_metadata_includes_required_fields(self) -> None:
        build_pack = self.generate_build_pack(build_target="python_stdlib_app")
        metadata = json.loads((Path(build_pack["path"]) / "build-pack.json").read_text(encoding="utf-8"))

        self.assertEqual(metadata["run_command"], "python3 app.py")
        self.assertEqual(metadata["test_command"], "python3 tests/smoke_app.py")
        self.assertTrue(metadata["suggested_first_codex_task"])
        self.assertTrue(metadata["non_goals"])
        self.assertEqual(metadata["build_pack_id"], build_pack["id"])

    def test_build_pack_codex_prompt_contains_required_sections(self) -> None:
        build_pack = self.generate_build_pack(build_target="static_app")
        prompt = (Path(build_pack["path"]) / "CODEX_BUILD_PROMPT.md").read_text(encoding="utf-8")

        self.assertIn("Read AGENTS.md first.", prompt)
        self.assertIn("## Objective", prompt)
        self.assertIn("## Context", prompt)
        self.assertIn("## Constraints", prompt)
        self.assertIn("## Acceptance Criteria", prompt)
        self.assertIn("## Verification Commands", prompt)
        self.assertIn("## Non-Goals", prompt)
        self.assertIn("## Suggested First PR-Sized Task", prompt)
        self.assertIn("Do not overbuild.", prompt)

    def test_build_pack_zip_endpoint_includes_all_generated_files(self) -> None:
        build_pack = self.generate_build_pack(build_target="python_stdlib_app")
        server = self.start_server()

        payload = self.http_get(server, f"/api/build_pack_zip?id={build_pack['id']}")
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertEqual(set(zf.namelist()), set(sprintos.build_pack_files_for_target("python_stdlib_app")))
            self.assertIn("Codex Build Prompt", zf.read("CODEX_BUILD_PROMPT.md").decode("utf-8"))

    def test_build_pack_file_serving_blocks_path_traversal(self) -> None:
        build_pack = self.generate_build_pack(build_target="static_app")
        server = self.start_server()

        preview = self.http_get(server, f"/build_pack/{build_pack['id']}/src/index.html").decode("utf-8")
        self.assertIn("SprintOS prototype", preview)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/build_pack_file?id={build_pack['id']}&file=../sprintos.py")
        self.assertEqual(exc.exception.code, 400)

    def test_generated_static_build_pack_smoke_test_passes(self) -> None:
        build_pack = self.generate_build_pack(build_target="static_app")
        result = subprocess.run(
            ["python3", "tests/smoke_static.py"],
            cwd=build_pack["path"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("smoke_static ok", result.stdout)

    def test_generated_python_build_pack_smoke_test_passes(self) -> None:
        build_pack = self.generate_build_pack(build_target="python_stdlib_app")
        result = subprocess.run(
            ["python3", "tests/smoke_app.py"],
            cwd=build_pack["path"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("smoke_app ok", result.stdout)

    def test_generated_ai_tool_stub_build_pack_smoke_test_passes_without_api_key(self) -> None:
        build_pack = self.generate_build_pack(build_target="ai_tool_stub")
        result = subprocess.run(
            ["python3", "tests/smoke_app.py"],
            cwd=build_pack["path"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, msg=result.stdout + result.stderr)
        self.assertIn("smoke_app ok", result.stdout)

    def test_project_markdown_export_includes_build_pack_context(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        deploy_pack = self.generate_deploy_pack(project, prototype, "static")
        self.generate_build_pack(sprintos.get_project(project["id"]), prototype, deploy_pack=deploy_pack, build_target="python_stdlib_app")

        _, markdown = sprintos.write_markdown_export(sprintos.get_project(project["id"]))

        self.assertIn("## Latest Build Pack", markdown)
        self.assertIn("Run command", markdown)
        self.assertIn("Suggested first Codex task", markdown)

    def test_project_zip_export_includes_build_pack_files_when_available(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        self.generate_build_pack(project, prototype, build_target="codex_repo_brief")

        _, payload = sprintos.build_zip_export(sprintos.get_project(project["id"]))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("build-pack.md", names)
            self.assertIn("build-pack-codex-prompt.md", names)
            self.assertIn("Codex Build Pack", zf.read("build-pack.md").decode("utf-8"))

    def test_project_hydration_and_prompts_include_latest_build_pack(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        build_pack = self.generate_build_pack(project, prototype, build_target="static_app")

        refreshed = sprintos.get_project(project["id"])
        self.assertEqual(refreshed["latest_build_pack"]["id"], build_pack["id"])
        self.assertIn(build_pack["path"], refreshed["sprint"]["codex_handoff"]["content"])

        summary = sprintos.build_iteration_summary(refreshed, prototype["id"])
        self.assertIn(build_pack["path"], summary["codex_prompt"])
        self.assertIn(build_pack["run_command"], summary["codex_prompt"])

    def test_generate_build_pack_endpoint_returns_expected_fields(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/generate_build_pack",
            {"project_id": project["id"], "prototype_id": prototype["id"], "build_target": "static_app"},
        )

        self.assertIn("build_pack_id", payload)
        self.assertEqual(payload["build_target"], "static_app")
        self.assertIn("/api/build_pack_zip", payload["zip_url"])
        self.assertIn("/build_pack/", payload["preview_url"])
        self.assertIn("Read AGENTS.md first.", payload["codex_prompt"])
        self.assertEqual(payload["run_command"], "python3 -m http.server 8080 -d src")
        self.assertEqual(set(payload["files_generated"]), set(sprintos.build_pack_files_for_target("static_app")))


class LocalBackupTests(SprintOSTestCase):
    def seed_backup_files(self) -> None:
        (self.root / "README.md").write_text("# Temp SprintOS\n", encoding="utf-8")
        (self.root / "AGENTS.md").write_text("# Temp Agents\n", encoding="utf-8")
        (self.root / ".env.example").write_text("OPENAI_API_KEY=\n", encoding="utf-8")
        docs_dir = self.root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "ARCHITECTURE.md").write_text("# Architecture\n", encoding="utf-8")
        scripts_dir = self.root / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        (scripts_dir / "helper.py").write_text("print('helper')\n", encoding="utf-8")
        tests_dir = self.root / "tests"
        tests_dir.mkdir(parents=True, exist_ok=True)
        (tests_dir / "sample_test.txt").write_text("sample\n", encoding="utf-8")
        core_dir = self.root / "sprintos_core"
        core_dir.mkdir(parents=True, exist_ok=True)
        (core_dir / "sample.py").write_text("VALUE = 1\n", encoding="utf-8")
        export_dir = sprintos.EXPORT_DIR / "reports"
        export_dir.mkdir(parents=True, exist_ok=True)
        (export_dir / "summary.md").write_text("local report\n", encoding="utf-8")
        workspace_dir = sprintos.WORKSPACE_DIR / "demo"
        workspace_dir.mkdir(parents=True, exist_ok=True)
        (workspace_dir / "app.py").write_text("print('workspace')\n", encoding="utf-8")

    def tamper_backup_manifest(self, backup: dict, manifest: dict) -> None:
        manifest_path = Path(backup["manifest_path"])
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        metadata = dict(backup["metadata"])
        metadata["manifest"] = manifest
        sprintos.update_local_backup_metadata(backup["backup_id"], metadata, backup_status=backup["backup_status"])

    def test_local_backup_tables_are_created(self) -> None:
        with sprintos.db() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
        self.assertIn("local_backups", tables)
        self.assertIn("local_restores", tables)

    def test_create_local_backup_produces_zip_and_manifest(self) -> None:
        self.seed_backup_files()
        backup = self.create_local_backup("nightly")

        self.assertTrue(Path(backup["backup_path"]).exists())
        self.assertTrue(Path(backup["manifest_path"]).exists())
        self.assertEqual(Path(backup["backup_path"]).parent, self.root / "backups")
        self.assertEqual(Path(backup["manifest_path"]).parent.parent, self.root / "exports" / "local_backups")
        manifest = json.loads(Path(backup["manifest_path"]).read_text(encoding="utf-8"))
        self.assertEqual(manifest["backup_id"], backup["backup_id"])
        self.assertTrue(manifest["files"])
        self.assertIn("data/sprintos.sqlite", {item["path"] for item in manifest["files"]})

    def test_local_backup_excludes_env_git_backup_zips_and_fake_api_key_files(self) -> None:
        self.seed_backup_files()
        (self.root / ".env").write_text("OPENAI_API_KEY=test-root-secret\n", encoding="utf-8")
        git_dir = self.root / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]\nrepositoryformatversion = 0\n", encoding="utf-8")
        (sprintos.BACKUP_DIR / "old-backup.zip").write_bytes(b"zip")
        (sprintos.EXPORT_DIR / "old-export.zip").write_bytes(b"zip")
        (sprintos.EXPORT_DIR / "leak.txt").write_text("OPENAI_API_KEY=test-leak-secret\n", encoding="utf-8")

        backup = self.create_local_backup("safe")
        manifest = json.loads(Path(backup["manifest_path"]).read_text(encoding="utf-8"))
        paths = {item["path"] for item in manifest["files"]}

        self.assertNotIn(".env", paths)
        self.assertNotIn(".git/config", paths)
        self.assertNotIn("backups/old-backup.zip", paths)
        self.assertNotIn("exports/old-export.zip", paths)
        self.assertNotIn("exports/leak.txt", paths)

    def test_local_backup_includes_data_exports_and_workspaces_when_present(self) -> None:
        self.seed_backup_files()
        backup = self.create_local_backup("roots")
        manifest = json.loads(Path(backup["manifest_path"]).read_text(encoding="utf-8"))
        included = set(manifest["included_roots"])
        paths = {item["path"] for item in manifest["files"]}

        self.assertIn("data", included)
        self.assertIn("exports", included)
        self.assertIn("workspaces", included)
        self.assertIn("exports/reports/summary.md", paths)
        self.assertIn("workspaces/demo/app.py", paths)

    def test_verify_local_backup_passes_clean_backup(self) -> None:
        self.seed_backup_files()
        backup = self.create_local_backup("verify-clean")

        result = sprintos.verify_local_backup(backup["backup_id"])

        self.assertTrue(result["verified"])
        self.assertEqual(result["blockers"], [])
        self.assertEqual(sprintos.get_local_backup(backup["backup_id"])["backup_status"], "verified")

    def test_verify_local_backup_detects_manifest_mismatch_and_forbidden_env(self) -> None:
        self.seed_backup_files()
        backup = self.create_local_backup("verify-bad")
        with zipfile.ZipFile(Path(backup["backup_path"]), "a", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("stray.txt", "oops")
            zf.writestr(".env", "OPENAI_API_KEY=test-bad-secret\n")

        result = sprintos.verify_local_backup(backup["backup_id"])

        self.assertFalse(result["verified"])
        self.assertTrue(any("manifest" in item.lower() for item in result["blockers"]))
        self.assertTrue(any(".env" in item for item in result["blockers"]))

    def test_restore_local_backup_dry_run_does_not_write_files(self) -> None:
        self.seed_backup_files()
        readme = self.root / "README.md"
        original = readme.read_text(encoding="utf-8")
        backup = self.create_local_backup("dry-run")
        readme.write_text("changed after backup\n", encoding="utf-8")

        restore = sprintos.restore_local_backup(backup["backup_id"], dry_run=True)

        self.assertEqual(readme.read_text(encoding="utf-8"), "changed after backup\n")
        self.assertEqual(restore["restore_status"], "dry_run")
        self.assertTrue((Path(restore["report_path"]) / "restore-report.md").exists())
        self.assertNotEqual(readme.read_text(encoding="utf-8"), original)

    def test_restore_local_backup_real_requires_confirm(self) -> None:
        self.seed_backup_files()
        backup = self.create_local_backup("confirm-required")
        with self.assertRaises(ValueError):
            sprintos.restore_local_backup(backup["backup_id"], dry_run=False, confirm_restore=False)

    def test_restore_local_backup_real_preserves_env_and_restores_files(self) -> None:
        self.seed_backup_files()
        readme = self.root / "README.md"
        env_path = self.root / ".env"
        env_path.write_text("OPENAI_API_KEY=test-keep-me\n", encoding="utf-8")
        original = readme.read_text(encoding="utf-8")
        backup = self.create_local_backup("restore-real")
        readme.write_text("broken\n", encoding="utf-8")

        restore = sprintos.restore_local_backup(backup["backup_id"], dry_run=False, confirm_restore=True)

        self.assertIn(restore["restore_status"], {"completed", "completed_with_warnings"})
        self.assertEqual(readme.read_text(encoding="utf-8"), original)
        self.assertEqual(env_path.read_text(encoding="utf-8"), "OPENAI_API_KEY=test-keep-me\n")

    def test_restore_local_backup_blocks_path_traversal_entries(self) -> None:
        self.seed_backup_files()
        backup = self.create_local_backup("traversal")
        manifest = json.loads(Path(backup["manifest_path"]).read_text(encoding="utf-8"))
        manifest["files"].append({"path": "../evil.txt", "size": 4, "modified_time": "2024-01-01T00:00:00", "sha256": "deadbeef"})
        manifest["total_files"] += 1
        self.tamper_backup_manifest(backup, manifest)
        with zipfile.ZipFile(Path(backup["backup_path"]), "a", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("../evil.txt", "evil")

        restore = sprintos.restore_local_backup(backup["backup_id"], dry_run=True)

        self.assertTrue(any("unsafe path" in item.lower() for item in restore["blockers"]))
        self.assertFalse((self.root.parent / "evil.txt").exists())

    def test_local_backup_and_restore_file_routes_block_path_traversal(self) -> None:
        self.seed_backup_files()
        backup = self.create_local_backup("route-check")
        restore = sprintos.restore_local_backup(backup["backup_id"], dry_run=True)
        server = self.start_server()

        backup_report = self.http_get(server, f"/api/local_backup_file?id={backup['backup_id']}&file=backup-report.md").decode("utf-8")
        restore_report = self.http_get(server, f"/api/local_restore_file?id={restore['restore_id']}&file=restore-report.md").decode("utf-8")
        self.assertIn("Local Backup Report", backup_report)
        self.assertIn("Local Restore Report", restore_report)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/local_backup_file?id={backup['backup_id']}&file=../secret.txt")
        self.assertEqual(exc.exception.code, 400)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/local_restore_file?id={restore['restore_id']}&file=../secret.txt")
        self.assertEqual(exc.exception.code, 400)

    def test_today_dashboard_includes_local_backup_status_and_activity(self) -> None:
        self.seed_backup_files()
        backup = self.create_local_backup("dashboard")

        summary = sprintos.build_today_dashboard_summary()
        markdown = sprintos.today_dashboard_export_markdown(summary)
        events = sprintos.get_global_activity(limit=10)

        self.assertEqual(summary["local_backup_status"]["latest_backup"]["backup_id"], backup["backup_id"])
        self.assertIn("## Local Backup Status", markdown)
        self.assertIn("local_backup_created", {item["event_type"] for item in events})

    def test_local_backup_endpoints_and_project_zip_export_behave(self) -> None:
        self.seed_backup_files()
        project = self.create_project()
        backup = self.create_local_backup("endpoint")
        server = self.start_server()

        listed = json.loads(self.http_get(server, "/api/local_backups?limit=5").decode("utf-8"))
        stored = json.loads(self.http_get(server, f"/api/local_backup?id={backup['backup_id']}").decode("utf-8"))
        zip_bytes = self.http_get(server, f"/api/local_backup_zip?id={backup['backup_id']}")
        restore_payload = self.http_post_json(server, "/api/restore_local_backup", {"backup_id": backup["backup_id"]})
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_post_json(
                server,
                "/api/restore_local_backup",
                {"backup_id": backup["backup_id"], "dry_run": False, "confirm_restore": False},
            )
        self.assertEqual(exc.exception.code, 400)

        self.assertEqual(listed["backups"][0]["backup_id"], backup["backup_id"])
        self.assertEqual(stored["backup_id"], backup["backup_id"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            self.assertIn("data/sprintos.sqlite", set(zf.namelist()))
        self.assertEqual(restore_payload["restore_status"], "dry_run")

        _, payload = sprintos.build_zip_export(sprintos.get_project(project["id"]))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertTrue(all(not name.endswith(".zip") for name in zf.namelist()))


class _MovedWorkspaceExportTests:
    def test_workspaces_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }

        self.assertIn("workspaces", tables)

    def test_export_workspace_fails_clearly_when_no_build_pack_exists(self) -> None:
        project = self.create_project()
        server = self.start_server()

        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/export_workspace",
            data=json.dumps({"project_id": project["id"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(exc.exception.code, 400)
        body = json.loads(exc.exception.read().decode("utf-8"))
        self.assertIn("No Build Pack exists", body["error"])

    def test_export_workspace_creates_folder_and_copies_build_pack_files(self) -> None:
        build_pack = self.generate_build_pack(build_target="python_stdlib_app")
        workspace = self.export_workspace(build_pack=build_pack)
        workspace_dir = Path(workspace["path"])

        self.assertTrue(workspace_dir.exists())
        self.assertEqual(workspace_dir.parent, self.root / "workspaces")
        self.assertTrue((workspace_dir / "app.py").exists())
        self.assertTrue((workspace_dir / "src" / "templates" / "index.html").exists())
        self.assertTrue(set(workspace["files_copied"]).issuperset({"app.py", "src/templates/index.html"}))

    def test_export_workspace_does_not_copy_env_from_build_pack(self) -> None:
        build_pack = self.generate_build_pack(build_target="ai_tool_stub")
        fixture_key = "sk" + "-test-should-not-copy"
        (Path(build_pack["path"]) / ".env").write_text(f"OPENAI_API_KEY={fixture_key}\n", encoding="utf-8")

        workspace = self.export_workspace(build_pack=build_pack)

        self.assertFalse((Path(workspace["path"]) / ".env").exists())

    def test_export_workspace_adds_required_docs_and_metadata(self) -> None:
        build_pack = self.generate_build_pack(build_target="ai_tool_stub")
        workspace = self.export_workspace(build_pack=build_pack)
        workspace_dir = Path(workspace["path"])

        for name in (
            "SPRINTOS_ORIGIN.md",
            "WORKSPACE_README.md",
            "CODEX_START_HERE.md",
            "RUN_AND_TEST.md",
            "LOCAL_ONLY_NOTICE.md",
            "workspace.json",
        ):
            self.assertTrue((workspace_dir / name).exists(), name)

        self.assertIn("stable local app workspace", (workspace_dir / "SPRINTOS_ORIGIN.md").read_text(encoding="utf-8"))
        self.assertIn("Open `CODEX_START_HERE.md`", (workspace_dir / "WORKSPACE_README.md").read_text(encoding="utf-8"))
        self.assertIn("You are working inside this generated workspace", (workspace_dir / "CODEX_START_HERE.md").read_text(encoding="utf-8"))
        self.assertIn("Default mode is mocked/offline", (workspace_dir / "RUN_AND_TEST.md").read_text(encoding="utf-8"))
        self.assertIn("Do not commit `.env`", (workspace_dir / "LOCAL_ONLY_NOTICE.md").read_text(encoding="utf-8"))

    def test_workspace_json_includes_required_fields(self) -> None:
        build_pack = self.generate_build_pack(build_target="ai_tool_stub")
        workspace = self.export_workspace(build_pack=build_pack)
        metadata = json.loads((Path(workspace["path"]) / "workspace.json").read_text(encoding="utf-8"))

        self.assertEqual(metadata["project_id"], build_pack["project_id"])
        self.assertEqual(metadata["build_pack_id"], build_pack["id"])
        self.assertEqual(metadata["run_command"], build_pack["run_command"])
        self.assertEqual(metadata["test_command"], build_pack["test_command"])
        self.assertTrue(metadata["files_copied"])
        self.assertTrue(metadata["files_added"])
        self.assertEqual(metadata["path"].split("/")[0], "workspaces")
        self.assertTrue(metadata["ai_runtime_available"])

    def test_workspace_init_scripts_are_generated_but_not_executed(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="static_app"))
        workspace_dir = Path(workspace["path"])

        self.assertTrue((workspace_dir / "init_git.sh").exists())
        self.assertTrue((workspace_dir / "init_git.ps1").exists())
        self.assertFalse((workspace_dir / ".git").exists())

    def test_workspace_zip_includes_workspace_files(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))

        filename, payload = sprintos.build_workspace_zip(workspace)
        self.assertTrue(filename.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("CODEX_START_HERE.md", names)
            self.assertIn("RUN_AND_TEST.md", names)
            self.assertIn("workspace.json", names)
            self.assertIn("app.py", names)

    def test_workspace_file_serving_blocks_path_traversal(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        server = self.start_server()

        prompt = self.http_get(server, f"/api/workspace_file?id={workspace['workspace_id']}&file=CODEX_START_HERE.md").decode("utf-8")
        self.assertIn("Read AGENTS.md first.", prompt)
        readme = self.http_get(server, f"/workspace/{workspace['workspace_id']}/WORKSPACE_README.md").decode("utf-8")
        self.assertIn("Workspace Readme", readme)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/workspace_file?id={workspace['workspace_id']}&file=../sprintos.py")
        self.assertEqual(exc.exception.code, 400)

    def test_project_markdown_and_zip_exports_include_workspace_context(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        build_pack = self.generate_build_pack(project, prototype, build_target="python_stdlib_app")
        self.export_workspace(project=sprintos.get_project(project["id"]), build_pack=build_pack)

        refreshed = sprintos.get_project(project["id"])
        self.assertIsNotNone(refreshed)
        _, markdown = sprintos.write_markdown_export(refreshed)
        self.assertIn("## Latest Workspace Export", markdown)
        self.assertIn("Codex start prompt path", markdown)

        _, payload = sprintos.build_zip_export(refreshed)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("workspace.md", names)
            self.assertIn("CODEX_START_HERE.md", names)
            self.assertIn("Workspace Export", zf.read("workspace.md").decode("utf-8"))

    def test_project_hydration_includes_latest_workspace(self) -> None:
        project = self.create_project()
        build_pack = self.generate_build_pack(project=project, build_target="static_app")
        workspace = self.export_workspace(project=project, build_pack=build_pack)

        refreshed = sprintos.get_project(project["id"])
        self.assertEqual(refreshed["latest_workspace"]["workspace_id"], workspace["workspace_id"])
        self.assertIn("You are working inside this generated workspace", refreshed["latest_workspace"]["codex_start_prompt"])

    def test_export_workspace_endpoint_returns_expected_fields(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        build_pack = self.generate_build_pack(project, prototype, build_target="static_app")
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/export_workspace",
            {"project_id": project["id"], "build_pack_id": build_pack["id"]},
        )

        self.assertIn("workspace_id", payload)
        self.assertEqual(payload["workspace_status"], "active")
        self.assertIn("/api/workspace_zip", payload["zip_url"])
        self.assertIn("Read AGENTS.md first.", payload["codex_start_prompt"])
        stored = json.loads(self.http_get(server, f"/api/workspace?id={payload['workspace_id']}").decode("utf-8"))
        self.assertEqual(stored["workspace_id"], payload["workspace_id"])


class _MovedWorkspaceSnapshotTests:
    def test_workspace_snapshots_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
        self.assertIn("workspace_snapshots", tables)

    def test_create_workspace_snapshot_fails_clearly_when_no_workspace_exists(self) -> None:
        project = self.create_project()
        server = self.start_server()

        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/create_workspace_snapshot",
            data=json.dumps({"project_id": project["id"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(exc.exception.code, 400)
        body = json.loads(exc.exception.read().decode("utf-8"))
        self.assertIn("No workspace exists", body["error"])

    def test_workspace_snapshot_creates_folder_and_copies_workspace_files(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        snapshot = self.create_workspace_snapshot(workspace=workspace, snapshot_label="before-codex")
        snapshot_dir = Path(snapshot["snapshot_path"])

        self.assertTrue(snapshot_dir.exists())
        self.assertEqual(snapshot_dir.parent, self.root / "exports" / "workspace_snapshots")
        self.assertTrue((snapshot_dir / "app.py").exists())
        self.assertTrue((snapshot_dir / "src" / "templates" / "index.html").exists())
        self.assertTrue((snapshot_dir / "snapshot-manifest.json").exists())

    def test_workspace_snapshot_excludes_env_and_git_internals(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        workspace_dir = Path(workspace["path"])
        snapshot_secret = "sk" + "-test-snapshot-secret"
        (workspace_dir / ".env").write_text(f"OPENAI_API_KEY={snapshot_secret}\n", encoding="utf-8")
        (workspace_dir / ".git").mkdir()
        (workspace_dir / ".git" / "config").write_text("[core]\nrepositoryformatversion = 0\n", encoding="utf-8")

        snapshot = self.create_workspace_snapshot(workspace=workspace)
        snapshot_dir = Path(snapshot["snapshot_path"])

        self.assertFalse((snapshot_dir / ".env").exists())
        self.assertFalse((snapshot_dir / ".git").exists())

    def test_workspace_snapshot_manifest_includes_sha256_entries(self) -> None:
        snapshot = self.create_workspace_snapshot(workspace=self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app")))
        manifest = json.loads((Path(snapshot["snapshot_path"]) / "snapshot-manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["snapshot_id"], snapshot["snapshot_id"])
        self.assertTrue(manifest["files"])
        self.assertTrue(all(item.get("sha256") for item in manifest["files"]))
        self.assertTrue(all(item.get("path") for item in manifest["files"]))

    def test_workspace_snapshot_report_and_zip_exist(self) -> None:
        snapshot = self.create_workspace_snapshot(workspace=self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app")))

        self.assertTrue((Path(snapshot["snapshot_path"]) / "snapshot-report.md").exists())
        filename, payload = sprintos.build_workspace_snapshot_zip(snapshot)
        self.assertTrue(filename.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("snapshot-manifest.json", names)
            self.assertIn("snapshot-report.md", names)
            self.assertIn("restore-instructions.md", names)
            self.assertIn("app.py", names)
            self.assertNotIn(".env", names)

    def test_workspace_snapshot_file_serving_blocks_path_traversal(self) -> None:
        snapshot = self.create_workspace_snapshot(workspace=self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app")))
        server = self.start_server()

        report = self.http_get(server, f"/api/workspace_snapshot_file?id={snapshot['snapshot_id']}&file=snapshot-report.md").decode("utf-8")
        stored = json.loads(self.http_get(server, f"/api/workspace_snapshot?id={snapshot['snapshot_id']}").decode("utf-8"))

        self.assertIn("Workspace Snapshot", report)
        self.assertEqual(stored["snapshot_id"], snapshot["snapshot_id"])
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/workspace_snapshot_file?id={snapshot['snapshot_id']}&file=../sprintos.py")
        self.assertEqual(exc.exception.code, 400)

    def test_project_hydration_includes_latest_workspace_snapshot(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="static_app"))
        snapshot = self.create_workspace_snapshot(workspace=workspace)
        refreshed = sprintos.get_project(workspace["project_id"])

        self.assertEqual(refreshed["latest_workspace_snapshot"]["snapshot_id"], snapshot["snapshot_id"])

    def test_restore_workspace_snapshot_creates_pre_restore_snapshot_and_replaces_files(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        workspace_dir = Path(workspace["path"])
        app_path = workspace_dir / "app.py"
        original = app_path.read_text(encoding="utf-8")
        snapshot = self.create_workspace_snapshot(workspace=workspace, snapshot_label="before-breakage")
        app_path.write_text(original + "\n# broken change\n", encoding="utf-8")

        restore = self.restore_workspace_snapshot(snapshot)

        self.assertEqual(app_path.read_text(encoding="utf-8"), original)
        self.assertTrue((Path(restore["report_path"]) / "restore-report.md").exists())
        latest_pre_restore = sprintos.latest_project_workspace_snapshot(workspace["project_id"])
        self.assertIn("before-restore-", latest_pre_restore["snapshot_label"])

    def test_restore_workspace_snapshot_preserves_env_and_git_internals(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        workspace_dir = Path(workspace["path"])
        env_path = workspace_dir / ".env"
        git_dir = workspace_dir / ".git"
        git_dir.mkdir()
        git_config = git_dir / "config"
        restore_secret = "sk" + "-test-restore-secret"
        env_path.write_text(f"OPENAI_API_KEY={restore_secret}\n", encoding="utf-8")
        git_config.write_text("[core]\nrepositoryformatversion = 0\n", encoding="utf-8")
        snapshot = self.create_workspace_snapshot(workspace=workspace)
        (workspace_dir / "app.py").write_text("print('broken')\n", encoding="utf-8")

        self.restore_workspace_snapshot(snapshot)

        self.assertEqual(env_path.read_text(encoding="utf-8"), f"OPENAI_API_KEY={restore_secret}\n")
        self.assertEqual(git_config.read_text(encoding="utf-8"), "[core]\nrepositoryformatversion = 0\n")

    def test_compare_workspace_snapshot_detects_added_modified_and_removed_files(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="static_app"))
        workspace_dir = Path(workspace["path"])
        snapshot = self.create_workspace_snapshot(workspace=workspace)
        app_js = workspace_dir / "src" / "app.js"
        app_js.write_text(app_js.read_text(encoding="utf-8") + "\nconsole.log('modified');\n", encoding="utf-8")
        (workspace_dir / "src" / "extra.md").write_text("added\n", encoding="utf-8")
        (workspace_dir / "src" / "style.css").unlink()

        comparison = self.compare_workspace_snapshot(workspace=workspace, snapshot=snapshot)

        self.assertIn("src/extra.md", comparison["added_files"])
        self.assertIn("src/app.js", comparison["modified_files"])
        self.assertIn("src/style.css", comparison["removed_files"])

    def test_project_exports_include_workspace_snapshot_context_and_files(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        snapshot = self.create_workspace_snapshot(workspace=workspace, snapshot_label="export-check")
        project = sprintos.get_project(workspace["project_id"])

        _, markdown = sprintos.write_markdown_export(project)
        _, payload = sprintos.build_zip_export(project)

        self.assertIn("## Latest Workspace Snapshot", markdown)
        self.assertIn(snapshot["snapshot_label"], markdown)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("workspace-snapshot.md", names)
            self.assertIn("restore-instructions.md", names)

    def test_workspace_sync_mentions_latest_snapshot(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="static_app"))
        self.create_workspace_snapshot(workspace=workspace, snapshot_label="before-sync")
        workspace_sync = self.sync_workspace(workspace=workspace)
        report_text = (Path(workspace_sync["report_path"]) / "workspace-sync-report.md").read_text(encoding="utf-8")

        self.assertIn("Latest Snapshot", report_text)
        self.assertIn("before-sync", report_text)

    def test_run_verify_suggests_restore_when_snapshot_exists_and_workspace_fails(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        workspace_dir = Path(workspace["path"])
        self.create_workspace_snapshot(workspace=workspace, snapshot_label="before-verify")
        verify_secret = "sk" + "-test-verify-secret"
        (workspace_dir / ".env").write_text(f"OPENAI_API_KEY={verify_secret}\n", encoding="utf-8")
        project = sprintos.get_project(workspace["project_id"])

        verification = sprintos.run_project_verification(project["id"], verification_scope="all_latest")

        self.assertNotEqual(verification["status"], "passed")
        self.assertTrue("restore" in verification["next_tiny_action"].lower() or "compare" in verification["next_tiny_action"].lower())

    def test_snapshot_reports_and_exports_do_not_contain_fake_api_keys(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        workspace_dir = Path(workspace["path"])
        secret = "sk" + "-snapshot-export-secret"
        (workspace_dir / ".env").write_text(f"OPENAI_API_KEY={secret}\n", encoding="utf-8")

        snapshot = self.create_workspace_snapshot(workspace=workspace, snapshot_label="safe-export")
        project = sprintos.get_project(workspace["project_id"])
        _, markdown = sprintos.write_markdown_export(project)
        report_text = (Path(snapshot["snapshot_path"]) / "snapshot-report.md").read_text(encoding="utf-8")
        manifest_text = (Path(snapshot["snapshot_path"]) / "snapshot-manifest.json").read_text(encoding="utf-8")

        self.assertNotIn(secret, report_text)
        self.assertNotIn(secret, manifest_text)
        self.assertNotIn(secret, markdown)

    def test_snapshot_endpoints_return_expected_fields(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/create_workspace_snapshot",
            {"project_id": workspace["project_id"], "workspace_id": workspace["workspace_id"], "snapshot_label": "endpoint-check"},
        )
        stored = json.loads(self.http_get(server, f"/api/workspace_snapshot?id={payload['snapshot_id']}").decode("utf-8"))
        comparison = json.loads(
            self.http_get(
                server,
                f"/api/compare_workspace_snapshot?workspace_id={workspace['workspace_id']}&snapshot_id={payload['snapshot_id']}",
            ).decode("utf-8")
        )

        self.assertIn("snapshot_id", payload)
        self.assertIn("snapshot_path", payload)
        self.assertIn("report_url", payload)
        self.assertIn("zip_url", payload)
        self.assertEqual(stored["snapshot_id"], payload["snapshot_id"])
        self.assertIn("unchanged_count", comparison)

    def test_restore_workspace_snapshot_api_returns_expected_fields(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        snapshot = self.create_workspace_snapshot(workspace=workspace)
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/restore_workspace_snapshot",
            {"snapshot_id": snapshot["snapshot_id"]},
        )
        report_text = self.http_get(server, payload["restore_report_url"])

        self.assertIn("restored", payload)
        self.assertIn("restore_report_url", payload)
        self.assertIn("files_restored", payload)
        self.assertIn("next_tiny_action", payload)
        self.assertTrue(report_text.decode("utf-8").startswith("# Workspace Restore Report"))


class _MovedWorkspaceSyncTests:
    def test_workspace_syncs_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
        self.assertIn("workspace_syncs", tables)

    def test_sync_workspace_fails_clearly_when_no_workspace_exists(self) -> None:
        project = self.create_project()
        server = self.start_server()

        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/sync_workspace",
            data=json.dumps({"project_id": project["id"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(exc.exception.code, 400)
        body = json.loads(exc.exception.read().decode("utf-8"))
        self.assertIn("No workspace exists", body["error"])

    def test_workspace_sync_detects_workspace_folder_and_writes_report_files(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        project = sprintos.get_project(workspace["project_id"])
        self.assertIsNotNone(project)

        workspace_sync = self.sync_workspace(project=project, workspace=workspace)
        report_dir = Path(workspace_sync["report_path"])

        self.assertEqual(workspace_sync["sync_status"], "passed")
        self.assertTrue(Path(workspace_sync["path"]).exists())
        self.assertTrue(report_dir.exists())
        self.assertEqual(set(path.name for path in report_dir.iterdir()), set(sprintos.WORKSPACE_SYNC_REPORT_FILES))
        parsed = json.loads((report_dir / "workspace-sync.json").read_text(encoding="utf-8"))
        self.assertEqual(parsed["workspace_sync_id"], workspace_sync["workspace_sync_id"])
        changed_files = json.loads((report_dir / "changed-files.json").read_text(encoding="utf-8"))
        self.assertIsInstance(changed_files, list)

    def test_workspace_sync_detects_changed_files_with_mtime_fallback(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="static_app"))
        workspace_dir = Path(workspace["path"])
        app_js = workspace_dir / "src" / "app.js"
        app_js.write_text(app_js.read_text(encoding="utf-8") + "\nconsole.log('workspace sync mtime');\n", encoding="utf-8")

        workspace_sync = self.sync_workspace(workspace=workspace)

        self.assertEqual(workspace_sync["changed_files_source"], "mtime")
        self.assertTrue(any(item["path"] == "src/app.js" for item in workspace_sync["changed_files"]))

    def test_workspace_sync_handles_git_status_when_workspace_is_a_repo(self) -> None:
        try:
            subprocess.run(["git", "--version"], check=False, capture_output=True, text=True)
        except FileNotFoundError:
            self.skipTest("git is not available")
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        workspace_dir = Path(workspace["path"])
        subprocess.run(["git", "init"], cwd=workspace_dir, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.email", "workspace-sync@test.local"], cwd=workspace_dir, check=True, capture_output=True, text=True)
        subprocess.run(["git", "config", "user.name", "Workspace Sync Test"], cwd=workspace_dir, check=True, capture_output=True, text=True)
        subprocess.run(["git", "add", "."], cwd=workspace_dir, check=True, capture_output=True, text=True)
        subprocess.run(["git", "commit", "-m", "baseline"], cwd=workspace_dir, check=True, capture_output=True, text=True)
        app_path = workspace_dir / "app.py"
        app_path.write_text(app_path.read_text(encoding="utf-8") + "\n# git workspace sync\n", encoding="utf-8")

        workspace_sync = self.sync_workspace(workspace=workspace)

        self.assertEqual(workspace_sync["changed_files_source"], "git")
        self.assertTrue(any(item["path"] == "app.py" and item.get("source") == "git" for item in workspace_sync["changed_files"]))

    def test_workspace_sync_excludes_env_and_does_not_store_env_contents(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        fixture_key = "sk" + "-workspace-sync-secret"
        (Path(workspace["path"]) / ".env").write_text(f"OPENAI_API_KEY={fixture_key}\n", encoding="utf-8")

        workspace_sync = self.sync_workspace(workspace=workspace)
        report_json = (Path(workspace_sync["report_path"]) / "workspace-sync.json").read_text(encoding="utf-8")
        changed_json = (Path(workspace_sync["report_path"]) / "changed-files.json").read_text(encoding="utf-8")
        with sprintos.db() as conn:
            row = conn.execute("SELECT changed_files_json, metadata_json FROM workspace_syncs WHERE id = ?", (workspace_sync["workspace_sync_id"],)).fetchone()

        self.assertFalse(any(item["path"] == ".env" for item in workspace_sync["changed_files"]))
        self.assertIn("excluded it from all outputs", " ".join(workspace_sync["warnings"]))
        self.assertNotIn(fixture_key, report_json)
        self.assertNotIn(fixture_key, changed_json)
        self.assertNotIn(fixture_key, row["changed_files_json"])
        self.assertNotIn(fixture_key, row["metadata_json"])

    def test_workspace_sync_prompt_and_import_note_include_required_sections(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        workspace_dir = Path(workspace["path"])
        readme_path = workspace_dir / "README.md"
        readme_path.write_text(readme_path.read_text(encoding="utf-8") + "\nWorkspace Sync note.\n", encoding="utf-8")

        workspace_sync = self.sync_workspace(workspace=workspace)
        prompt = workspace_sync["codex_followup_prompt"]
        import_note = workspace_sync["sprintos_import_note"]

        self.assertIn("Read AGENTS.md first.", prompt)
        self.assertIn("You are working in this workspace, not SprintOS internals.", prompt)
        self.assertIn("## Changed Files", prompt)
        self.assertIn("## Acceptance Criteria", prompt)
        self.assertIn("## Verification Commands", prompt)
        self.assertIn("## Non-Goals", prompt)
        self.assertIn("Do not expose API keys.", prompt)
        self.assertIn("## Next tiny action", import_note)
        self.assertIn(workspace_sync["next_tiny_action"], import_note)

    def test_workspace_sync_zip_and_safe_file_serving_work(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        workspace_sync = self.sync_workspace(workspace=workspace)
        server = self.start_server()

        zip_payload = self.http_get(server, f"/api/workspace_sync_zip?id={workspace_sync['workspace_sync_id']}")
        with zipfile.ZipFile(io.BytesIO(zip_payload)) as zf:
            self.assertEqual(set(zf.namelist()), set(sprintos.WORKSPACE_SYNC_REPORT_FILES))

        report_text = self.http_get(server, f"/api/workspace_sync_report?id={workspace_sync['workspace_sync_id']}&file=workspace-sync-report.md").decode("utf-8")
        route_text = self.http_get(server, f"/workspace_sync/{workspace_sync['workspace_sync_id']}/workspace-sync-report.md").decode("utf-8")
        stored = json.loads(self.http_get(server, f"/api/workspace_sync?id={workspace_sync['workspace_sync_id']}").decode("utf-8"))

        self.assertIn("Workspace Sync Report", report_text)
        self.assertIn("Workspace Sync Report", route_text)
        self.assertEqual(stored["workspace_sync_id"], workspace_sync["workspace_sync_id"])
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/workspace_sync_report?id={workspace_sync['workspace_sync_id']}&file=../sprintos.py")
        self.assertEqual(exc.exception.code, 400)

    def test_workspace_sync_import_note_can_be_saved_to_progress(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        workspace_sync = self.sync_workspace(workspace=workspace)
        server = self.start_server()

        self.http_post_json(
            server,
            "/api/progress",
            {"project_id": workspace_sync["project_id"], "note": workspace_sync["sprintos_import_note"]},
        )
        refreshed = sprintos.get_project(workspace_sync["project_id"])
        self.assertIsNotNone(refreshed)
        self.assertIn("SprintOS Import Note", refreshed["last_progress_note"])
        self.assertIn("SprintOS Import Note", refreshed["progress_notes"][0]["note"])

    def test_project_markdown_and_zip_exports_include_workspace_sync_context(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        self.sync_workspace(workspace=workspace)

        project = sprintos.get_project(workspace["project_id"])
        self.assertIsNotNone(project)
        _, markdown = sprintos.write_markdown_export(project)
        _, payload = sprintos.build_zip_export(project)

        self.assertIn("## Latest Workspace Sync", markdown)
        self.assertIn("Changed files", markdown)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("workspace-sync.md", names)
            self.assertIn("codex-followup-prompt.md", names)
            self.assertIn("sprintos-import-note.md", names)

    def test_workspace_sync_is_hydrated_on_project(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        workspace_sync = self.sync_workspace(workspace=workspace)

        refreshed = sprintos.get_project(workspace["project_id"])
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed["latest_workspace_sync"]["workspace_sync_id"], workspace_sync["workspace_sync_id"])

    def test_run_verify_mentions_latest_workspace_sync(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="python_stdlib_app"))
        workspace_dir = Path(workspace["path"])
        app_path = workspace_dir / "app.py"
        app_path.write_text("def broken(:\n    pass\n", encoding="utf-8")
        self.sync_workspace(workspace=workspace)
        project = sprintos.get_project(workspace["project_id"])
        self.assertIsNotNone(project)

        verification = sprintos.verify_workspace_artifact(project, sprintos.get_workspace(workspace["workspace_id"], include_prompt=True))
        self.assertNotEqual(verification["status"], "passed")
        self.assertTrue(any(item["name"] == "latest workspace sync is healthy" and item["status"] == "fail" for item in verification["checks"]))

    def test_sync_workspace_api_returns_expected_fields(self) -> None:
        workspace = self.export_workspace(build_pack=self.generate_build_pack(build_target="static_app"))
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/sync_workspace",
            {"project_id": workspace["project_id"], "workspace_id": workspace["workspace_id"], "run_checks": True},
        )

        self.assertIn("workspace_sync_id", payload)
        self.assertIn("sync_status", payload)
        self.assertIn("changed_files", payload)
        self.assertIn("report_url", payload)
        self.assertIn("zip_url", payload)
        self.assertIn("codex_followup_prompt", payload)
        self.assertIn("sprintos_import_note", payload)


class _MovedWorkspaceReleasePackTests:
    def prepare_release_context(
        self,
        *,
        build_target: str = "static_app",
        prototype_type: str = "landing_page",
        run_sync: bool = True,
        run_verification: bool = True,
    ):
        project = self.create_project(
            raw_idea="Build a small local app release candidate for manual testing."
            if build_target != "ai_tool_stub"
            else "Build a local AI text tool that stays mocked/offline by default."
        )
        prototype = self.generate_prototype(project, prototype_type)
        deploy_pack = self.generate_deploy_pack(project, prototype, hosting_target="static") if build_target == "static_app" else None
        build_pack = self.generate_build_pack(project, prototype, deploy_pack=deploy_pack, build_target=build_target)
        workspace = self.export_workspace(project=project, build_pack=build_pack)
        if run_sync:
            self.sync_workspace(project=project, workspace=workspace, run_checks=True)
        if run_verification:
            sprintos.run_project_verification(project["id"], verification_scope="build_pack", build_pack_id=build_pack["id"])
        return project, prototype, build_pack, workspace

    def test_workspace_release_packs_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
        self.assertIn("workspace_release_packs", tables)

    def test_create_workspace_release_fails_clearly_when_no_workspace_exists(self) -> None:
        project = self.create_project()
        server = self.start_server()

        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/api/create_workspace_release",
            data=json.dumps({"project_id": project["id"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(exc.exception.code, 400)
        body = json.loads(exc.exception.read().decode("utf-8"))
        self.assertIn("No workspace exists", body["error"])

    def test_release_type_detection_for_static_app(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="static_app")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)
        self.assertEqual(release_pack["release_type"], "static_site")

    def test_release_type_detection_for_python_stdlib_app(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)
        self.assertEqual(release_pack["release_type"], "local_python_app")

    def test_release_type_detection_for_ai_tool_stub(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="ai_tool_stub", prototype_type="ai_text_tool")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)
        self.assertEqual(release_pack["release_type"], "ai_tool_app")

    def test_release_pack_folder_and_app_copy_are_created(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)
        release_dir = Path(release_pack["path"])

        self.assertTrue(release_dir.exists())
        self.assertEqual(release_dir.parent, self.root / "exports" / "workspace_releases")
        self.assertTrue((release_dir / "app").exists())
        self.assertTrue((release_dir / "app" / "app.py").exists())
        self.assertTrue((release_dir / "app" / "src" / "templates" / "index.html").exists())
        self.assertTrue(any(name == "app/app.py" for name in release_pack["files_copied"]))

    def test_workspace_release_excludes_env_from_app_copy(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="ai_tool_stub", prototype_type="ai_text_tool", run_sync=False, run_verification=False)
        release_secret = "sk" + "-workspace-release-env-secret"
        (Path(workspace["path"]) / ".env").write_text(f"OPENAI_API_KEY={release_secret}\n", encoding="utf-8")

        release_pack = self.create_workspace_release(project=project, workspace=workspace)

        self.assertFalse((Path(release_pack["app_path"]) / ".env").exists())

    def test_workspace_release_excludes_git_internals(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app", run_sync=False, run_verification=False)
        workspace_dir = Path(workspace["path"])
        (workspace_dir / ".git").mkdir()
        (workspace_dir / ".git" / "config").write_text("[core]\nrepositoryformatversion = 0\n", encoding="utf-8")

        release_pack = self.create_workspace_release(project=project, workspace=workspace)

        self.assertFalse((Path(release_pack["app_path"]) / ".git").exists())

    def test_workspace_release_docs_and_manifest_exist(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)
        release_dir = Path(release_pack["path"])

        for name in (
            "RELEASE.md",
            "RELEASE_NOTES.md",
            "TESTER_INSTRUCTIONS.md",
            "DEPLOY_OR_SHARE.md",
            "CODEX_NEXT_PROMPT.md",
            "release-pack.json",
        ):
            self.assertTrue((release_dir / name).exists(), name)

    def test_release_pack_json_contains_required_fields(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)
        payload = json.loads((Path(release_pack["path"]) / "release-pack.json").read_text(encoding="utf-8"))

        for field in (
            "release_pack_id",
            "project_id",
            "workspace_id",
            "created_at",
            "release_label",
            "release_status",
            "release_type",
            "path",
            "app_path",
            "files_copied",
            "files_added",
            "warnings",
            "blockers",
            "run_command",
            "test_command",
            "share_ready",
            "codex_ready",
            "next_tiny_action",
            "tester_message",
            "codex_next_prompt_path",
        ):
            self.assertIn(field, payload)

    def test_static_release_includes_correct_local_run_command(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="static_app")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)
        deploy_text = (Path(release_pack["path"]) / "DEPLOY_OR_SHARE.md").read_text(encoding="utf-8")

        self.assertIn("python3 -m http.server 8080 -d app/src", deploy_text)

    def test_ai_tool_release_documents_mocked_offline_default_and_optional_local_ai(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="ai_tool_stub", prototype_type="ai_text_tool")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)
        deploy_text = (Path(release_pack["path"]) / "DEPLOY_OR_SHARE.md").read_text(encoding="utf-8")
        tester_text = (Path(release_pack["path"]) / "TESTER_INSTRUCTIONS.md").read_text(encoding="utf-8")

        self.assertIn("mocked/offline", deploy_text)
        self.assertIn("Copy `.env.example` to `.env`", deploy_text)
        self.assertIn("Do not commit or share `.env`.", deploy_text)
        self.assertIn("Start the app in mocked/offline mode first.", tester_text)

    def test_workspace_release_zip_includes_release_files_and_app_files(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)

        filename, payload = sprintos.build_workspace_release_zip(release_pack)
        self.assertTrue(filename.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("RELEASE.md", names)
            self.assertIn("TESTER_INSTRUCTIONS.md", names)
            self.assertIn("release-pack.json", names)
            self.assertIn("app/app.py", names)

    def test_workspace_release_file_serving_blocks_path_traversal(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)
        server = self.start_server()

        release_text = self.http_get(server, f"/api/workspace_release_file?id={release_pack['release_pack_id']}&file=RELEASE.md").decode("utf-8")
        stored = json.loads(self.http_get(server, f"/api/workspace_release?id={release_pack['release_pack_id']}").decode("utf-8"))
        route_text = self.http_get(server, f"/workspace_release/{release_pack['release_pack_id']}/TESTER_INSTRUCTIONS.md").decode("utf-8")

        self.assertIn("Release", release_text)
        self.assertEqual(stored["release_pack_id"], release_pack["release_pack_id"])
        self.assertIn("Tester Instructions", route_text)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/workspace_release_file?id={release_pack['release_pack_id']}&file=../sprintos.py")
        self.assertEqual(exc.exception.code, 400)

    def test_project_markdown_export_includes_release_context(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)
        refreshed = sprintos.get_project(project["id"])

        _, markdown = sprintos.write_markdown_export(refreshed)

        self.assertIn("## Latest Workspace Release Pack", markdown)
        self.assertIn(release_pack["release_label"], markdown)
        self.assertIn(release_pack["next_tiny_action"], markdown)

    def test_project_zip_export_includes_release_docs_but_not_release_app_contents(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app")
        self.create_workspace_release(project=project, workspace=workspace)
        refreshed = sprintos.get_project(project["id"])

        _, payload = sprintos.build_zip_export(refreshed)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("workspace-release.md", names)
            self.assertIn("tester-instructions.md", names)
            self.assertIn("deploy-or-share.md", names)
            self.assertIn("release-codex-next-prompt.md", names)
            self.assertNotIn("app/app.py", names)

    def test_workspace_sync_mentions_latest_release_pack(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)
        workspace_sync = self.sync_workspace(project=project, workspace=workspace)
        report_text = (Path(workspace_sync["report_path"]) / "workspace-sync-report.md").read_text(encoding="utf-8")

        self.assertIn("Latest Release Pack", report_text)
        self.assertIn(release_pack["release_label"], report_text)

    def test_run_verify_markdown_suggests_creating_release_pack_when_workspace_passes(self) -> None:
        project, _, build_pack, workspace = self.prepare_release_context(build_target="python_stdlib_app", run_sync=True, run_verification=False)
        sprintos.run_project_verification(project["id"], verification_scope="build_pack", build_pack_id=build_pack["id"])
        refreshed = sprintos.get_project(project["id"])

        markdown = sprintos.verification_markdown(refreshed)
        self.assertIn("Create a Workspace Release Pack next", markdown)

    def test_release_reports_and_zip_do_not_include_fake_api_keys(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app", run_sync=False, run_verification=False)
        release_secret = "sk" + "-workspace-release-secret"
        (Path(workspace["path"]) / ".env").write_text(f"OPENAI_API_KEY={release_secret}\n", encoding="utf-8")

        release_pack = self.create_workspace_release(project=project, workspace=workspace)
        report_text = (Path(release_pack["path"]) / "RELEASE.md").read_text(encoding="utf-8")
        notes_text = (Path(release_pack["path"]) / "RELEASE_NOTES.md").read_text(encoding="utf-8")
        manifest_text = (Path(release_pack["path"]) / "release-pack.json").read_text(encoding="utf-8")
        _, payload = sprintos.build_workspace_release_zip(release_pack)

        self.assertNotIn(release_secret, report_text)
        self.assertNotIn(release_secret, notes_text)
        self.assertNotIn(release_secret, manifest_text)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            for name in zf.namelist():
                self.assertNotIn(release_secret, zf.read(name).decode("utf-8"))

    def test_project_hydration_includes_latest_workspace_release_pack(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app")
        release_pack = self.create_workspace_release(project=project, workspace=workspace)

        refreshed = sprintos.get_project(project["id"])
        self.assertEqual(refreshed["latest_workspace_release_pack"]["release_pack_id"], release_pack["release_pack_id"])

    def test_create_workspace_release_endpoint_returns_expected_fields(self) -> None:
        project, _, _, workspace = self.prepare_release_context(build_target="python_stdlib_app")
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/create_workspace_release",
            {"project_id": project["id"], "workspace_id": workspace["workspace_id"], "release_label": "endpoint-rc"},
        )

        self.assertIn("release_pack_id", payload)
        self.assertIn("release_status", payload)
        self.assertIn("release_type", payload)
        self.assertIn("path", payload)
        self.assertIn("app_path", payload)
        self.assertIn("zip_url", payload)
        self.assertIn("report_url", payload)
        self.assertIn("tester_instructions_url", payload)
        self.assertIn("deploy_or_share_url", payload)
        self.assertIn("codex_next_prompt", payload)
        self.assertIn("tester_message", payload)
        self.assertIn("next_tiny_action", payload)


class _MovedPipelineRunTests:
    def test_pipeline_runs_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
        self.assertIn("pipeline_runs", tables)

    def test_auto_prototype_type_selection_is_deterministic(self) -> None:
        ai_project = self.create_project(raw_idea="AI writing assistant that summarizes messy notes into clearer drafts.")
        calc_project = self.create_project(raw_idea="ROI calculator for pricing, budgets, and estimates.")
        quiz_project = self.create_project(raw_idea="A recommender quiz funnel for onboarding and diagnostic questions.")
        generic_project = self.create_project(raw_idea="A local-first idea landing page for one simple test.")

        self.assertEqual(sprintos.auto_select_prototype_type(ai_project), "ai_text_tool")
        self.assertEqual(sprintos.auto_select_prototype_type(calc_project), "calculator")
        self.assertEqual(sprintos.auto_select_prototype_type(quiz_project), "quiz_funnel")
        self.assertEqual(sprintos.auto_select_prototype_type(generic_project), "landing_page")

    def test_auto_build_target_selection_is_deterministic(self) -> None:
        ai_project = self.create_project(raw_idea="AI writing tool for summarizing text fast.")
        generic_project = self.create_project(raw_idea="Simple static validation page for a local service.")
        complex_project = self.create_project(raw_idea="Enterprise multi-tenant workflow engine SaaS for several teams.")

        self.assertEqual(sprintos.auto_select_build_target(ai_project, "ai_text_tool", "codex_build_ready"), "ai_tool_stub")
        self.assertEqual(sprintos.auto_select_build_target(generic_project, "landing_page", "public_static_test"), "static_app")
        self.assertEqual(sprintos.auto_select_build_target(complex_project, "landing_page", "codex_build_ready"), "codex_repo_brief")

    def test_running_pipeline_creates_artifacts_and_report_folder(self) -> None:
        project = self.create_project(raw_idea="Build a local static product test page for a small execution tool.")

        pipeline_run = self.generate_pipeline(project, pipeline_goal="public_static_test")
        report_dir = Path(pipeline_run["report_path"])
        refreshed = sprintos.get_project(project["id"])

        self.assertEqual(pipeline_run["status"], "completed")
        self.assertTrue(report_dir.exists())
        self.assertTrue(pipeline_run["prototype_id"])
        self.assertTrue(pipeline_run["deploy_pack_id"])
        self.assertTrue(pipeline_run["build_pack_id"])
        self.assertEqual(set(path.name for path in report_dir.iterdir()), set(sprintos.PIPELINE_REPORT_FILES))
        self.assertIsNotNone(refreshed)
        self.assertEqual(refreshed["latest_pipeline_run"]["pipeline_run_id"], pipeline_run["pipeline_run_id"])
        self.assertIsNotNone(refreshed["latest_prototype"])
        self.assertIsNotNone(refreshed["latest_deploy_pack"])
        self.assertIsNotNone(refreshed["latest_build_pack"])

    def test_pipeline_report_folder_includes_required_files(self) -> None:
        pipeline_run = self.generate_pipeline()
        report_dir = Path(pipeline_run["report_path"])
        self.assertEqual(set(path.name for path in report_dir.iterdir()), set(sprintos.PIPELINE_REPORT_FILES))
        report_text = (report_dir / "pipeline-report.md").read_text(encoding="utf-8")
        artifact_index = (report_dir / "artifact-index.md").read_text(encoding="utf-8")
        next_action = (report_dir / "next-action.md").read_text(encoding="utf-8")
        checklist = (report_dir / "manual-test-checklist.md").read_text(encoding="utf-8")

        self.assertIn("## Steps Completed", report_text)
        self.assertIn("## Next Tiny Action", report_text)
        self.assertIn("Artifact Index", artifact_index)
        self.assertTrue(next_action.strip())
        self.assertIn("Open preview", checklist)
        self.assertIn("Import feedback back into SprintOS", checklist)

    def test_pipeline_run_json_includes_warnings_blockers_and_codex_task(self) -> None:
        pipeline_run = self.generate_pipeline()
        payload = json.loads((Path(pipeline_run["report_path"]) / "pipeline-run.json").read_text(encoding="utf-8"))

        self.assertIn("warnings", payload)
        self.assertIn("blockers", payload)
        self.assertTrue(payload["next_tiny_action"])
        self.assertTrue(payload["suggested_first_codex_task"])

    def test_pipeline_skips_deploy_pack_when_readiness_has_blockers_but_still_builds(self) -> None:
        project = self.create_project(raw_idea="Simple static app idea that should still build locally.")
        original_write_prototype = sprintos.write_prototype_package

        def broken_write_prototype_package(current_project, prototype_type):
            prototype = original_write_prototype(current_project, prototype_type)
            app_js = Path(prototype["path"]) / "app.js"
            app_js.write_text(app_js.read_text(encoding="utf-8") + '\nfetch("https://example.com");\n', encoding="utf-8")
            return sprintos.get_prototype(prototype["id"], include_prompt=True)

        with mock.patch("sprintos.write_prototype_package", side_effect=broken_write_prototype_package):
            rerun = self.generate_pipeline(project, prototype_type="landing_page", build_target="static_app")

        self.assertEqual(rerun["status"], "partial")
        self.assertTrue(rerun["prototype_id"])
        self.assertFalse(rerun["deploy_pack_id"])
        self.assertTrue(rerun["build_pack_id"])
        self.assertTrue(any("fetch()" in item or "external URL" in item for item in rerun["blockers"]))

    def test_pipeline_zip_includes_only_report_files(self) -> None:
        pipeline_run = self.generate_pipeline()
        filename, payload = sprintos.build_pipeline_report_zip(pipeline_run)

        self.assertTrue(filename.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertEqual(set(zf.namelist()), set(sprintos.PIPELINE_REPORT_FILES))

    def test_pipeline_file_serving_blocks_path_traversal(self) -> None:
        pipeline_run = self.generate_pipeline()
        server = self.start_server()

        report = self.http_get(server, f"/api/pipeline_report?id={pipeline_run['pipeline_run_id']}&file=pipeline-report.md").decode("utf-8")
        self.assertIn("Pipeline Report", report)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/pipeline_report?id={pipeline_run['pipeline_run_id']}&file=../sprintos.py")
        self.assertEqual(exc.exception.code, 400)

    def test_project_markdown_export_includes_pipeline_context(self) -> None:
        project = self.create_project()
        self.generate_pipeline(project)

        _, markdown = sprintos.write_markdown_export(sprintos.get_project(project["id"]))

        self.assertIn("## Latest Pipeline Run", markdown)
        self.assertIn("## Codex Next Prompt", markdown)
        self.assertIn("Next tiny action", markdown)

    def test_project_zip_export_includes_pipeline_files(self) -> None:
        project = self.create_project()
        self.generate_pipeline(project)

        _, payload = sprintos.build_zip_export(sprintos.get_project(project["id"]))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("pipeline-run.md", names)
            self.assertIn("codex-next-prompt.md", names)
            self.assertIn("share-message.md", names)

    def test_pipeline_endpoints_return_expected_fields(self) -> None:
        project = self.create_project()
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/run_testable_pipeline",
            {"project_id": project["id"]},
        )

        self.assertIn("pipeline_run_id", payload)
        self.assertIn("report_url", payload)
        self.assertIn("next_tiny_action", payload)
        self.assertIn("preview_urls", payload)
        self.assertIn("zip_urls", payload)
        run_payload = json.loads(self.http_get(server, f"/api/pipeline_run?id={payload['pipeline_run_id']}").decode("utf-8"))
        self.assertEqual(run_payload["pipeline_run_id"], payload["pipeline_run_id"])


class _MovedQuickLaunchTests:
    def app_file_generation_payload(self) -> dict:
        return {
            "app_name": "Quick Launch Preview App",
            "app_type": "static_app",
            "short_description": "A local app with one visible scoring flow.",
            "user_flow": [
                "Paste a business idea.",
                "Click Score Idea.",
                "Review the visible score, risks, smallest testable version, and next action.",
            ],
            "files": [
                {
                    "filename": "index.html",
                    "content": """<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" /><title>Quick Launch Preview App</title><link rel=\"stylesheet\" href=\"style.css\" /></head><body><main data-app-shape=\"business_idea_scorer\"><textarea id=\"idea-input\" data-template-marker=\"main-input\"></textarea><button id=\"score-idea\" data-template-marker=\"primary-action\">Score Idea</button><div id=\"result\" class=\"result\" data-template-marker=\"result-output\"><div id=\"idea-score\">0</div><ul id=\"idea-risks\" data-template-marker=\"risk_breakdown\"><li>No score yet.</li></ul><div id=\"idea-smallest-test\" data-template-marker=\"smallest-testable-version\">No score yet.</div><div id=\"idea-next-action\" data-template-marker=\"next-action\">No score yet.</div></div><script src=\"app.js\"></script></main></body></html>""",
                },
                {"filename": "style.css", "content": "body{font-family:sans-serif;padding:24px;}textarea{width:100%;min-height:120px;} .result{margin-top:16px;}"},
                {
                    "filename": "app.js",
                    "content": "function scoreIdea(){const idea=document.getElementById('idea-input').value.trim();const score=idea.length>20?'6':'3';document.getElementById('idea-score').textContent=score;document.getElementById('idea-risks').innerHTML='<li>Demand risk: medium</li><li>Execution risk: high</li>';document.getElementById('idea-smallest-test').textContent='Smallest testable version: rewrite the offer and show it to one target user.';document.getElementById('idea-next-action').textContent='Next action: schedule one validation conversation.';}document.getElementById('score-idea').addEventListener('click', scoreIdea);",
                },
                {"filename": "README.md", "content": "# Quick Launch Preview App\n\nRun `python3 -m http.server 8080` and open `index.html`."},
                {"filename": "TEST_PLAN.md", "content": "# Test Plan\n\n- Open the app.\n- Click Score Idea.\n- Confirm the result updates with a score, risks, smallest testable version, and next action."},
            ],
            "run_instructions": "Run `python3 -m http.server 8080` and open `index.html`.",
            "test_instructions": "Click the main button and confirm the result changes locally.",
            "codex_next_prompt": "Preserve the working flow and improve one small part only.",
            "limitations": ["Prototype only."],
            "mocked_parts": ["The scoring logic is intentionally simple."],
        }

    def test_quick_launches_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }
        self.assertIn("quick_launches", tables)

    def test_quick_launch_rejects_empty_raw_idea(self) -> None:
        with self.assertRaises(ValueError) as exc:
            sprintos.run_quick_launch(raw_idea="")
        self.assertIn("raw_idea is required", str(exc.exception))

    def test_quick_launch_creates_project_sprint_and_pipeline(self) -> None:
        quick_launch = self.generate_quick_launch()
        project = sprintos.get_project(quick_launch["project_id"])

        self.assertIsNotNone(project)
        self.assertTrue(project["sprint"]["sprint_plan"])
        self.assertEqual(project["status"], "active")
        self.assertEqual(project["latest_quick_launch"]["quick_launch_id"], quick_launch["quick_launch_id"])
        self.assertEqual(project["latest_pipeline_run"]["pipeline_run_id"], quick_launch["pipeline_run_id"])
        self.assertEqual(quick_launch["status"], project["latest_pipeline_run"]["status"])

    def test_create_app_result_surfaces_open_app_preview(self) -> None:
        quick_launch = self.generate_quick_launch(raw_idea="Build a business idea scoring app that feels like a real local tool.")
        project = sprintos.get_project(quick_launch["project_id"])
        app_state = project["app_state_summary"]

        self.assertEqual(app_state["primary_action"]["label"], "Open App Preview")
        self.assertEqual(app_state["generated_by"], "Offline")

    def test_ai_failure_in_template_mode_still_creates_offline_app(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-template-fallback-test"

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
        self.assertIsNotNone(project["latest_prototype"])
        self.assertTrue(Path(project["latest_prototype"]["path"], "index.html").exists())
        self.assertEqual(project["app_state_summary"]["primary_action"]["label"], "Open App Preview")

    def test_report_only_ai_failure_creates_failure_report_without_app_files(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-report-only-test"
        os.environ["SPRINTOS_APP_GENERATION_FALLBACK_MODE"] = "report_only"

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
        self.assertTrue(quick_launch["ai_generation_failed"])
        self.assertEqual(project["latest_prototype"], None)
        self.assertFalse(list((sprintos.EXPORT_DIR / "prototypes").glob("*")))
        report_dir = Path(quick_launch["failure_report_path"])
        self.assertTrue((report_dir / "app-generation-failure.md").exists())
        self.assertTrue((report_dir / "failure-summary.json").exists())
        self.assertTrue((report_dir / "retry-instructions.md").exists())
        self.assertTrue((report_dir / "sanitized-diagnostics.md").exists())
        summary = json.loads((report_dir / "failure-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["provider"], "openai")
        self.assertEqual(summary["model"], DEFAULT_OPENAI_MODEL)
        self.assertEqual(summary["failure_category"], "provider_timeout")
        self.assertEqual(summary["fallback_mode"], "report_only")
        self.assertFalse(summary["fallback_used"])
        self.assertIn("validation_details", summary)
        self.assertIn("Retry Instructions", (report_dir / "retry-instructions.md").read_text(encoding="utf-8"))
        encoded = "\n".join(path.read_text(encoding="utf-8") for path in report_dir.iterdir())
        self.assertNotIn("Using local template", encoded)
        self.assertNotIn("sk-openai-report-only-test", encoded)

    def test_report_only_schema_failure_keeps_safe_validation_details(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-report-schema-test"
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
        self.assertTrue(quick_launch["ai_generation_failed"])
        self.assertIsNone(project["latest_prototype"])
        self.assertFalse(list((sprintos.EXPORT_DIR / "prototypes").glob("*")))
        summary = json.loads((Path(quick_launch["failure_report_path"]) / "failure-summary.json").read_text(encoding="utf-8"))
        self.assertEqual(summary["failure_category"], "missing_required_files")
        self.assertIn("TEST_PLAN.md", summary["validation_details"]["missing_required_files"])
        encoded = "\n".join(path.read_text(encoding="utf-8") for path in Path(quick_launch["failure_report_path"]).iterdir())
        self.assertNotIn("sk-openai-report-schema-test", encoded)

    def test_report_only_create_app_response_and_state_show_failure_actions(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-report-response-test"
        server = self.start_server()

        with mock.patch(
            "sprintos_core.ai_provider.call_openai_responses",
            return_value=fake_provider_result(
                ok=False,
                error="OpenAI HTTP error 503: service unavailable",
                provider="openai",
                model=DEFAULT_OPENAI_MODEL,
                used_ai=False,
                fallback_reason="openai_http_error",
                task_name="app_file_generation",
            ),
        ):
            payload = self.http_post_json(
                server,
                "/api/quick_launch",
                {
                    "raw_idea": "Build a business idea scoring app that feels like a real local tool.",
                    "generation_mode": "ai",
                    "fallback_mode": "report_only",
                },
            )

        project = sprintos.get_project(payload["project_id"])
        app_state = project["app_state_summary"]
        action_labels = [item["label"] for item in app_state["secondary_actions"]]
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["status"], "ai_generation_failed")
        self.assertFalse(payload["fallback_used"])
        self.assertEqual(payload["failure_category"], "provider_unavailable")
        self.assertEqual(app_state["state"], "ai_generation_failed")
        self.assertEqual(app_state["label"], "AI Generation Failed")
        self.assertIn("No app was created", app_state["app_generation_status"]["summary"])
        self.assertNotIn("Using local template", app_state["app_generation_status"]["summary"])
        self.assertFalse(app_state["what_exists"]["preview_available"])
        self.assertFalse(app_state["preview_url"])
        self.assertEqual(app_state["primary_action"]["label"], "Retry Create App")
        self.assertNotIn("Open App Preview", action_labels)
        self.assertIn("Open Failure Report", action_labels)
        self.assertIn("Switch to Local Template Fallback", action_labels)
        self.assertIn("AI app generation stopped", sprintos.INDEX_HTML)

    def test_create_app_download_actions_use_app_and_source_pack_labels(self) -> None:
        quick_launch = self.generate_quick_launch(raw_idea="Build a business idea scoring app that feels like a real local tool.")
        project = sprintos.get_project(quick_launch["project_id"])
        app_state = project["app_state_summary"]
        zip_urls = quick_launch["zip_urls"]

        download_app = app_state["actions"]["download_package"]
        download_source = app_state["actions"]["download_source_pack"]

        self.assertEqual(download_app["label"], "Download App")
        self.assertEqual(download_app["summary"], "Runnable local app package for previewing and sharing the current draft.")
        self.assertIn("index.html", download_app["primary_files"])
        self.assertEqual(download_app["url"], zip_urls["deploy_pack"])
        self.assertIn("/api/deploy_pack_zip", download_app["url"])
        self.assertEqual(download_source["label"], "Download Source Pack")
        self.assertEqual(download_source["summary"], "Editable source/Codex package for inspecting or continuing the app locally.")
        self.assertIn("CODEX_BUILD_PROMPT.md", download_source["primary_files"])
        self.assertEqual(download_source["url"], zip_urls["build_pack"])
        self.assertIn("/api/build_pack_zip", download_source["url"])
        self.assertEqual(app_state["download_app_url"], zip_urls["deploy_pack"])
        self.assertEqual(app_state["download_source_pack_url"], zip_urls["build_pack"])
        self.assertEqual(app_state["download_package_url"], zip_urls["deploy_pack"])

    def test_app_and_source_pack_zips_exclude_env_and_secret_files(self) -> None:
        quick_launch = self.generate_quick_launch(raw_idea="Build a business idea scoring app that feels like a real local tool.")
        project = sprintos.get_project(quick_launch["project_id"])
        deploy_pack = project["latest_deploy_pack"]
        build_pack = project["latest_build_pack"]
        fixture_key = "sk" + "-download-clarity-secret"

        Path(deploy_pack["path"], ".env").write_text(f"OPENAI_API_KEY={fixture_key}\n", encoding="utf-8")
        Path(build_pack["path"], ".env").write_text(f"OPENAI_API_KEY={fixture_key}\n", encoding="utf-8")

        for _, payload in (sprintos.build_deploy_pack_zip(deploy_pack), sprintos.build_build_pack_zip(build_pack)):
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                names = set(zf.namelist())
                self.assertFalse(any(name == ".env" or name.startswith(".env.") for name in names))
                for name in names:
                    self.assertNotIn(fixture_key, zf.read(name).decode("utf-8", errors="ignore"))

    def test_app_draft_hero_state_reports_provider_when_ai_is_used(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-quick-launch-test"
        payload = self.app_file_generation_payload()
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
            quick_launch = self.generate_quick_launch(raw_idea="Build a business idea scoring app that feels like a real local tool.")
        project = sprintos.get_project(quick_launch["project_id"])
        app_state = project["app_state_summary"]

        self.assertEqual(app_state["generated_by"], "OpenAI")
        self.assertEqual(app_state["primary_action"]["label"], "Open App Preview")
        self.assertIn("TEST_PLAN.md", app_state["technical_details"]["generated_files"])

    def test_quick_launch_persists_row_and_project_list_includes_created_project(self) -> None:
        quick_launch = self.generate_quick_launch(raw_idea="Quick launch a local static offer page for messy startup ideas.")
        with sprintos.db() as conn:
            row = conn.execute(
                "SELECT project_id, pipeline_run_id, launch_goal, status FROM quick_launches WHERE id = ?",
                (quick_launch["quick_launch_id"],),
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["project_id"], quick_launch["project_id"])
        self.assertEqual(row["pipeline_run_id"], quick_launch["pipeline_run_id"])
        self.assertEqual(row["launch_goal"], "codex_build_ready")
        self.assertEqual(row["status"], quick_launch["status"])
        self.assertIn(quick_launch["project_id"], [item["id"] for item in sprintos.list_projects()])

    def test_quick_launch_report_folder_includes_required_files(self) -> None:
        quick_launch = self.generate_quick_launch()
        report_dir = Path(quick_launch["report_path"])

        self.assertTrue(report_dir.exists())
        self.assertEqual(set(path.name for path in report_dir.iterdir()), set(sprintos.QUICK_LAUNCH_REPORT_FILES))
        report_text = (report_dir / "quick-launch-report.md").read_text(encoding="utf-8")
        next_action = (report_dir / "next-action.md").read_text(encoding="utf-8")
        share_message = (report_dir / "share-message.md").read_text(encoding="utf-8")

        self.assertIn("## Launch Goal", report_text)
        self.assertIn("## Pipeline Run ID", report_text)
        self.assertIn("## Suggested First Codex Task", report_text)
        self.assertTrue(next_action.strip())
        self.assertTrue(share_message.strip())

    def test_quick_launch_bundle_json_includes_required_fields(self) -> None:
        quick_launch = self.generate_quick_launch()
        bundle = json.loads((Path(quick_launch["report_path"]) / "launch-bundle.json").read_text(encoding="utf-8"))

        self.assertEqual(bundle["quick_launch_id"], quick_launch["quick_launch_id"])
        self.assertEqual(bundle["project_id"], quick_launch["project_id"])
        self.assertEqual(bundle["pipeline_run_id"], quick_launch["pipeline_run_id"])
        self.assertEqual(bundle["status"], quick_launch["status"])
        self.assertIn("warnings", bundle)
        self.assertIn("blockers", bundle)
        self.assertTrue(bundle["next_tiny_action"])
        self.assertTrue(bundle["suggested_first_codex_task"])

    def test_quick_launch_zip_includes_report_files_only(self) -> None:
        quick_launch = self.generate_quick_launch()
        filename, payload = sprintos.build_quick_launch_zip(quick_launch)

        self.assertTrue(filename.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            self.assertEqual(set(zf.namelist()), set(sprintos.QUICK_LAUNCH_REPORT_FILES))

    def test_quick_launch_file_serving_blocks_path_traversal(self) -> None:
        quick_launch = self.generate_quick_launch()
        server = self.start_server()

        report = self.http_get(server, f"/api/quick_launch_report?id={quick_launch['quick_launch_id']}&file=quick-launch-report.md").decode("utf-8")
        self.assertIn("Quick Launch Report", report)
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/quick_launch_report?id={quick_launch['quick_launch_id']}&file=../sprintos.py")
        self.assertEqual(exc.exception.code, 400)

    def test_project_markdown_and_zip_exports_include_quick_launch_context(self) -> None:
        quick_launch = self.generate_quick_launch()
        project = sprintos.get_project(quick_launch["project_id"])
        self.assertIsNotNone(project)

        _, markdown = sprintos.write_markdown_export(project)
        _, payload = sprintos.build_zip_export(project)

        self.assertIn("## Latest Quick Launch", markdown)
        self.assertIn("## Quick Launch Codex Next Prompt", markdown)
        self.assertIn("## Quick Launch Share Message", markdown)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("quick-launch.md", names)
            self.assertIn("quick-launch-codex-next-prompt.md", names)
            self.assertIn("quick-launch-share-message.md", names)

    def test_quick_launch_codex_prompt_references_build_pack_when_available(self) -> None:
        quick_launch = self.generate_quick_launch()
        prompt = quick_launch["codex_next_prompt"]

        self.assertIn("Build Pack path:", prompt)
        self.assertIn("CODEX_BUILD_PROMPT.md", prompt)
        self.assertIn("Suggested first Codex task:", prompt)

    def test_quick_launch_endpoints_return_expected_fields(self) -> None:
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/quick_launch",
            {
                "raw_idea": "Build a quick local-first package that turns a rough idea into a testable static flow.",
                "launch_goal": "public_static_test",
                "timebox_minutes": 60,
                "end_output": "a static test package",
                "prototype_type": "auto",
                "hosting_target": "static",
                "build_target": "auto",
            },
        )

        self.assertIn("quick_launch_id", payload)
        self.assertIn("project_id", payload)
        self.assertIn("pipeline_run_id", payload)
        self.assertIn("report_url", payload)
        self.assertIn("zip_url", payload)
        self.assertIn("preview_urls", payload)
        self.assertIn("zip_urls", payload)
        stored = json.loads(self.http_get(server, f"/api/quick_launch?id={payload['quick_launch_id']}").decode("utf-8"))
        self.assertEqual(stored["quick_launch_id"], payload["quick_launch_id"])
        zip_payload = self.http_get(server, f"/api/quick_launch_zip?id={payload['quick_launch_id']}")
        with zipfile.ZipFile(io.BytesIO(zip_payload)) as zf:
            self.assertEqual(set(zf.namelist()), set(sprintos.QUICK_LAUNCH_REPORT_FILES))

    def test_quick_launch_endpoint_rejects_invalid_targets(self) -> None:
        server = self.start_server()

        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_post_json(
                server,
                "/api/quick_launch",
                {
                    "raw_idea": "Build a quick launch flow.",
                    "timebox_minutes": 45,
                    "hosting_target": "unknown-host",
                },
            )

        self.assertEqual(exc.exception.code, 400)
        body = exc.exception.read().decode("utf-8")
        self.assertTrue("timebox_minutes must be one of 30, 60, 120, 240" in body or "Unsupported hosting target" in body)

    def test_codex_handoff_includes_latest_quick_launch_context(self) -> None:
        quick_launch = self.generate_quick_launch()
        project = sprintos.get_project(quick_launch["project_id"])
        self.assertIsNotNone(project)
        handoff = project["sprint"]["codex_handoff"]["content"]

        self.assertIn("Latest Quick Launch goal/status", handoff)
        self.assertIn(quick_launch["launch_goal"], handoff)
        self.assertIn(quick_launch["status"], handoff)
        self.assertIn(quick_launch["report_path"], handoff)


class _MovedVerificationRunTests:
    def app_file_generation_payload(self) -> dict:
        return {
            "app_name": "Verification Preview App",
            "app_type": "static_app",
            "short_description": "A deterministic app with one safe visible scoring flow.",
            "user_flow": [
                "Paste a business idea.",
                "Click Score Idea.",
                "Review the visible score, risks, smallest testable version, and next action.",
            ],
            "files": [
                {
                    "filename": "index.html",
                    "content": """<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\" /><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" /><title>Verification Preview App</title><link rel=\"stylesheet\" href=\"style.css\" /></head><body><main data-app-shape=\"business_idea_scorer\"><textarea id=\"idea-input\" data-template-marker=\"main-input\"></textarea><button id=\"score-idea\" data-template-marker=\"primary-action\">Score Idea</button><div id=\"result\" class=\"result\" data-template-marker=\"result-output\"><div id=\"idea-score\">0</div><ul id=\"idea-risks\" data-template-marker=\"risk_breakdown\"><li>No score yet.</li></ul><div id=\"idea-smallest-test\" data-template-marker=\"smallest-testable-version\">No score yet.</div><div id=\"idea-next-action\" data-template-marker=\"next-action\">No score yet.</div></div><script src=\"app.js\"></script></main></body></html>""",
                },
                {"filename": "style.css", "content": "body{font-family:sans-serif;padding:24px;}textarea{width:100%;min-height:120px;} .result{margin-top:16px;}"},
                {
                    "filename": "app.js",
                    "content": "function scoreIdea(){const idea=document.getElementById('idea-input').value.trim();const score=idea.length>20?'8':'4';document.getElementById('idea-score').textContent=score;document.getElementById('idea-risks').innerHTML='<li>Demand risk: medium</li><li>Execution risk: high</li>';document.getElementById('idea-smallest-test').textContent='Smallest testable version: interview 3 target users.';document.getElementById('idea-next-action').textContent='Next action: book one validation call.';}document.getElementById('score-idea').addEventListener('click', scoreIdea);",
                },
                {"filename": "README.md", "content": "# Verification Preview App\n\nRun `python3 -m http.server 8080` and open `index.html`."},
                {"filename": "TEST_PLAN.md", "content": "# Test Plan\n\n- Open the app.\n- Click Score Idea.\n- Confirm the result updates with a score, risks, smallest testable version, and next action."},
            ],
            "run_instructions": "Run `python3 -m http.server 8080` and open `index.html`.",
            "test_instructions": "Click the main button and confirm the result changes locally.",
            "codex_next_prompt": "Preserve the working flow and improve one small part only.",
            "limitations": ["Prototype only."],
            "mocked_parts": ["The scoring logic is intentionally simple."],
        }

    def test_verification_runs_table_is_created(self) -> None:
        with sprintos.db() as conn:
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            }

        self.assertIn("verification_runs", tables)

    def test_prototype_verification_passes_for_generated_package(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")

        verification = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])

        self.assertEqual(verification["status"], "passed")
        self.assertEqual(verification["verification_scope"], "prototype")
        self.assertTrue(verification["share_ready"])
        self.assertFalse(verification["codex_ready"])
        self.assertFalse(verification["blockers"])

    def test_prototype_verification_fails_when_required_file_is_missing(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        (Path(prototype["path"]) / "style.css").unlink()

        verification = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])

        self.assertEqual(verification["status"], "failed")
        self.assertFalse(verification["share_ready"])
        self.assertTrue(any("style.css" in item for item in verification["blockers"]))

    def test_prototype_verification_catches_external_network_markers(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        app_js = Path(prototype["path"]) / "app.js"
        app_js.write_text(app_js.read_text(encoding="utf-8") + '\nfetch("https://example.com/api");\n', encoding="utf-8")

        verification = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])

        self.assertEqual(verification["status"], "failed")
        self.assertTrue(any("fetch()" in item or "external URL" in item for item in verification["blockers"]))

    def test_run_verify_catches_browser_side_fetch_to_provider(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        app_js = Path(prototype["path"]) / "app.js"
        app_js.write_text(
            "document.getElementById('waitlist-submit').addEventListener('click', () => fetch('https://api.openai.com/v1/responses'));",
            encoding="utf-8",
        )

        verification = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])

        self.assertEqual(verification["status"], "failed")
        self.assertTrue(any("provider endpoint" in item or "fetch()" in item for item in verification["blockers"]))

    def test_run_verify_passes_safe_ai_generated_app(self) -> None:
        os.environ["SPRINTOS_AI_PROVIDER"] = "openai"
        os.environ["SPRINTOS_AI_ENABLED"] = "true"
        os.environ["OPENAI_API_KEY"] = "sk-openai-verification-test"
        payload = self.app_file_generation_payload()
        project = self.create_project(raw_idea="Build a business idea scoring app that feels like a real local tool.")
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
            prototype = self.generate_prototype(project, "landing_page", generation_mode="auto")

        verification = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])

        self.assertEqual(verification["status"], "passed")
        self.assertFalse(verification["blockers"])

    def test_app_specific_verification_checks_business_idea_scorer_outputs(self) -> None:
        project = self.create_project(raw_idea="Build a business idea scorer that evaluates startup ideas.")
        prototype = self.generate_prototype(project, "landing_page", generation_mode="offline")
        passed = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])
        passed_checks = passed["metadata"]["checks"]

        self.assertEqual(passed["metadata"].get("app_shape"), "business_idea_scorer")
        self.assertTrue(any(item["name"] == "business idea scorer: risk output exists" and item["status"] == "pass" for item in passed_checks))

        package_dir = Path(prototype["path"])
        (package_dir / "index.html").write_text(
            """<!doctype html><html><head><link rel="stylesheet" href="style.css" /></head><body><textarea id="idea-input"></textarea><button id="score-idea">Score Idea</button><section id="result" class="result">Score appears here.</section><script src="app.js"></script></body></html>""",
            encoding="utf-8",
        )
        (package_dir / "app.js").write_text(
            "document.getElementById('score-idea').addEventListener('click', function(){document.getElementById('result').textContent='Score: 7/10';});",
            encoding="utf-8",
        )

        failed = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])
        checks = failed["metadata"]["checks"]

        self.assertEqual(failed["status"], "failed")
        self.assertTrue(any(item["name"] == "business idea scorer: risk output exists" and item["status"] == "fail" for item in checks))
        self.assertTrue(any("Business idea scorer needs an `idea-smallest-test` output" in item for item in failed["blockers"]))

    def test_app_specific_verification_checks_budget_calculator_shape(self) -> None:
        project = self.create_project(raw_idea="Build a personal budget calculator for income, expenses, and monthly savings.")
        prototype = self.generate_prototype(project, "calculator", generation_mode="offline")
        passed = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])
        passed_checks = passed["metadata"]["checks"]

        self.assertEqual(passed["metadata"].get("app_shape"), "budget_calculator")
        self.assertTrue(any(item["name"] == "budget calculator: income and expense input markers exist" and item["status"] == "pass" for item in passed_checks))

        package_dir = Path(prototype["path"])
        index_path = package_dir / "index.html"
        index_path.write_text(
            index_path.read_text(encoding="utf-8")
            .replace('type="number"', 'type="text"', 1)
            .replace('type="number"', 'type="text"', 1),
            encoding="utf-8",
        )

        failed = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])
        checks = failed["metadata"]["checks"]

        self.assertEqual(failed["status"], "failed")
        self.assertTrue(any(item["name"] == "budget calculator: income and expense input markers exist" and item["status"] == "fail" for item in checks))
        self.assertTrue(any("Budget calculator needs `budget-income` and expense input markers" in item for item in failed["blockers"]))

    def test_app_specific_verification_checks_flashcard_helper_outputs_and_local_note(self) -> None:
        project = self.create_project(raw_idea="Build a study flashcard helper where students paste notes and get cards.")
        prototype = self.generate_prototype(project, "ai_text_tool", generation_mode="offline")
        passed = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])
        passed_checks = passed["metadata"]["checks"]

        self.assertEqual(passed["metadata"].get("app_shape"), "flashcard_helper")
        self.assertTrue(any(item["name"] == "flashcard helper: card output exists" and item["status"] == "pass" for item in passed_checks))

        package_dir = Path(prototype["path"])
        (package_dir / "index.html").write_text(
            """<!doctype html><html><head><link rel="stylesheet" href="style.css" /></head><body><textarea id="notes-input" data-template-marker="main-input"></textarea><button id="build-cards" data-template-marker="primary-action">Build Flashcards</button><section id="card-output" class="result" data-template-marker="flashcard-cards">Cards appear here.</section><script src="app.js"></script></body></html>""",
            encoding="utf-8",
        )
        (package_dir / "README.md").write_text("# Study Card Builder\n\nRun locally.\n", encoding="utf-8")

        warned = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])
        checks = warned["metadata"]["checks"]

        self.assertNotEqual(warned["status"], "passed")
        self.assertTrue(any(item["name"] == "flashcard helper: mocked/local limitation note exists" and item["status"] == "warn" for item in checks))
        self.assertTrue(any("Flashcard helper should explain that card generation is local/mocked" in item for item in warned["warnings"]))

        (package_dir / "index.html").write_text(
            """<!doctype html><html><head><link rel="stylesheet" href="style.css" /></head><body><textarea id="notes-input"></textarea><button id="build-cards">Build Flashcards</button><section id="plain-output" class="result">Output appears here.</section><script src="app.js"></script></body></html>""",
            encoding="utf-8",
        )
        (package_dir / "app.js").write_text(
            "document.getElementById('build-cards').addEventListener('click', function(){document.getElementById('plain-output').textContent='Built output.';});",
            encoding="utf-8",
        )

        failed = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])
        failed_checks = failed["metadata"]["checks"]

        self.assertEqual(failed["status"], "failed")
        self.assertTrue(any(item["name"] == "flashcard helper: card output exists" and item["status"] == "fail" for item in failed_checks))
        self.assertTrue(any("Flashcard helper needs a `card-output` area" in item for item in failed["blockers"]))

    def test_app_specific_verification_requires_shape_update_markers(self) -> None:
        scorer_html = """<!doctype html><html><body><textarea id="idea-input" data-template-marker="main-input"></textarea><button id="score-idea" data-template-marker="primary-action">Score Idea</button><section data-template-marker="result-output"><div id="idea-score">0</div><ul id="idea-risks" data-template-marker="risk_breakdown"></ul><div id="idea-smallest-test" data-template-marker="smallest-testable-version"></div><div id="idea-next-action" data-template-marker="next-action"></div></section></body></html>"""
        scorer_checks = static_app_shape_verification_checks(
            "business_idea_scorer",
            index_html=scorer_html,
            app_js="document.getElementById('score-idea').addEventListener('click', function(){document.getElementById('idea-risks').innerHTML='<li>Risk</li>';document.getElementById('idea-smallest-test').textContent='Test';document.getElementById('idea-next-action').textContent='Next';});",
        )
        self.assertTrue(any(item["name"] == "business idea scorer: score output updates" and item["status"] == "fail" for item in scorer_checks))

        budget_html = """<!doctype html><html><body><input id="budget-income" data-template-marker="main-input" type="number" /><input id="budget-food" class="expense-input" data-template-marker="expense-input" type="number" /><button id="budget-run" data-template-marker="primary-action">Calculate Budget</button><section data-template-marker="result-output"><div id="budget-savings">0</div></section><div id="budget-breakdown" data-template-marker="spending-breakdown"></div><div id="budget-recommendation" data-template-marker="recommendation"></div></body></html>"""
        budget_checks = static_app_shape_verification_checks(
            "budget_calculator",
            index_html=budget_html,
            app_js="document.getElementById('budget-run').addEventListener('click', function(){document.getElementById('budget-breakdown').textContent='Breakdown';document.getElementById('budget-recommendation').textContent='Recommendation';});",
        )
        self.assertTrue(any(item["name"] == "budget calculator: savings output updates" and item["status"] == "fail" for item in budget_checks))

        flashcard_html = """<!doctype html><html><body><textarea id="notes-input" data-template-marker="main-input"></textarea><button id="build-cards" data-template-marker="primary-action">Build Flashcards</button><section id="card-output" data-template-marker="flashcard-cards"></section></body></html>"""
        flashcard_checks = static_app_shape_verification_checks(
            "flashcard_helper",
            index_html=flashcard_html,
            app_js="document.getElementById('build-cards').addEventListener('click', function(){document.getElementById('card-output').textContent='Cards ready';});",
        )
        self.assertTrue(any(item["name"] == "flashcard helper: flashcard content renders" and item["status"] == "fail" for item in flashcard_checks))

    def test_canonical_app_behavior_verification_requires_input_action_and_output_evidence(self) -> None:
        scorer_html = """<!doctype html><html><body><textarea id="idea-input" data-template-marker="main-input"></textarea><button id="score-idea" data-template-marker="primary-action">Score Idea</button><section data-template-marker="result-output"><div id="idea-score">0</div><ul id="idea-risks" data-template-marker="risk_breakdown"></ul><div id="idea-smallest-test" data-template-marker="smallest-testable-version"></div><div id="idea-next-action" data-template-marker="next-action"></div></section></body></html>"""
        scorer_js = """function scoreIdea(){const idea=document.querySelector('#idea-input').value.trim();document.querySelector('#idea-score').textContent=idea.length?'7':'1';document.querySelector('#idea-risks').innerHTML='<li>Demand risk</li>';document.querySelector('#idea-smallest-test').textContent='Interview one user.';document.querySelector('#idea-next-action').textContent='Book one validation call.';}document.querySelector('#score-idea').addEventListener('click', scoreIdea);"""
        scorer_checks = static_app_shape_verification_checks("business_idea_scorer", index_html=scorer_html, app_js=scorer_js)
        self.assertFalse([item for item in scorer_checks if item["status"] == "fail"])

        no_action_checks = static_app_shape_verification_checks(
            "business_idea_scorer",
            index_html=scorer_html,
            app_js=scorer_js.replace("document.querySelector('#score-idea').addEventListener('click', scoreIdea);", ""),
        )
        self.assertTrue(any(item["name"] == "business idea scorer: score action is wired" and item["status"] == "fail" for item in no_action_checks))

        no_next_update_checks = static_app_shape_verification_checks(
            "business_idea_scorer",
            index_html=scorer_html,
            app_js=scorer_js.replace("document.querySelector('#idea-next-action').textContent='Book one validation call.';", ""),
        )
        self.assertTrue(any(item["name"] == "business idea scorer: next action output updates" and item["status"] == "fail" for item in no_next_update_checks))

        budget_html = """<!doctype html><html><body><input id="budget-income" data-template-marker="main-input" type="number" /><input id="budget-food" class="expense-input" data-template-marker="expense-input" type="number" /><button id="budget-run" data-template-marker="primary-action">Calculate Budget</button><section data-template-marker="result-output"><div id="budget-savings">0</div></section><div id="budget-breakdown" data-template-marker="spending-breakdown"></div><div id="budget-recommendation" data-template-marker="recommendation"></div></body></html>"""
        budget_js = """function calculateBudget(){const income=Number(document.getElementById('budget-income').value||0);const food=Number(document.getElementById('budget-food').value||0);document.getElementById('budget-savings').textContent=String(income-food);document.getElementById('budget-breakdown').textContent='Food: '+food;document.getElementById('budget-recommendation').textContent='Reduce one flexible expense.';}document.getElementById('budget-run').addEventListener('click', calculateBudget);"""
        budget_checks = static_app_shape_verification_checks("budget_calculator", index_html=budget_html, app_js=budget_js)
        self.assertFalse([item for item in budget_checks if item["status"] == "fail"])

        no_income_checks = static_app_shape_verification_checks(
            "budget_calculator",
            index_html=budget_html,
            app_js=budget_js.replace("const income=Number(document.getElementById('budget-income').value||0);", "const income=0;"),
        )
        self.assertTrue(any(item["name"] == "budget calculator: income input is read" and item["status"] == "fail" for item in no_income_checks))

        no_budget_outputs_checks = static_app_shape_verification_checks(
            "budget_calculator",
            index_html=budget_html,
            app_js=budget_js.replace("document.getElementById('budget-breakdown').textContent='Food: '+food;", "").replace("document.getElementById('budget-recommendation').textContent='Reduce one flexible expense.';", ""),
        )
        self.assertTrue(any(item["name"] == "budget calculator: breakdown output updates" and item["status"] == "fail" for item in no_budget_outputs_checks))
        self.assertTrue(any(item["name"] == "budget calculator: recommendation output updates" and item["status"] == "fail" for item in no_budget_outputs_checks))

        flashcard_html = """<!doctype html><html><body><textarea id="notes-input" data-template-marker="main-input"></textarea><button id="build-cards" data-template-marker="primary-action">Build Flashcards</button><section id="card-output" data-template-marker="flashcard-cards"></section><p>Local mocked flashcards only.</p></body></html>"""
        flashcard_js = """function buildCards(){const notes=document.getElementById('notes-input').value.trim();document.getElementById('card-output').innerHTML='<article class="flashcard-card"><strong>Question</strong><p>Answer: '+notes+'</p></article>';}document.getElementById('build-cards').addEventListener('click', buildCards);"""
        flashcard_checks = static_app_shape_verification_checks("flashcard_helper", index_html=flashcard_html, app_js=flashcard_js)
        self.assertFalse([item for item in flashcard_checks if item["status"] == "fail"])

        no_notes_checks = static_app_shape_verification_checks(
            "flashcard_helper",
            index_html=flashcard_html,
            app_js=flashcard_js.replace("const notes=document.getElementById('notes-input').value.trim();", "const notes='';"),
        )
        self.assertTrue(any(item["name"] == "flashcard helper: notes input is read" and item["status"] == "fail" for item in no_notes_checks))

        no_card_output_checks = static_app_shape_verification_checks(
            "flashcard_helper",
            index_html=flashcard_html,
            app_js=flashcard_js.replace("document.getElementById('card-output').innerHTML=", "document.getElementById('other-output').innerHTML="),
        )
        self.assertTrue(any(item["name"] == "flashcard helper: card output updates" and item["status"] == "fail" for item in no_card_output_checks))

    def test_custom_app_shape_is_not_subject_to_canonical_behavior_checks(self) -> None:
        html = """<!doctype html><html><body><textarea id="idea-input" data-template-marker="main-input"></textarea><button id="score-idea" data-template-marker="primary-action">Score Idea</button><div id="idea-score" data-template-marker="result-output"></div></body></html>"""
        checks = static_app_shape_verification_checks("custom_static_app", index_html=html, app_js="")

        self.assertEqual(checks, [])

    def test_secondary_app_shape_checks_cover_quiz_and_waitlist_apps(self) -> None:
        quiz_checks = static_app_shape_verification_checks(
            "quiz_recommender",
            index_html="""<!doctype html><html><body><select id="quiz-answer"><option>Fastest path</option></select><button id="quiz-run">Show Recommendation</button><section id="quiz-recommendation">Recommendation appears here.</section></body></html>""",
            app_js="document.getElementById('quiz-run').addEventListener('click', function(){document.getElementById('quiz-recommendation').textContent='Local recommendation';});",
            readme_text="Uses a deterministic local score with no AI.",
        )
        waitlist_checks = static_app_shape_verification_checks(
            "waitlist_page",
            index_html="""<!doctype html><html><body><h1>Join Waitlist</h1><input id="waitlist-email" type="email" /><button id="waitlist-submit">Join Waitlist</button><p id="waitlist-result">Local-only confirmation appears here.</p></body></html>""",
            app_js="document.getElementById('waitlist-submit').addEventListener('click', function(){document.getElementById('waitlist-result').textContent='Thanks. This is a mock signup.';});",
        )

        self.assertFalse([item for item in quiz_checks if item["status"] == "fail"])
        self.assertFalse([item for item in waitlist_checks if item["status"] == "fail"])

    def test_deploy_pack_verification_passes_for_generated_package(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        deploy_pack = self.generate_deploy_pack(project, prototype, "static")

        verification = self.run_verification(project, verification_scope="deploy_pack", deploy_pack_id=deploy_pack["id"])

        self.assertEqual(verification["status"], "passed")
        self.assertTrue(verification["share_ready"])
        self.assertFalse(verification["blockers"])

    def test_build_pack_verification_passes_for_static_app_and_runs_generated_smoke(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        build_pack = self.generate_build_pack(project, prototype, build_target="static_app")

        verification = self.run_verification(project, verification_scope="build_pack", build_pack_id=build_pack["id"])
        checks = verification["metadata"]["checks"]

        self.assertEqual(verification["status"], "passed")
        self.assertTrue(verification["codex_ready"])
        self.assertTrue(any(item["name"] == "tests/smoke_static.py passes" and item["status"] == "pass" for item in checks))

    def test_build_pack_verification_mentions_workspace_when_available(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        build_pack = self.generate_build_pack(project, prototype, build_target="python_stdlib_app")
        self.export_workspace(project=project, build_pack=build_pack)

        verification = self.run_verification(project, verification_scope="build_pack", build_pack_id=build_pack["id"])
        checks = verification["metadata"]["checks"]

        self.assertTrue(any(item["name"] == "linked workspace export passes basic verification" for item in checks))
        self.assertTrue(any(ref["label"] == "Workspace" for ref in verification["referenced_artifacts"]))

    def test_build_pack_verification_syntax_checks_python_build_pack(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        build_pack = self.generate_build_pack(project, prototype, build_target="python_stdlib_app")

        verification = self.run_verification(project, verification_scope="build_pack", build_pack_id=build_pack["id"])
        checks = verification["metadata"]["checks"]

        self.assertEqual(verification["status"], "passed")
        self.assertTrue(any(item["name"] == "app.py syntax-compiles" and item["status"] == "pass" for item in checks))
        self.assertTrue(any(item["name"] == "tests/smoke_app.py passes" and item["status"] == "pass" for item in checks))

    def test_build_pack_verification_passes_for_ai_tool_stub_and_runs_generated_smoke(self) -> None:
        build_pack = self.generate_build_pack(build_target="ai_tool_stub")
        project = sprintos.get_project(build_pack["project_id"])
        self.assertIsNotNone(project)

        verification = self.run_verification(project, verification_scope="build_pack", build_pack_id=build_pack["id"])
        checks = verification["metadata"]["checks"]

        self.assertEqual(verification["status"], "passed")
        self.assertTrue(any(item["name"] == "app.py includes optional AI runtime markers" and item["status"] == "pass" for item in checks))
        self.assertTrue(any(item["name"] == "app.py includes mocked fallback markers" and item["status"] == "pass" for item in checks))
        self.assertTrue(any(item["name"] == "frontend calls /api/generate" and item["status"] == "pass" for item in checks))
        self.assertTrue(any(item["name"] == "README.md explains mocked default and local AI opt-in" and item["status"] == "pass" for item in checks))
        self.assertTrue(any(item["name"] == "app.py avoids obvious hardcoded API keys" and item["status"] == "pass" for item in checks))
        self.assertTrue(any(item["name"] == "tests/smoke_app.py passes" and item["status"] == "pass" for item in checks))

    def test_build_pack_verification_catches_hardcoded_key_in_ai_tool_stub_fixture(self) -> None:
        build_pack = self.generate_build_pack(build_target="ai_tool_stub")
        project = sprintos.get_project(build_pack["project_id"])
        self.assertIsNotNone(project)
        app_path = Path(build_pack["path"]) / "app.py"
        original = app_path.read_text(encoding="utf-8")
        fixture_key = "sk" + "-test-fixture-secret"
        app_path.write_text(original + f'\nOPENAI_API_KEY = "{fixture_key}"\n', encoding="utf-8")

        verification = self.run_verification(project, verification_scope="build_pack", build_pack_id=build_pack["id"])
        checks = verification["metadata"]["checks"]

        self.assertNotEqual(verification["status"], "passed")
        self.assertTrue(any(item["name"] == "app.py avoids obvious hardcoded API keys" and item["status"] == "fail" for item in checks))

    def test_pipeline_verification_passes_for_generated_pipeline_run(self) -> None:
        project = self.create_project()
        pipeline_run = self.generate_pipeline(project, pipeline_goal="codex_build_ready")

        verification = self.run_verification(project, verification_scope="pipeline", pipeline_run_id=pipeline_run["pipeline_run_id"])

        self.assertEqual(verification["status"], "passed")
        self.assertTrue(verification["share_ready"])
        self.assertTrue(verification["codex_ready"])

    def test_quick_launch_verification_passes_for_generated_quick_launch(self) -> None:
        quick_launch = self.generate_quick_launch()
        project = sprintos.get_project(quick_launch["project_id"])

        verification = self.run_verification(project, verification_scope="quick_launch", quick_launch_id=quick_launch["quick_launch_id"])

        self.assertEqual(verification["status"], "passed")
        self.assertTrue(verification["share_ready"])
        self.assertTrue(verification["codex_ready"])

    def test_all_latest_combines_available_checks(self) -> None:
        quick_launch = self.generate_quick_launch()
        project = sprintos.get_project(quick_launch["project_id"])
        self.assertIsNotNone(project)
        latest_build_pack = project["latest_build_pack"]
        self.export_workspace(project=project, build_pack=latest_build_pack)
        project = sprintos.get_project(quick_launch["project_id"])

        verification = self.run_verification(project, verification_scope="all_latest")
        subresults = verification["metadata"]["subresults"]

        self.assertEqual(verification["status"], "passed")
        self.assertTrue(verification["share_ready"])
        self.assertTrue(verification["codex_ready"])
        self.assertEqual(set(subresults.keys()), {"prototype", "deploy_pack", "build_pack", "pipeline", "quick_launch", "workspace"})

    def test_workspace_verification_catches_copied_env_in_controlled_fixture(self) -> None:
        build_pack = self.generate_build_pack(build_target="python_stdlib_app")
        workspace = self.export_workspace(build_pack=build_pack)
        workspace_dir = Path(workspace["path"])
        fixture_key = "sk" + "-test-fixture-secret"
        (workspace_dir / ".env").write_text(f"OPENAI_API_KEY={fixture_key}\n", encoding="utf-8")
        project = sprintos.get_project(build_pack["project_id"])
        self.assertIsNotNone(project)

        verification = sprintos.verify_workspace_artifact(project, sprintos.get_workspace(workspace["workspace_id"], include_prompt=True))
        checks = verification["checks"]

        self.assertNotEqual(verification["status"], "passed")
        self.assertTrue(any(item["name"] == "no .env copied into workspace" and item["status"] == "fail" for item in checks))

    def test_missing_artifacts_produce_partial_status_without_crashing(self) -> None:
        project = self.create_project()

        prototype_verification = self.run_verification(project, verification_scope="prototype")
        all_latest_verification = self.run_verification(project, verification_scope="all_latest")

        self.assertEqual(prototype_verification["status"], "partial")
        self.assertEqual(all_latest_verification["status"], "partial")
        self.assertFalse(all_latest_verification["share_ready"])
        self.assertFalse(all_latest_verification["codex_ready"])

    def test_verification_report_folder_and_json_outputs_are_created(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")

        verification = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])
        report_dir = Path(verification["report_path"])

        self.assertTrue(report_dir.exists())
        self.assertEqual(set(path.name for path in report_dir.iterdir()), set(sprintos.VERIFICATION_REPORT_FILES))
        parsed = json.loads((report_dir / "check-results.json").read_text(encoding="utf-8"))
        self.assertEqual(parsed["scope"], "prototype")
        self.assertIn("verification-report.md", {path.name for path in report_dir.iterdir()})

    def test_codex_fix_prompt_and_tester_readiness_files_include_required_content(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        (Path(prototype["path"]) / "app.js").write_text("", encoding="utf-8")

        verification = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])
        report_dir = Path(verification["report_path"])
        codex_fix_prompt = (report_dir / "codex-fix-prompt.md").read_text(encoding="utf-8")
        tester_readiness = (report_dir / "tester-share-readiness.md").read_text(encoding="utf-8")

        self.assertIn("Read AGENTS.md first.", codex_fix_prompt)
        self.assertIn("## Objective", codex_fix_prompt)
        self.assertIn("## Verification Summary", codex_fix_prompt)
        self.assertIn("## Failed Checks", codex_fix_prompt)
        self.assertIn("## Warnings", codex_fix_prompt)
        self.assertIn("## Files Likely Touched", codex_fix_prompt)
        self.assertIn("## Acceptance Criteria", codex_fix_prompt)
        self.assertIn("## Verification Commands", codex_fix_prompt)
        self.assertIn("## Non-Goals", codex_fix_prompt)
        self.assertIn("Preserve existing behavior.", codex_fix_prompt)
        self.assertIn("Do not overbuild.", codex_fix_prompt)
        self.assertIn("Not ready to share with testers yet.", tester_readiness)
        self.assertIn("## What to test", tester_readiness)
        self.assertIn("## What not to collect", tester_readiness)

    def test_verification_zip_and_safe_file_serving_work(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        verification = self.run_verification(project, verification_scope="prototype", prototype_id=prototype["id"])
        server = self.start_server()

        zip_payload = self.http_get(server, f"/api/verification_zip?id={verification['verification_run_id']}")
        with zipfile.ZipFile(io.BytesIO(zip_payload)) as zf:
            self.assertEqual(set(zf.namelist()), set(sprintos.VERIFICATION_REPORT_FILES))

        report_text = self.http_get(server, f"/api/verification_report?id={verification['verification_run_id']}&file=verification-report.md").decode("utf-8")
        route_text = self.http_get(server, f"/verification/{verification['verification_run_id']}/verification-report.md").decode("utf-8")
        self.assertIn("Verification Report", report_text)
        self.assertIn("Verification Report", route_text)
        stored = json.loads(self.http_get(server, f"/api/verification_run?id={verification['verification_run_id']}").decode("utf-8"))
        self.assertEqual(stored["verification_run_id"], verification["verification_run_id"])
        with self.assertRaises(urllib.error.HTTPError) as exc:
            self.http_get(server, f"/api/verification_report?id={verification['verification_run_id']}&file=../sprintos.py")
        self.assertEqual(exc.exception.code, 400)

    def test_project_exports_and_handoff_include_latest_verification_context(self) -> None:
        quick_launch = self.generate_quick_launch()
        project = sprintos.get_project(quick_launch["project_id"])
        verification = self.run_verification(project, verification_scope="all_latest")
        project = sprintos.get_project(project["id"])

        self.assertEqual(project["latest_verification_run"]["verification_run_id"], verification["verification_run_id"])
        _, markdown = sprintos.write_markdown_export(project)
        _, payload = sprintos.build_zip_export(project)
        handoff = project["sprint"]["codex_handoff"]["content"]

        self.assertIn("## Latest Verification Run", markdown)
        self.assertIn(verification["report_path"], markdown)
        self.assertIn("Latest verification scope/status", handoff)
        self.assertIn(verification["status"], handoff)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            self.assertIn("verification-run.md", names)
            self.assertIn("codex-fix-prompt.md", names)
            self.assertIn("tester-share-readiness.md", names)
            self.assertIn("Run & Verify", zf.read("verification-run.md").decode("utf-8"))

    def test_run_verification_api_returns_expected_fields(self) -> None:
        project = self.create_project()
        prototype = self.generate_prototype(project, "landing_page")
        server = self.start_server()

        payload = self.http_post_json(
            server,
            "/api/run_verification",
            {"project_id": project["id"], "verification_scope": "prototype", "prototype_id": prototype["id"]},
        )

        self.assertIn("verification_run_id", payload)
        self.assertEqual(payload["verification_scope"], "prototype")
        self.assertIn("report_url", payload)
        self.assertIn("zip_url", payload)
        self.assertIn("codex_fix_prompt", payload)
        self.assertIn("tester_share_readiness", payload)


class FullLoopRegressionTests(SprintOSTestCase):
    def test_server_status_endpoint_returns_safe_runtime_metadata(self) -> None:
        os.environ["OPENAI_API_KEY"] = "sk-test-secret-value"
        server = self.start_server()

        payload = json.loads(self.http_get(server, "/api/server_status").decode("utf-8"))

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["app"], "SprintOS")
        self.assertEqual(payload["pid"], os.getpid())
        self.assertIsInstance(payload["uptime_seconds"], int)
        self.assertGreaterEqual(payload["uptime_seconds"], 0)
        self.assertTrue(str(payload["started_at"]))
        self.assertEqual(payload["url"], f"http://127.0.0.1:{server.server_address[1]}")
        self.assertEqual(payload["data_dir"], str(sprintos.DATA_DIR))
        self.assertEqual(payload["exports_dir"], str(sprintos.EXPORT_DIR))
        self.assertEqual(payload["workspaces_dir"], str(sprintos.WORKSPACE_DIR))
        self.assertEqual(payload["backups_dir"], str(sprintos.BACKUP_DIR))
        self.assertEqual(payload["ai_provider_mode"], "offline")
        self.assertNotIn("OPENAI_API_KEY", payload)
        self.assertNotIn("sk-test-secret-value", json.dumps(payload))

    def test_full_local_chain_fixture_stays_intact(self) -> None:
        chain = self.generate_full_chain()

        self.assertEqual(chain["verification"]["status"], "passed")
        self.assertEqual(chain["quick_launch_verification"]["status"], "passed")
        self.assertTrue(chain["iteration"]["iteration_brief"])
        self.assertTrue(Path(chain["prototype"]["path"]).exists())
        self.assertTrue(Path(chain["deploy_pack"]["path"]).exists())
        self.assertTrue(Path(chain["build_pack"]["path"]).exists())
        self.assertTrue(Path(chain["pipeline_run"]["report_path"]).exists())
        self.assertTrue(Path(chain["quick_launch"]["report_path"]).exists())
        self.assertTrue(Path(chain["verification"]["report_path"]).exists())
        self.assertTrue(Path(chain["quick_launch_verification"]["report_path"]).exists())
        self.assertIn("## Resume Mode", chain["markdown"])
        self.assertIn("## Latest Prototype Package", chain["markdown"])
        self.assertIn("## Latest Deploy Pack", chain["markdown"])
        self.assertIn("## Latest Build Pack", chain["markdown"])
        self.assertIn("## Latest Pipeline Run", chain["markdown"])
        self.assertIn("## Latest Verification Run", chain["markdown"])
        self.assertTrue(chain["markdown_name"].endswith(".md"))
        self.assertTrue(chain["zip_name"].endswith(".zip"))

        with zipfile.ZipFile(io.BytesIO(chain["zip_payload"])) as zf:
            names = set(zf.namelist())
            self.assertIn("sprint.md", names)
            self.assertIn("codex-task.md", names)
            self.assertIn("resume.md", names)
            self.assertIn("prototypes.md", names)
            self.assertIn("deploy-pack.md", names)
            self.assertIn("build-pack.md", names)
            self.assertIn("pipeline-run.md", names)
            self.assertIn("verification-run.md", names)
            self.assertIn("feedback.md", names)


if __name__ == "__main__":
    unittest.main()
