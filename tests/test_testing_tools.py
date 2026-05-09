import contextlib
import io
from pathlib import Path
from unittest import mock

import scripts.launch as launch
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
