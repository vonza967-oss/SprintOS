import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "exports" / "live_app_generation_acceptance"


def _report_dirs() -> set[str]:
    if not REPORT_ROOT.exists():
        return set()
    return {path.name for path in REPORT_ROOT.iterdir() if path.is_dir()}


class LiveAcceptanceScriptTests(unittest.TestCase):
    def test_node_harness_refuses_without_confirm_and_does_not_create_report(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")
        before = _report_dirs()
        env = dict(os.environ)
        env.update(
            {
                "SPRINTOS_AI_ENABLED": "true",
                "SPRINTOS_AI_PROVIDER": "openai",
                "OPENAI_API_KEY": "sk-live-test-secret-that-must-not-appear",
            }
        )
        completed = subprocess.run(
            ["node", "scripts/live-app-generation-acceptance.mjs"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--confirm-live-provider", output)
        self.assertNotIn("sk-live-test-secret-that-must-not-appear", output)
        self.assertEqual(before, _report_dirs())

    def test_node_harness_refuses_confirmed_run_in_test_environment(self) -> None:
        if not shutil.which("node"):
            self.skipTest("node is not available")
        before = _report_dirs()
        env = dict(os.environ)
        env.update({"NODE_ENV": "test", "SPRINTOS_TEST_MODE": "true"})
        completed = subprocess.run(
            ["node", "scripts/live-app-generation-acceptance.mjs", "--confirm-live-provider", "--provider", "openai"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 2)
        self.assertIn("test environment", output)
        self.assertEqual(before, _report_dirs())

    def test_python_harness_also_refuses_without_confirm(self) -> None:
        before = _report_dirs()
        completed = subprocess.run(
            [sys.executable, "scripts/live_app_generation_acceptance.py"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--confirm-live-provider", output)
        self.assertEqual(before, _report_dirs())

    def test_python_harness_refuses_confirmed_run_in_test_environment(self) -> None:
        before = _report_dirs()
        env = dict(os.environ)
        env.update(
            {
                "SPRINTOS_TEST_MODE": "true",
                "SPRINTOS_AI_ENABLED": "true",
                "SPRINTOS_AI_PROVIDER": "openai",
                "OPENAI_API_KEY": "sk-live-test-secret-that-must-not-appear",
            }
        )
        completed = subprocess.run(
            [sys.executable, "scripts/live_app_generation_acceptance.py", "--confirm-live-provider", "--provider", "openai"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        output = completed.stdout + completed.stderr
        self.assertEqual(completed.returncode, 2)
        self.assertIn("test environment", output)
        self.assertNotIn("sk-live-test-secret-that-must-not-appear", output)
        self.assertEqual(before, _report_dirs())

    def test_fast_full_smoke_and_health_do_not_run_live_acceptance(self) -> None:
        checked_files = (
            ROOT / "scripts" / "test_fast.py",
            ROOT / "scripts" / "test_full.py",
            ROOT / "scripts" / "smoke.py",
            ROOT / "scripts" / "health.py",
        )
        for path in checked_files:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("live_app_generation_acceptance.py", text)
            self.assertNotIn("live-app-generation-acceptance.mjs", text)


if __name__ == "__main__":
    unittest.main()
