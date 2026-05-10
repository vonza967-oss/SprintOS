import json
import os
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from typing import Optional

import sprintos
from sprintos_core.ai_provider import DEFAULT_DEEPSEEK_BASE_URL, DEFAULT_OPENAI_MODEL


class SprintOSTestCase(unittest.TestCase):
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
            sprintos.BACKUP_DIR,
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
            "SPRINTOS_APP_GENERATION_FALLBACK_MODE": os.environ.get("SPRINTOS_APP_GENERATION_FALLBACK_MODE"),
            "SPRINTOS_DISABLE_OFFLINE_APP_FALLBACK": os.environ.get("SPRINTOS_DISABLE_OFFLINE_APP_FALLBACK"),
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
        sprintos.BACKUP_DIR = self.root / "backups"
        os.chdir(self.root)
        os.environ["OPENAI_API_KEY"] = ""
        os.environ["DEEPSEEK_API_KEY"] = ""
        os.environ["DEEPSEEK_BASE_URL"] = DEFAULT_DEEPSEEK_BASE_URL
        os.environ["SPRINTOS_AI_PROVIDER"] = "offline"
        os.environ["SPRINTOS_AI_ENABLED"] = "false"
        os.environ["SPRINTOS_MODEL"] = DEFAULT_OPENAI_MODEL
        os.environ["SPRINTOS_AI_TIMEOUT_SECONDS"] = "20"
        os.environ["SPRINTOS_AI_MAX_OUTPUT_TOKENS"] = "2000"
        os.environ.pop("SPRINTOS_APP_GENERATION_FALLBACK_MODE", None)
        os.environ.pop("SPRINTOS_DISABLE_OFFLINE_APP_FALLBACK", None)
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
        sprintos.DATA_DIR, sprintos.EXPORT_DIR, sprintos.WORKFLOW_DIR, sprintos.DB_PATH, sprintos.WORKSPACE_DIR, sprintos.BACKUP_DIR = self.original_paths
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

    def create_minimal_project(self):
        return self.create_project()

    def create_project_with_sprint(self, **kwargs):
        return self.create_project(**kwargs)

    def generate_prototype(self, project=None, prototype_type: str = "landing_page", generation_mode: str = "auto"):
        project = project or self.create_project()
        prototype = sprintos.write_prototype_package(project, prototype_type, generation_mode=generation_mode)
        self.assertIsNotNone(prototype)
        return prototype

    def create_project_with_prototype(self, **kwargs):
        project = self.create_project(**kwargs)
        prototype = self.generate_prototype(project)
        return project, prototype

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

    def create_project_with_build_pack(self, **kwargs):
        project = self.create_project(**kwargs)
        prototype = self.generate_prototype(project)
        deploy_pack = self.generate_deploy_pack(project, prototype, "static")
        build_pack = self.generate_build_pack(project, prototype, deploy_pack=deploy_pack, build_target="static_app")
        return project, prototype, deploy_pack, build_pack

    def export_workspace(self, project=None, build_pack=None):
        build_pack = build_pack or self.generate_build_pack(project)
        project = project or sprintos.get_project(build_pack["project_id"]) or self.create_project()
        workspace = sprintos.write_workspace_export(project, build_pack)
        self.assertIsNotNone(workspace)
        return workspace

    def create_project_with_workspace(self, **kwargs):
        project, prototype, deploy_pack, build_pack = self.create_project_with_build_pack(**kwargs)
        workspace = self.export_workspace(project, build_pack)
        return project, prototype, deploy_pack, build_pack, workspace

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

    def create_project_with_release_pack(self, **kwargs):
        project, prototype, deploy_pack, build_pack, workspace = self.create_project_with_workspace(**kwargs)
        release_pack = self.create_workspace_release(project, workspace, run_checks=True)
        return project, prototype, deploy_pack, build_pack, workspace, release_pack

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

    def create_local_backup(self, backup_label: str = "manual-backup"):
        backup = sprintos.create_local_backup(backup_label=backup_label)
        self.assertIsNotNone(backup)
        return backup

    def verify_local_backup(self, backup=None):
        backup = backup or self.create_local_backup()
        payload = sprintos.verify_local_backup(backup["backup_id"])
        self.assertIsNotNone(payload)
        return payload

    def restore_local_backup(self, backup=None, *, dry_run: bool = True, confirm_restore: bool = False):
        backup = backup or self.create_local_backup()
        payload = sprintos.restore_local_backup(
            backup["backup_id"],
            dry_run=dry_run,
            confirm_restore=confirm_restore,
        )
        self.assertIsNotNone(payload)
        return payload

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

    def run_guided_demo(self, demo_mode: str = "quick"):
        demo_run = sprintos.run_guided_demo(demo_mode)
        self.assertIsNotNone(demo_run)
        return demo_run

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
