
import sys
from unittest.mock import MagicMock

# Mock ramses module structure before importing publisher
ramses_mock = MagicMock()
sys.modules["ramses"] = ramses_mock
sys.modules["ramses.file_info"] = MagicMock()
sys.modules["ramses.constants"] = MagicMock()

# Also mock ramses.ram_settings due to import in gui.py (though we test publisher here)
# publisher -> register_ramses_objects -> ramses imports
sys.modules["ramses.ram_sequence"] = MagicMock()
sys.modules["ramses.ram_shot"] = MagicMock()
sys.modules["ramses.daemon_interface"] = MagicMock()

import unittest
import os
import shutil
from unittest.mock import patch
from ramses_ingest.publisher import execute_plan, IngestPlan, IngestResult
from ramses_ingest.prober import MediaInfo

class TestRollback(unittest.TestCase):
    def setUp(self):
        self.test_dir = "tests/tmp_rollback"
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        os.makedirs(self.test_dir)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    @patch("ramses_ingest.publisher.copy_frames")
    @patch("ramses_ingest.publisher._write_ramses_metadata")
    def test_rollback_on_metadata_failure(self, mock_meta, mock_copy):
        # Setup
        target_dir = os.path.join(self.test_dir, "v001")
        
        # Mock copy to simulate success and create the folder "as if" it did
        def side_effect_copy(*args, **kwargs):
            os.makedirs(target_dir, exist_ok=True)
            with open(os.path.join(target_dir, "test.exr"), "w") as f:
                f.write("data")
            return 1, "hash", 100, "test.exr"
        
        mock_copy.side_effect = side_effect_copy
        
        # Mock metadata to fail
        mock_meta.side_effect = Exception("Simulated Metadata Failure")

        match_mock = MagicMock()
        match_mock.matched = True
        match_mock.clip.frame_count = 1
        match_mock.clip.is_sequence = False
        
        plan = IngestPlan(
            match=match_mock,
            media_info=MediaInfo(),
            target_publish_dir=target_dir,
            project_id="TEST",
            shot_id="SH010",
            version=1,
            enabled=True
        )

        # Execute
        result = execute_plan(plan, generate_thumbnail=False, generate_proxy=False)

        # Verify
        self.assertFalse(result.success)
        self.assertIn("Simulated Metadata Failure", result.error)
        self.assertIn("Rolled back", result.error)
        
        # Check if directory was deleted
        self.assertFalse(os.path.exists(target_dir), "Target directory should have been deleted by rollback")

    @patch("ramses_ingest.publisher.copy_frames")
    def test_rollback_on_copy_failure(self, mock_copy):
        # Setup
        target_dir = os.path.join(self.test_dir, "v002")
        
        # Mock copy to fail, but let's say it created the dir before failing (simulating partial copy)
        def side_effect_copy(*args, **kwargs):
            os.makedirs(target_dir, exist_ok=True)
            raise OSError("Disk Full")
        
        mock_copy.side_effect = side_effect_copy

        match_mock = MagicMock()
        match_mock.matched = True
        match_mock.clip.frame_count = 1
        match_mock.clip.is_sequence = False
        
        plan = IngestPlan(
            match=match_mock,
            media_info=MediaInfo(),
            target_publish_dir=target_dir,
            project_id="TEST",
            shot_id="SH010",
            version=1,
            enabled=True
        )

        # Execute
        result = execute_plan(plan, generate_thumbnail=False, generate_proxy=False)

        # Verify
        self.assertFalse(result.success)
        self.assertIn("Disk Full", result.error)
        self.assertIn("Rolled back", result.error)
        
        # Check if directory was deleted
        self.assertFalse(os.path.exists(target_dir), "Target directory should have been deleted by rollback")

if __name__ == "__main__":
    unittest.main()
