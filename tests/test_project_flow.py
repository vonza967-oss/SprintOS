from tests.test_sprintos import (
    _MovedCodexHandoffTests,
    _MovedFeedbackLoopTests,
    _MovedFocusSessionTests,
    _MovedPipelineRunTests,
    _MovedProjectStateTests,
    _MovedQuickLaunchTests,
    _MovedResumeModeTests,
)
from tests.test_support import SprintOSTestCase


class CodexHandoffTests(_MovedCodexHandoffTests, SprintOSTestCase):
    pass


class ProjectStateTests(_MovedProjectStateTests, SprintOSTestCase):
    pass


class ResumeModeTests(_MovedResumeModeTests, SprintOSTestCase):
    pass


class FocusSessionTests(_MovedFocusSessionTests, SprintOSTestCase):
    pass


class FeedbackLoopTests(_MovedFeedbackLoopTests, SprintOSTestCase):
    pass


class PipelineRunTests(_MovedPipelineRunTests, SprintOSTestCase):
    pass


class QuickLaunchTests(_MovedQuickLaunchTests, SprintOSTestCase):
    pass
