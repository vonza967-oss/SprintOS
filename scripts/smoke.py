#!/usr/bin/env python3

import io
import json
import os
import sys
import tempfile
import threading
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sprintos
from sprintos_core.ai_provider import DEFAULT_DEEPSEEK_BASE_URL, load_ai_provider_config


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sprintos.DATA_DIR = root / "data"
        sprintos.EXPORT_DIR = root / "exports"
        sprintos.WORKFLOW_DIR = root / "workflows"
        sprintos.DB_PATH = sprintos.DATA_DIR / "sprintos.sqlite"
        sprintos.WORKSPACE_DIR = root / "workspaces"
        sprintos.BACKUP_DIR = root / "backups"
        os.environ["SPRINTOS_AI_PROVIDER"] = "offline"
        os.environ["SPRINTOS_AI_ENABLED"] = "false"
        os.environ["SPRINTOS_MODEL"] = "gpt-4.1-mini"
        os.environ["SPRINTOS_AI_TIMEOUT_SECONDS"] = "20"
        os.environ["SPRINTOS_AI_MAX_OUTPUT_TOKENS"] = "2000"
        os.environ["SPRINTOS_APP_GENERATION_FALLBACK_MODE"] = "template"
        os.environ["SPRINTOS_DISABLE_OFFLINE_APP_FALLBACK"] = "false"
        os.environ["OPENAI_API_KEY"] = ""
        os.environ["DEEPSEEK_API_KEY"] = ""
        os.environ["DEEPSEEK_BASE_URL"] = DEFAULT_DEEPSEEK_BASE_URL

        deepseek_config = load_ai_provider_config({"SPRINTOS_AI_PROVIDER": "deepseek", "SPRINTOS_AI_ENABLED": "false"})
        assert deepseek_config.provider == "deepseek"
        assert deepseek_config.base_url == DEFAULT_DEEPSEEK_BASE_URL
        assert not deepseek_config.api_key_present

        sprintos.ensure_dirs()
        sprintos.write_default_workflows()
        sprintos.init_db()

        server = sprintos.ThreadingHTTPServer(("127.0.0.1", 0), sprintos.SprintOSHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"

        def post_json(path: str, payload: dict) -> dict:
            request = urllib.request.Request(
                base_url + path,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))

        def get_json(path: str) -> dict:
            with urllib.request.urlopen(base_url + path, timeout=5) as response:
                return json.loads(response.read().decode("utf-8"))

        health_payload = get_json("/api/health")
        assert health_payload["ok"] is True
        assert health_payload["app"] == "SprintOS"
        server_status = get_json("/api/server_status")
        assert server_status["ok"] is True
        assert server_status["app"] == "SprintOS"
        assert server_status["pid"] == os.getpid()
        assert server_status["url"] == base_url
        assert "OPENAI_API_KEY" not in json.dumps(server_status)
        assert "DEEPSEEK_API_KEY" not in json.dumps(server_status)

        empty_dashboard = get_json("/api/today_dashboard")
        assert empty_dashboard["stats"]["total_projects"] == 0
        assert empty_dashboard["global_recommended_action"]["action_id"] == "none"
        assert empty_dashboard["server_status"]["app"] == "SprintOS"
        assert empty_dashboard["setup_doctor"]["recommended_action"]["action_id"] == "create_backup"
        assert empty_dashboard["first_run_onboarding"]["show"] is True

        setup_doctor = get_json("/api/setup_doctor")
        assert setup_doctor["status"] in {"ok", "warning", "blocked"}
        assert "runtime" in setup_doctor["sections"]
        assert "storage" in setup_doctor["sections"]
        setup_doctor_markdown = urllib.request.urlopen(base_url + "/api/setup_doctor_export", timeout=5).read().decode("utf-8")
        assert "# Setup Doctor" in setup_doctor_markdown
        setup_action = post_json("/api/run_setup_doctor_action", {})
        assert setup_action["action_id"] == "create_backup"
        assert setup_action["ran"] or setup_action["status"] in {"manual", "blocked"}

        setup_doctor_after_backup = get_json("/api/setup_doctor")
        assert setup_doctor_after_backup["secondary_action"]["action_id"] == "run_guided_demo"
        guided_demo = post_json("/api/run_guided_demo", {"demo_mode": "quick"})
        assert guided_demo["demo_run_id"]
        assert guided_demo["demo_mode"] == "quick"
        assert guided_demo["project_id"]
        guided_demo_payload = get_json(f"/api/demo_run?id={guided_demo['demo_run_id']}")
        assert guided_demo_payload["demo_run_id"] == guided_demo["demo_run_id"]
        guided_demo_report = urllib.request.urlopen(base_url + guided_demo["report_url"], timeout=5).read().decode("utf-8")
        assert "# Guided Demo Report" in guided_demo_report
        assert "AI Study Flashcard Helper" in guided_demo_report
        guided_demo_project = get_json(f"/api/project?id={guided_demo['project_id']}")["project"]
        assert guided_demo_project["id"] == guided_demo["project_id"]
        demo_dashboard = get_json("/api/today_dashboard")
        assert demo_dashboard["latest_demo_run"]["demo_run_id"] == guided_demo["demo_run_id"]

        raw_idea = "Build a local-first execution engine that turns messy ideas into small finished outputs."
        desired_output = "a local working prototype"
        sprint = sprintos.generate_sprint(raw_idea, "software_mvp", 120, "high", desired_output)
        pid = sprintos.save_project(raw_idea, sprint["_workflow_id"], 120, "high", desired_output, sprint)
        command_center = get_json(f"/api/project_command_center?project_id={pid}")["command_center"]
        assert command_center["recommended_action"]["action_id"] == "start_focus_session"
        assert command_center["recommended_action"]["source_action_id"] == "generate_prototype"
        focus_session = post_json(
            "/api/start_focus_session",
            {
                "project_id": pid,
                "timebox_minutes": 30,
                "action_id": command_center["recommended_action"]["source_action_id"],
            },
        )
        assert focus_session["session_status"] == "active"
        focus_session_id = focus_session["focus_session_id"]
        active_focus_dashboard = get_json("/api/today_dashboard")
        assert active_focus_dashboard["active_focus_session"]["focus_session_id"] == focus_session_id
        assert active_focus_dashboard["recommended_project"]["project_id"] == pid
        updated_focus_session = post_json(
            "/api/update_focus_session",
            {
                "focus_session_id": focus_session_id,
                "progress_note": "Generated the session plan and stayed inside the first tiny action.",
            },
        )
        assert updated_focus_session["progress_note"]
        completed_focus_session = post_json(
            "/api/complete_focus_session",
            {
                "focus_session_id": focus_session_id,
                "outcome": "Session complete: ready to generate the prototype package next.",
                "progress_note": "Saved the session outcome and next tiny action.",
            },
        )["focus_session"]
        focus_session_dir = Path(completed_focus_session["report_path"])
        assert focus_session_dir.exists()
        assert (focus_session_dir / "focus-session-report.md").exists()
        action_result = post_json("/api/run_recommended_action", {"project_id": pid, "action_id": "generate_prototype"})
        assert action_result["ran"]
        assert action_result["action_id"] == "generate_prototype"
        project = sprintos.generate_and_store_resume_plan(pid)
        assert project is not None
        project = sprintos.get_project(pid)
        assert project is not None
        prototype = project["latest_prototype"]
        assert prototype is not None
        prototype_dir = Path(prototype["path"])
        prototype_index = (prototype_dir / "index.html").read_text(encoding="utf-8")
        prototype_style = (prototype_dir / "style.css").read_text(encoding="utf-8")
        prototype_app_js = (prototype_dir / "app.js").read_text(encoding="utf-8")
        prototype_meta = json.loads((prototype_dir / "prototype.json").read_text(encoding="utf-8"))

        sprintos.add_feedback_entry(
            project["id"],
            prototype_id=prototype["id"],
            tester_label="Smoke tester",
            source="manual",
            rating=4,
            pain_level=4,
            would_use="yes",
            would_pay="maybe",
            confusing_parts="The first step could be clearer.",
            missing_features="A result preview.",
            favorite_part="The local-first framing.",
            freeform_feedback="Worth one more iteration.",
        )
        project = sprintos.get_project(pid)
        assert project is not None
        summary = sprintos.build_iteration_summary(project, prototype["id"])
        sprintos.save_iteration_snapshot(project["id"], prototype["id"], summary)
        project = sprintos.get_project(pid)
        assert project is not None
        assert project["feedback"]["latest_iteration"] is not None
        readiness = sprintos.check_deploy_readiness(prototype)
        assert readiness["ready"]
        assert "index.html" in readiness["checked_files"]

        deploy_pack = sprintos.write_deploy_pack(project, prototype, "static")
        deploy_dir = Path(deploy_pack["path"])
        deploy_index = (deploy_dir / "index.html").read_text(encoding="utf-8")
        deploy_md = (deploy_dir / "DEPLOY.md").read_text(encoding="utf-8")
        build_pack = sprintos.write_build_pack(project, prototype, "static_app", deploy_pack=deploy_pack)
        build_dir = Path(build_pack["path"])
        build_prompt = (build_dir / "CODEX_BUILD_PROMPT.md").read_text(encoding="utf-8")
        pipeline_run = sprintos.run_testable_pipeline(pid, pipeline_goal="codex_build_ready")
        pipeline_dir = Path(pipeline_run["report_path"])
        pipeline_report = (pipeline_dir / "pipeline-report.md").read_text(encoding="utf-8")
        pipeline_prompt = (pipeline_dir / "codex-next-prompt.md").read_text(encoding="utf-8")
        today_action = post_json("/api/run_today_action", {})
        assert today_action["action_id"] == "export_workspace"
        assert today_action["ran"]
        project = sprintos.get_project(pid)
        assert project is not None
        workspace = project["latest_workspace"] or sprintos.write_workspace_export(project, build_pack)
        project = sprintos.get_project(pid)
        assert project is not None
        assert workspace is not None
        quick_launch = post_json(
            "/api/quick_launch",
            {
                "raw_idea": "Turn one messy idea into a testable local package with a Codex-ready next step.",
                "launch_goal": "codex_build_ready",
                "timebox_minutes": 120,
                "energy_level": "medium",
                "end_output": "a testable local package",
                "generation_mode": "offline",
            },
        )
        quick_launch_dir = Path(quick_launch["report_path"])
        quick_launch_report = (quick_launch_dir / "quick-launch-report.md").read_text(encoding="utf-8")
        quick_launch_prompt = (quick_launch_dir / "codex-next-prompt.md").read_text(encoding="utf-8")
        quick_launch_project = sprintos.get_project(quick_launch["project_id"])
        quick_launch_command_center = get_json(f"/api/project_command_center?project_id={quick_launch['project_id']}")["command_center"]
        quick_launch_dashboard = get_json("/api/today_dashboard")
        quick_launch_timeline = get_json(f"/api/project_timeline?project_id={quick_launch['project_id']}&limit=10")
        global_activity = get_json("/api/global_activity?limit=10")
        assert quick_launch["command_center"]["project_id"] == quick_launch["project_id"]
        assert quick_launch_command_center["recommended_action"]["action_id"]
        assert quick_launch_dashboard["stats"]["quick_launch_count"] >= 1
        assert quick_launch["project_id"] in [item["project_id"] for item in quick_launch_dashboard["recent_projects"]]
        assert quick_launch_timeline["count"] >= 1
        assert any(item["event_type"] == "quick_launch_completed" for item in quick_launch_timeline["events"])
        assert global_activity["count"] >= 1
        assert any(item["event_type"] == "quick_launch_completed" for item in global_activity["events"])
        assert quick_launch_dashboard["recent_global_activity"]
        verification = sprintos.run_project_verification(quick_launch["project_id"], verification_scope="all_latest")
        verification_dir = Path(verification["report_path"])
        workspace_dir = Path(workspace["path"])
        workspace_snapshot = sprintos.create_workspace_snapshot(project["id"], workspace_id=workspace["workspace_id"], snapshot_label="smoke-before-codex")
        workspace_snapshot_dir = Path(workspace_snapshot["snapshot_path"])
        workspace_app_path = workspace_dir / "src" / "app.js"
        original_workspace_app = workspace_app_path.read_text(encoding="utf-8")
        workspace_app_path.write_text(original_workspace_app + "\nconsole.log('smoke snapshot change');\n", encoding="utf-8")
        workspace_comparison = sprintos.compare_workspace_to_snapshot(workspace["workspace_id"], workspace_snapshot["snapshot_id"])
        workspace_restore = sprintos.restore_workspace_snapshot(workspace_snapshot["snapshot_id"])
        workspace_restore_dir = Path(workspace_restore["report_path"])
        workspace_sync = sprintos.run_workspace_sync(project["id"], workspace_id=workspace["workspace_id"], run_checks=True)
        workspace_sync_dir = Path(workspace_sync["report_path"])
        sprintos.run_project_verification(project["id"], verification_scope="build_pack", build_pack_id=build_pack["id"])
        workspace_release = sprintos.create_workspace_release_pack(
            project["id"],
            workspace_id=workspace["workspace_id"],
            release_label="smoke-rc",
            run_checks=True,
        )
        sprintos.add_release_feedback(
            project["id"],
            release_pack_id=workspace_release["release_pack_id"],
            tester_label="Release smoke tester",
            source="manual",
            rating=4,
            would_use="yes",
            would_pay="maybe",
            confusing_parts="The first run instructions could be tighter.",
            missing_features="A clearer result summary.",
            favorite_part="The local release packaging.",
            bug_report="",
            freeform_feedback="Worth another quick pass.",
        )
        project = sprintos.get_project(pid)
        assert project is not None
        today_after_release_feedback = sprintos.build_today_dashboard_summary()
        assert today_after_release_feedback["global_recommended_action"]["action_id"] == "generate_release_iteration"
        release_iteration_summary = sprintos.build_release_iteration_summary(project, workspace_release["release_pack_id"])
        sprintos.save_release_iteration_snapshot(project["id"], workspace_release["release_pack_id"], release_iteration_summary)
        workspace_release_dir = Path(workspace_release["path"])
        project = sprintos.get_project(pid)
        assert project is not None
        artifact_history_payload = get_json(f"/api/project_artifact_history?project_id={pid}&limit=10")
        artifact_history_export = urllib.request.urlopen(
            base_url + f"/api/project_artifact_history_export?project_id={pid}",
            timeout=5,
        ).read().decode("utf-8")
        assert artifact_history_payload["project_id"] == pid
        assert artifact_history_payload["total_count"] >= 1
        assert artifact_history_payload["groups"]["prototypes"]
        assert "# Artifact History" in artifact_history_export
        assert "## Prototypes" in artifact_history_export

        markdown_name, markdown = sprintos.write_markdown_export(project)
        assert markdown_name.endswith(".md")
        assert "## Codex Handoff" in markdown
        assert "## Resume Mode" in markdown
        assert "## Activity Timeline" in markdown
        assert "## Latest Prototype Package" in markdown
        assert "## Latest Deploy Pack" in markdown
        assert "## Latest Build Pack" in markdown
        assert "## Latest Pipeline Run" in markdown
        assert "## Project Command Center" in markdown
        assert "## Latest Workspace Snapshot" in markdown
        assert "## Feedback Loop" in markdown
        assert "## Release Feedback" in markdown

        assert (prototype_dir / "index.html").exists()
        assert (prototype_dir / "style.css").exists()
        assert (prototype_dir / "codex-build-prompt.md").exists()
        assert (prototype_dir / "feedback-import-instructions.md").exists()
        assert prototype["preview_url"].endswith("/index.html")
        assert prototype_meta["provider"] == "offline"
        assert prototype_meta["app_type"]
        assert "OPENAI_API_KEY" not in json.dumps(prototype_meta)
        assert "DEEPSEEK_API_KEY" not in json.dumps(prototype_meta)
        assert "sk-" not in json.dumps(prototype_meta)
        assert "Tester Feedback" in prototype_index
        assert "Save Feedback Locally" in prototype_index
        assert prototype_style.strip()
        assert "localStorage.setItem" in prototype_app_js
        assert "Export Feedback JSON" in prototype_index
        assert deploy_index == prototype_index
        assert "python3 -m http.server 8080" in deploy_md
        assert build_pack["run_command"] == "python3 -m http.server 8080 -d src"
        assert (build_dir / "src" / "index.html").exists()
        assert "Read AGENTS.md first." in build_prompt
        assert pipeline_dir.exists()
        assert (pipeline_dir / "pipeline-report.md").exists()
        assert (pipeline_dir / "codex-next-prompt.md").exists()
        assert "## Steps Completed" in pipeline_report
        assert "Build Pack path:" in pipeline_prompt
        assert quick_launch_dir.exists()
        assert quick_launch["project_id"]
        assert (quick_launch_dir / "quick-launch-report.md").exists()
        assert (quick_launch_dir / "codex-next-prompt.md").exists()
        assert "## Launch Goal" in quick_launch_report
        assert "Build Pack path:" in quick_launch_prompt
        assert quick_launch_project is not None
        assert verification["status"] == "passed"
        assert verification_dir.exists()
        assert (verification_dir / "verification-report.md").exists()
        assert (verification_dir / "codex-fix-prompt.md").exists()
        assert workspace_dir.exists()
        assert (workspace_dir / "CODEX_START_HERE.md").exists()
        assert (workspace_dir / "RUN_AND_TEST.md").exists()
        assert workspace_snapshot_dir.exists()
        assert (workspace_snapshot_dir / "snapshot-manifest.json").exists()
        assert (workspace_snapshot_dir / "snapshot-report.md").exists()
        assert workspace_comparison["modified_count"] >= 1
        assert workspace_restore_dir.exists()
        assert (workspace_restore_dir / "restore-report.md").exists()
        assert workspace_app_path.read_text(encoding="utf-8") == original_workspace_app
        assert workspace_sync["sync_status"] == "passed"
        assert workspace_sync_dir.exists()
        assert (workspace_sync_dir / "workspace-sync-report.md").exists()
        assert (workspace_sync_dir / "codex-followup-prompt.md").exists()
        assert (workspace_sync_dir / "sprintos-import-note.md").exists()
        assert workspace_release_dir.exists()
        assert (workspace_release_dir / "RELEASE.md").exists()
        assert (workspace_release_dir / "TESTER_INSTRUCTIONS.md").exists()
        assert (workspace_release_dir / "DEPLOY_OR_SHARE.md").exists()
        assert (workspace_release_dir / "CODEX_NEXT_PROMPT.md").exists()
        assert project["latest_release_iteration"] is not None
        assert "## Feedback Summary" in project["latest_release_iteration"]["codex_prompt"]
        assert focus_session_dir.exists()
        assert (focus_session_dir / "focus-session-report.md").exists()

        backup_create = post_json("/api/create_local_backup", {"backup_label": "smoke"})
        assert backup_create["backup_id"]
        backup_verify = post_json("/api/verify_local_backup", {"backup_id": backup_create["backup_id"]})
        assert backup_verify["verified"]
        backup_zip = urllib.request.urlopen(base_url + f"/api/local_backup_zip?id={backup_create['backup_id']}", timeout=5).read()
        with zipfile.ZipFile(io.BytesIO(backup_zip)) as zf:
            assert "data/sprintos.sqlite" in set(zf.namelist())
        backup_restore = post_json("/api/restore_local_backup", {"backup_id": backup_create["backup_id"], "dry_run": True})
        assert backup_restore["restore_status"] == "dry_run"
        restore_report = urllib.request.urlopen(base_url + backup_restore["report_url"], timeout=5).read().decode("utf-8")
        assert restore_report.startswith("# Local Restore Report")

        zip_name, payload = sprintos.build_zip_export(project)
        assert zip_name.endswith(".zip")
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            names = set(zf.namelist())
            assert {"sprint.md", "codex-task.md", "resume.md"}.issubset(names)
            assert "activity-timeline.md" in names
            assert "artifact-history.md" in names
            assert "command-center.md" in names
            assert "focus-session.md" in names
            assert "focus-session-codex-next-prompt.md" in names
            assert "focus-session-resume-note.md" in names
            assert "prototypes.md" in names
            assert "deploy-pack.md" in names
            assert "build-pack.md" in names
            assert "build-pack-codex-prompt.md" in names
            assert "pipeline-run.md" in names
            assert "codex-next-prompt.md" in names
            assert "share-message.md" in names
            assert "workspace.md" in names
            assert "workspace-snapshot.md" in names
            assert "restore-instructions.md" in names
            assert "CODEX_START_HERE.md" in names
            assert "workspace-sync.md" in names
            assert "codex-followup-prompt.md" in names
            assert "sprintos-import-note.md" in names
            assert "workspace-release.md" in names
            assert "tester-instructions.md" in names
            assert "deploy-or-share.md" in names
            assert "release-codex-next-prompt.md" in names
            assert "release-feedback.md" in names
            assert "release-iteration-brief.md" in names
            assert "release-iteration-codex-prompt.md" in names
            assert "feedback.md" in names

        deploy_zip_name, deploy_payload = sprintos.build_deploy_pack_zip(deploy_pack)
        assert deploy_zip_name.endswith(".zip")
        with zipfile.ZipFile(io.BytesIO(deploy_payload)) as zf:
            names = set(zf.namelist())
            assert "index.html" in names
            assert "DEPLOY.md" in names

        build_zip_name, build_payload = sprintos.build_build_pack_zip(build_pack)
        assert build_zip_name.endswith(".zip")
        with zipfile.ZipFile(io.BytesIO(build_payload)) as zf:
            names = set(zf.namelist())
            assert "CODEX_BUILD_PROMPT.md" in names
            assert "src/index.html" in names

        pipeline_zip_name, pipeline_payload = sprintos.build_pipeline_report_zip(pipeline_run)
        assert pipeline_zip_name.endswith(".zip")
        with zipfile.ZipFile(io.BytesIO(pipeline_payload)) as zf:
            names = set(zf.namelist())
            assert "pipeline-report.md" in names
            assert "codex-next-prompt.md" in names

        quick_launch_zip_name, quick_launch_payload = sprintos.build_quick_launch_zip(quick_launch)
        assert quick_launch_zip_name.endswith(".zip")
        with zipfile.ZipFile(io.BytesIO(quick_launch_payload)) as zf:
            names = set(zf.namelist())
            assert "quick-launch-report.md" in names
            assert "codex-next-prompt.md" in names

        verification_zip_name, verification_payload = sprintos.build_verification_zip(verification)
        assert verification_zip_name.endswith(".zip")
        with zipfile.ZipFile(io.BytesIO(verification_payload)) as zf:
            names = set(zf.namelist())
            assert "verification-report.md" in names
            assert "codex-fix-prompt.md" in names

        workspace_zip_name, workspace_payload = sprintos.build_workspace_zip(workspace)
        assert workspace_zip_name.endswith(".zip")
        with zipfile.ZipFile(io.BytesIO(workspace_payload)) as zf:
            names = set(zf.namelist())
            assert "CODEX_START_HERE.md" in names
            assert "RUN_AND_TEST.md" in names
            assert "workspace.json" in names

        workspace_sync_zip_name, workspace_sync_payload = sprintos.build_workspace_sync_zip(workspace_sync)
        assert workspace_sync_zip_name.endswith(".zip")
        with zipfile.ZipFile(io.BytesIO(workspace_sync_payload)) as zf:
            names = set(zf.namelist())
            assert "workspace-sync-report.md" in names
            assert "codex-followup-prompt.md" in names

        workspace_release_zip_name, workspace_release_payload = sprintos.build_workspace_release_zip(workspace_release)
        assert workspace_release_zip_name.endswith(".zip")
        with zipfile.ZipFile(io.BytesIO(workspace_release_payload)) as zf:
            names = set(zf.namelist())
            assert "RELEASE.md" in names
            assert "TESTER_INSTRUCTIONS.md" in names
            assert "DEPLOY_OR_SHARE.md" in names
            assert "app/src/index.html" in names

        workspace_snapshot_zip_name, workspace_snapshot_payload = sprintos.build_workspace_snapshot_zip(workspace_snapshot)
        assert workspace_snapshot_zip_name.endswith(".zip")
        with zipfile.ZipFile(io.BytesIO(workspace_snapshot_payload)) as zf:
            names = set(zf.namelist())
            assert "snapshot-manifest.json" in names
            assert "snapshot-report.md" in names
            assert "restore-instructions.md" in names
            assert ".env" not in names

        with urllib.request.urlopen(base_url + "/api/ai_status", timeout=5) as response:
            ai_status = json.loads(response.read().decode("utf-8"))
        assert "provider" in ai_status
        assert "usable" in ai_status

        with urllib.request.urlopen(base_url + "/api/ai_diagnostics?limit=20", timeout=5) as response:
            diagnostics_payload = json.loads(response.read().decode("utf-8"))
        assert "diagnostics" in diagnostics_payload
        assert diagnostics_payload["count"] >= 1
        assert isinstance(diagnostics_payload["diagnostics"], list)
        assert "generation_mode_requested" in diagnostics_payload["diagnostics"][0]
        assert quick_launch["generation_mode_requested"] == "offline"

        with urllib.request.urlopen(base_url + "/api/ai_routes", timeout=5) as response:
            routes_payload = json.loads(response.read().decode("utf-8"))
        assert len(routes_payload["routes"]) == len(sprintos.SUPPORTED_AI_TASK_NAMES)
        assert {item["task_name"] for item in routes_payload["routes"]} == set(sprintos.SUPPORTED_AI_TASK_NAMES)

        preset_payload = post_json("/api/apply_ai_route_preset", {"preset": "offline_only"})
        assert preset_payload["preset"] == "offline_only"
        assert all(item["provider"] == "offline" for item in preset_payload["routes"])

        eval_payload = post_json("/api/run_ai_provider_eval", {"eval_mode": "offline_eval"})
        assert eval_payload["summary"]["count"] == len(sprintos.SUPPORTED_AI_TASK_NAMES)
        assert len(eval_payload["results"]) == len(sprintos.SUPPORTED_AI_TASK_NAMES)

        with urllib.request.urlopen(base_url + "/api/ai_provider_evals?limit=20", timeout=5) as response:
            evals_payload = json.loads(response.read().decode("utf-8"))
        assert evals_payload["count"] >= len(sprintos.SUPPORTED_AI_TASK_NAMES)
        assert "estimated_total_cost_usd" in (evals_payload.get("summary") or {})

        with urllib.request.urlopen(base_url + "/api/ai_route_recommendations", timeout=5) as response:
            recommendations_payload = json.loads(response.read().decode("utf-8"))
        assert recommendations_payload["recommended_preset"] == "offline_only"
        assert all(item["provider"] == "offline" for item in recommendations_payload["routes"])

        quick_launch_after_preset = sprintos.run_quick_launch(
            raw_idea="Keep Quick Launch working after an offline-only routing preset is applied.",
            launch_goal="codex_build_ready",
            timebox_minutes=120,
            energy_level="medium",
            end_output="a local offline package",
        )
        assert quick_launch_after_preset["status"]
        assert quick_launch_after_preset["metadata"]["resolved_provider"] == "offline"
        assert not quick_launch_after_preset["metadata"]["used_ai"]

        server.shutdown()
        server.server_close()

    print("smoke ok")


if __name__ == "__main__":
    main()
