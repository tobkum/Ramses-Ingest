
import os
import re
import unittest
import logging
from unittest.mock import patch, MagicMock
from ramses_ingest.matcher import _validate_id, NamingRule, match_clip, Clip
from ramses_ingest.scanner import RE_FRAME_PADDING
from ramses_ingest.publisher import _calculate_md5

# Configure logging to capture matcher warnings
logging.basicConfig(level=logging.WARNING)

class TestAuditFixes(unittest.TestCase):

    def test_matcher_validate_id_logging(self):
        """Verify _validate_id returns empty string but logs a warning for invalid input."""
        with self.assertLogs('ramses_ingest.matcher', level='WARNING') as cm:
            result = _validate_id("invalid.name", "test_field")
            self.assertEqual(result, "")
            self.assertTrue(any("Invalid test_field format" in o for o in cm.output))

    def test_matcher_validate_id_path_traversal(self):
        """Verify path traversal is caught and logged."""
        with self.assertLogs('ramses_ingest.matcher', level='WARNING') as cm:
            result = _validate_id("../etc/passwd", "test_field")
            self.assertEqual(result, "")
            self.assertTrue(any("Potential path traversal" in o for o in cm.output))

    def test_matcher_version_parsing(self):
        """Verify version parsing handles non-integer versions gracefully."""
        # Setup a rule that captures a 'version' group
        rule = NamingRule(pattern=r"(?P<shot>\w+)_(?P<version>v\w+)")
        clip = Clip(base_name="SH010_vBad", extension="exr", directory=os.getcwd())
        
        # Should not crash, just ignore version
        with self.assertLogs('ramses_ingest.matcher', level='WARNING') as cm:
            result = match_clip(clip, [rule])
            self.assertEqual(result.shot_id, "SH010")
            self.assertIsNone(result.version)
            self.assertTrue(any("Could not parse version" in o for o in cm.output))

    def test_scanner_regex_underscores(self):
        """Verify scanner regex now supports underscores before frame numbers."""
        # Dot separator (standard)
        m1 = RE_FRAME_PADDING.match("shot.1001.exr")
        self.assertIsNotNone(m1)
        self.assertEqual(m1.group("base"), "shot")
        self.assertEqual(m1.group("frame"), "1001")

        # Underscore separator (newly supported)
        m2 = RE_FRAME_PADDING.match("shot_1001.exr")
        self.assertIsNotNone(m2)
        self.assertEqual(m2.group("base"), "shot")
        self.assertEqual(m2.group("frame"), "1001")

    @patch("builtins.open", side_effect=OSError("Disk failure"))
    def test_publisher_md5_failure(self, mock_open):
        """Verify _calculate_md5 raises OSError instead of returning empty string."""
        with self.assertRaises(OSError):
            _calculate_md5("dummy_path")

if __name__ == '__main__':
    unittest.main()
