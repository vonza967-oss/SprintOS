from tests.test_sprintos import (
    _MovedVerificationRunTests,
    _MovedWorkspaceExportTests,
    _MovedWorkspaceSnapshotTests,
    _MovedWorkspaceSyncTests,
)
from tests.test_support import SprintOSTestCase


class WorkspaceExportTests(_MovedWorkspaceExportTests, SprintOSTestCase):
    pass


class WorkspaceSnapshotTests(_MovedWorkspaceSnapshotTests, SprintOSTestCase):
    pass


class WorkspaceSyncTests(_MovedWorkspaceSyncTests, SprintOSTestCase):
    pass


class VerificationRunTests(_MovedVerificationRunTests, SprintOSTestCase):
    pass
