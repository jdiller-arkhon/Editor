import unittest
from montage_editor.config import Settings
from montage_editor.environment import detect_environment


class FoundationTests(unittest.TestCase):
    def test_settings_reject_invalid_dimensions(self):
        with self.assertRaises(ValueError):
            Settings(width=101)

    def test_environment_reports_runtime(self):
        self.assertIn("python", detect_environment())
