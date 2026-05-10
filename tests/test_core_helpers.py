import sprintos

from tests.test_support import SprintOSTestCase


class CoreHelperTests(SprintOSTestCase):
    def test_safe_slug_generation_is_stable(self) -> None:
        self.assertEqual(sprintos.slugify("  Hello, SprintOS!  "), "hello-sprintos")
        self.assertEqual(sprintos.slugify("///", default="fallback"), "fallback")

    def test_filename_sanitization_blocks_path_segments_and_bad_suffixes(self) -> None:
        self.assertEqual(sprintos.sanitize_filename("../Bad Name!!.md"), "bad-name.md")
        self.assertEqual(sprintos.sanitize_filename("nested/folder/Project Plan.EXE"), "project-plan.exe")
