
import unittest
import os
import shutil
from ramses_ingest.matcher import EDLMapper

class TestEDLFailures(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/tmp_edl"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_missing_file_raises_error(self):
        """Verify that a non-existent file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            EDLMapper("non_existent_file.edl")

    def test_malformed_file_utf8_error(self):
        """Verify that a binary file raises UnicodeDecodeError (simulating bad encoding)."""
        bad_file = os.path.join(self.test_dir, "bad_encoding.edl")
        with open(bad_file, "wb") as f:
            f.write(b"\x80")  # Invalid start byte for UTF-8

        with self.assertRaises(UnicodeDecodeError):
            EDLMapper(bad_file)

if __name__ == "__main__":
    unittest.main()
