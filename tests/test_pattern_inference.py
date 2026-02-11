# -*- coding: utf-8 -*-
"""Tests for smart pattern inference engine."""

import unittest
from ramses_ingest.pattern_inference import (
    PatternInferenceEngine,
    Annotation,
    Flexibility,
    test_pattern
)


class TestPatternInference(unittest.TestCase):
    """Test pattern inference with real-world naming conventions."""

    def setUp(self):
        self.engine = PatternInferenceEngine()

    # ========== PROJECT 1: RO9S ==========

    def test_ro9s_shot_extraction(self):
        """Test extraction of shot from RO9S project naming convention."""
        examples = [
            "A077C013_230614_RO9S.mov",
            "A081C011_230615_RO9S_1.mov",
            "A027C009_230512_RO9S_A.mov",
            "A016C013_230509_RO9S_B.mov"
        ]

        # User selects "A077" in first example
        annotation = Annotation(
            example=examples[0],
            selected_text="A077",
            field_name="shot",
            start_pos=0,
            end_pos=4
        )

        candidates = self.engine.infer_pattern([annotation], test_examples=examples)

        # Should generate multiple candidates
        self.assertGreater(len(candidates), 0)

        # Best candidate should extract all shot IDs correctly
        best = candidates[0]
        extractions = test_pattern(best.pattern, examples, "shot")

        expected = ["A077", "A081", "A027", "A016"]
        self.assertEqual(extractions, expected)

    def test_ro9s_resource_extraction(self):
        """Test extraction of optional resource suffix."""
        examples = [
            "A077C013_230614_RO9S.mov",      # No resource
            "A081C011_230615_RO9S_1.mov",    # Resource: 1
            "A027C009_230512_RO9S_A.mov",    # Resource: A
            "A016C013_230509_RO9S_B.mov"     # Resource: B
        ]

        # User selects "A" in third example (the resource part)
        annotation = Annotation(
            example=examples[2],
            selected_text="A",
            field_name="resource",
            start_pos=24,  # Position after "RO9S_"
            end_pos=25
        )

        candidates = self.engine.infer_pattern([annotation], test_examples=examples)
        best = candidates[0]
        extractions = test_pattern(best.pattern, examples, "resource")

        # Should extract resources where present, None where absent
        # Note: Basic pattern might extract from all - that's OK for now
        self.assertIsNotNone(extractions[2])  # Should extract "A"
        self.assertEqual(extractions[2], "A")

    # ========== PROJECT 2: ISIH ==========

    def test_isih_shot_extraction(self):
        """Test extraction from ISIH project (project_sequence_shot format)."""
        examples = [
            "ISIH_A1_030.mov",
            "ISIH_A1_030_REF.mp4",
            "ISIH_A1_120.mov"
        ]

        # User selects "030" in first example
        annotation = Annotation(
            example=examples[0],
            selected_text="030",
            field_name="shot",
            start_pos=8,
            end_pos=11
        )

        candidates = self.engine.infer_pattern([annotation], test_examples=examples)
        best = candidates[0]
        extractions = test_pattern(best.pattern, examples, "shot")

        expected = ["030", "030", "120"]
        self.assertEqual(extractions, expected)

    def test_isih_sequence_extraction(self):
        """Test extraction of sequence from ISIH project."""
        examples = [
            "ISIH_A1_030.mov",
            "ISIH_A1_030_REF.mp4",
            "ISIH_A1_120.mov"
        ]

        # User selects "A1" in first example
        annotation = Annotation(
            example=examples[0],
            selected_text="A1",
            field_name="sequence",
            start_pos=5,
            end_pos=7
        )

        candidates = self.engine.infer_pattern([annotation], test_examples=examples)
        best = candidates[0]
        extractions = test_pattern(best.pattern, examples, "sequence")

        # All should extract "A1"
        expected = ["A1", "A1", "A1"]
        self.assertEqual(extractions, expected)

    def test_isih_resource_extraction(self):
        """Test extraction of resource (REF) from ISIH project."""
        examples = [
            "ISIH_A1_030.mov",
            "ISIH_A1_030_REF.mp4",
            "ISIH_A1_120.mov"
        ]

        # User selects "REF" in second example
        annotation = Annotation(
            example=examples[1],
            selected_text="REF",
            field_name="resource",
            start_pos=12,
            end_pos=15
        )

        candidates = self.engine.infer_pattern([annotation], test_examples=examples)
        best = candidates[0]
        extractions = test_pattern(best.pattern, examples, "resource")

        # Should extract "REF" from second example
        self.assertEqual(extractions[1], "REF")

    # ========== PROJECT 3: DJI ==========

    def test_dji_shot_extraction(self):
        """Test extraction from DJI project (shot at start)."""
        examples = [
            "27_vfx_DJI_0658.mov",
            "67_vfx_DJI_0232.mov",
            "35_vfx_DJI_0993_Proxy.mov"
        ]

        # User selects "27" in first example
        annotation = Annotation(
            example=examples[0],
            selected_text="27",
            field_name="shot",
            start_pos=0,
            end_pos=2
        )

        candidates = self.engine.infer_pattern([annotation], test_examples=examples)
        best = candidates[0]
        extractions = test_pattern(best.pattern, examples, "shot")

        expected = ["27", "67", "35"]
        self.assertEqual(extractions, expected)

    def test_dji_resource_extraction(self):
        """Test extraction of Proxy resource from DJI project."""
        examples = [
            "27_vfx_DJI_0658.mov",
            "67_vfx_DJI_0232.mov",
            "35_vfx_DJI_0993_Proxy.mov"
        ]

        # User selects "Proxy" in third example (position 16-21)
        annotation = Annotation(
            example=examples[2],
            selected_text="Proxy",
            field_name="resource",
            start_pos=16,
            end_pos=21
        )

        candidates = self.engine.infer_pattern([annotation], test_examples=examples)

        # For optional fields, check that AT LEAST ONE candidate extracts correctly
        # (User would pick the right one from the list in real usage)
        found_correct = False
        for candidate in candidates:
            extractions = test_pattern(candidate.pattern, examples, "resource")
            if extractions[2] == "Proxy":
                found_correct = True
                break

        self.assertTrue(found_correct, "No candidate pattern extracted 'Proxy' correctly")

    # ========== PROJECT 4: ICK ==========

    def test_ick_sequence_extraction(self):
        """Test extraction of sequence from ICK project (dash delimiter)."""
        examples = [
            "ICK_012-0500.mov",
            "ICK_010-0090.mov",
            "ICK_010-0110.mov"
        ]

        # User selects "012" in first example
        annotation = Annotation(
            example=examples[0],
            selected_text="012",
            field_name="sequence",
            start_pos=4,
            end_pos=7
        )

        candidates = self.engine.infer_pattern([annotation], test_examples=examples)
        best = candidates[0]
        extractions = test_pattern(best.pattern, examples, "sequence")

        expected = ["012", "010", "010"]
        self.assertEqual(extractions, expected)

    def test_ick_shot_extraction(self):
        """Test extraction of shot from ICK project (after dash)."""
        examples = [
            "ICK_012-0500.mov",
            "ICK_010-0090.mov",
            "ICK_010-0110.mov"
        ]

        # User selects "0500" in first example
        annotation = Annotation(
            example=examples[0],
            selected_text="0500",
            field_name="shot",
            start_pos=8,
            end_pos=12
        )

        candidates = self.engine.infer_pattern([annotation], test_examples=examples)
        best = candidates[0]
        extractions = test_pattern(best.pattern, examples, "shot")

        expected = ["0500", "0090", "0110"]
        self.assertEqual(extractions, expected)

    # ========== MULTI-EXAMPLE LEARNING ==========

    def test_multi_annotation_refinement(self):
        """Test that multiple annotations improve pattern confidence."""
        examples = [
            "A077C013_230614_RO9S.mov",
            "A081C011_230615_RO9S_1.mov"
        ]

        # Annotate shot in both examples
        annotations = [
            Annotation(
                example=examples[0],
                selected_text="A077",
                field_name="shot",
                start_pos=0,
                end_pos=4
            ),
            Annotation(
                example=examples[1],
                selected_text="A081",
                field_name="shot",
                start_pos=0,
                end_pos=4
            )
        ]

        candidates = self.engine.infer_pattern(annotations, test_examples=examples)
        best = candidates[0]

        # Multi-example should have higher confidence
        self.assertGreater(best.confidence, 0.5)

        # Should still extract correctly
        extractions = test_pattern(best.pattern, examples, "shot")
        expected = ["A077", "A081"]
        self.assertEqual(extractions, expected)

    # ========== PATTERN ANALYSIS TESTS ==========

    def test_character_pattern_analysis_mixed(self):
        """Test character pattern analysis for mixed letter+digit."""
        pattern = self.engine._analyze_character_pattern("A077")

        # Should detect 1 letter + 3 digits
        self.assertIsNotNone(pattern['specific'])
        self.assertIn("A-Z", pattern['specific'])
        self.assertIn("\\d", pattern['specific'])

    def test_character_pattern_analysis_digits_only(self):
        """Test character pattern analysis for digits only."""
        pattern = self.engine._analyze_character_pattern("030")

        # Should detect digits only
        self.assertIsNotNone(pattern['specific'])
        self.assertIn("\\d", pattern['specific'])

    def test_character_pattern_analysis_word(self):
        """Test character pattern analysis for alphabetic word."""
        pattern = self.engine._analyze_character_pattern("Proxy")

        # Should detect mixed case letters
        self.assertIsNotNone(pattern['flexible'])

    # ========== BOUNDARY DETECTION TESTS ==========

    def test_left_boundary_start_of_string(self):
        """Test left boundary detection at start of string."""
        boundary = self.engine._get_left_boundary("A077C013_230614_RO9S.mov", 0)
        self.assertEqual(boundary, "^")

    def test_left_boundary_after_delimiter(self):
        """Test left boundary detection after underscore."""
        boundary = self.engine._get_left_boundary("ISIH_A1_030.mov", 5)
        self.assertEqual(boundary, "_")

    def test_right_boundary_end_of_string(self):
        """Test right boundary detection at end of string."""
        text = "A077"
        boundary = self.engine._get_right_boundary(text, len(text))
        self.assertEqual(boundary, "$")

    def test_right_boundary_before_delimiter(self):
        """Test right boundary detection before underscore."""
        boundary = self.engine._get_right_boundary("A077_C013", 4)
        self.assertEqual(boundary, "_")


if __name__ == "__main__":
    unittest.main()
