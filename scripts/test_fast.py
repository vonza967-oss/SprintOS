import sys
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


FAST_TEST_TARGETS = [
    "tests.test_core_helpers",
    "tests.test_ai_providers.AIProviderTests",
    "tests.test_ai_providers.AIQualityLayerTests.test_ai_schema_validation_passes_valid_payload",
    "tests.test_ai_providers.AIQualityLayerTests.test_generation_mode_offline_never_attempts_provider_call",
    "tests.test_live_acceptance_script.LiveAcceptanceScriptTests",
    "tests.test_dashboard_flow.DashboardFlowTests.test_command_center_summary_for_project_with_only_sprint",
    "tests.test_dashboard_flow.DashboardFlowTests.test_today_dashboard_returns_empty_state_when_no_projects_exist",
    "tests.test_dashboard_flow.DashboardFlowTests.test_setup_doctor_endpoint_returns_expected_structure",
    "tests.test_dashboard_flow.DashboardFlowTests.test_today_dashboard_detects_active_focus_session",
    "tests.test_project_flow.QuickLaunchTests.test_quick_launch_creates_project_sprint_and_pipeline",
    "tests.test_workspace_flow.WorkspaceExportTests.test_export_workspace_creates_folder_and_copies_build_pack_files",
    "tests.test_release_flow.WorkspaceReleasePackTests.test_release_pack_folder_and_app_copy_are_created",
]


def build_suite(targets=None) -> unittest.TestSuite:
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite()
    for target in targets or FAST_TEST_TARGETS:
        suite.addTests(loader.loadTestsFromName(target))
    return suite


def run_targets(targets=None, verbosity: int = 2) -> bool:
    started = time.time()
    suite = build_suite(targets)
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    duration = time.time() - started
    print(f"\nFast test duration: {duration:.2f}s")
    return result.wasSuccessful()


def main() -> int:
    return 0 if run_targets() else 1


if __name__ == "__main__":
    raise SystemExit(main())
