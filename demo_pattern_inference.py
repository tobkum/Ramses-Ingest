# -*- coding: utf-8 -*-
"""Demo of the smart pattern inference engine."""

from ramses_ingest.pattern_inference import (
    PatternInferenceEngine,
    Annotation,
    test_pattern
)


def demo_project(name, examples, annotation_data):
    """Run inference demo for a project."""
    print(f"\n{'='*60}")
    print(f"PROJECT: {name}")
    print(f"{'='*60}")

    print(f"\nExamples:")
    for i, ex in enumerate(examples, 1):
        print(f"  {i}. {ex}")

    print(f"\nUser annotates: '{annotation_data['selected_text']}' as {annotation_data['field_name']}")

    engine = PatternInferenceEngine()
    annotation = Annotation(**annotation_data)

    candidates = engine.infer_pattern([annotation], test_examples=examples)

    print(f"\nTop 3 Pattern Candidates:")
    for i, candidate in enumerate(candidates[:3], 1):
        print(f"\n{i}. Confidence: {candidate.confidence:.2f} ({candidate.flexibility.value})")
        print(f"   Pattern: {candidate.pattern}")
        print(f"   Description: {candidate.description}")

        extractions = test_pattern(candidate.pattern, examples, annotation_data['field_name'])
        print(f"   Results:")
        for ex, val in zip(examples, extractions):
            val_str = f"'{val}'" if val else "None"
            print(f"      {ex} -> {val_str}")


def main():
    """Run demos for all real-world projects."""

    # Project 1: RO9S
    demo_project(
        "RO9S (Letter+Digit Shot IDs)",
        examples=[
            "A077C013_230614_RO9S.mov",
            "A081C011_230615_RO9S_1.mov",
            "A027C009_230512_RO9S_A.mov",
            "A016C013_230509_RO9S_B.mov"
        ],
        annotation_data={
            "example": "A077C013_230614_RO9S.mov",
            "selected_text": "A077",
            "field_name": "shot",
            "start_pos": 0,
            "end_pos": 4
        }
    )

    # Project 2: ISIH
    demo_project(
        "ISIH (Project_Sequence_Shot format)",
        examples=[
            "ISIH_A1_030.mov",
            "ISIH_A1_030_REF.mp4",
            "ISIH_A1_120.mov"
        ],
        annotation_data={
            "example": "ISIH_A1_030.mov",
            "selected_text": "030",
            "field_name": "shot",
            "start_pos": 8,
            "end_pos": 11
        }
    )

    # Project 3: DJI
    demo_project(
        "DJI (Shot at start, rest irrelevant)",
        examples=[
            "27_vfx_DJI_0658.mov",
            "67_vfx_DJI_0232.mov",
            "35_vfx_DJI_0993_Proxy.mov"
        ],
        annotation_data={
            "example": "27_vfx_DJI_0658.mov",
            "selected_text": "27",
            "field_name": "shot",
            "start_pos": 0,
            "end_pos": 2
        }
    )

    # Project 4: ICK
    demo_project(
        "ICK (Sequence-Shot with dash delimiter)",
        examples=[
            "ICK_012-0500.mov",
            "ICK_010-0090.mov",
            "ICK_010-0110.mov"
        ],
        annotation_data={
            "example": "ICK_012-0500.mov",
            "selected_text": "0500",
            "field_name": "shot",
            "start_pos": 8,
            "end_pos": 12
        }
    )


if __name__ == "__main__":
    main()
