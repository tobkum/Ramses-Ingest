# -*- coding: utf-8 -*-
"""Stress tests for Netflix VFX naming recommendation compliance."""

import unittest
import re
from ramses_ingest.pattern_inference import (
    PatternInferenceEngine,
    Annotation,
    test_pattern
)

class TestNetflixCompliance(unittest.TestCase):
    def setUp(self):
        self.engine = PatternInferenceEngine()

    def test_netflix_standard_shot(self):
        """Test standard Netflix [project]_[seq]_[shot]_[version] structure."""
        examples = [
            "BRG_101_0010_v001.mov",
            "BRG_101_0020_v002.mov",
            "BRG_102_0010_v001.mov"
        ]
        
        # User annotates shot "0010" in the first example
        annotations = {
            "sequence": Annotation(examples[0], "101", "sequence", 4, 7),
            "shot": Annotation(examples[0], "0010", "shot", 8, 12),
            "version": Annotation(examples[0], "v001", "version", 13, 17)
        }
        
        candidates = self.engine.infer_combined_pattern(annotations, test_examples=examples)
        self.assertGreater(len(candidates), 0)
        
        best = candidates[0]
        # Verify extraction across all examples
        for ex in examples:
            match = re.search(best.pattern, ex)
            self.assertIsNotNone(match, f"Pattern {best.pattern} failed to match {ex}")
            groups = match.groupdict()
            self.assertTrue(groups["shot"].isdigit())
            self.assertTrue(groups["version"].startswith('v'))

    def test_vendor_delivery_complex(self):
        """Test complex vendor naming: [project]_[ep]_[seq]_[shot]_[dept]_[vendor]_[version]."""
        examples = [
            "AGM_104_065_010_comp_NFX_v005.mov",
            "AGM_104_065_020_anim_OTB_v001.mov"
        ]
        
        # Annotate shot and complex resource
        annotations = {
            "shot": Annotation(examples[0], "010", "shot", 12, 15),
            "resource": Annotation(examples[0], "comp_NFX", "resource", 16, 24),
            "version": Annotation(examples[0], "v005", "version", 25, 29)
        }
        
        candidates = self.engine.infer_combined_pattern(annotations, test_examples=examples)
        best = candidates[0]
        
        # Check extraction of the second example
        match = re.search(best.pattern, examples[1])
        self.assertIsNotNone(match)
        self.assertEqual(match.group("resource"), "anim_OTB")
        self.assertEqual(match.group("shot"), "020")

    def test_concatenated_hybrid_boundaries(self):
        """Test concatenated fields which are common 'in the wild'."""
        examples = [
            "BRG101_SH0010v001.exr",
            "BRG101_SH0020v005.exr"
        ]
        
        annotations = {
            "sequence": Annotation(examples[0], "BRG101", "sequence", 0, 6),
            "shot": Annotation(examples[0], "SH0010", "shot", 7, 13),
            "version": Annotation(examples[0], "v001", "version", 13, 17)
        }
        
        candidates = self.engine.infer_combined_pattern(annotations, test_examples=examples)
        best = candidates[0]
        
        match = re.search(best.pattern, examples[1])
        self.assertIsNotNone(match)
        self.assertEqual(match.group("shot"), "SH0020")
        self.assertEqual(match.group("version"), "v005")

    def test_dynamic_length_inference(self):
        """Test that engine learns length variability from multiple annotations of same field."""
        examples = [
            "shot_1.mov",
            "shot_10.mov",
            "shot_100.mov"
        ]
        
        # Provide TWO annotations for the SAME field 'shot'
        # This tells the engine: "Look, the length varies!"
        annotations = {
            "shot": [
                Annotation(examples[0], "1", "shot", 5, 6),
                Annotation(examples[1], "10", "shot", 5, 7)
            ]
        }
        
        candidates = self.engine.infer_combined_pattern(annotations, test_examples=examples)
        best = candidates[0]
        
        # Best pattern should have inferred a range like \d{1,2} or \d+
        # and should match the 3-digit example too.
        match = re.search(best.pattern, examples[2])
        self.assertIsNotNone(match, f"Pattern {best.pattern} failed to handle variable length")
        self.assertEqual(match.group("shot"), "100")

if __name__ == "__main__":
    unittest.main()
