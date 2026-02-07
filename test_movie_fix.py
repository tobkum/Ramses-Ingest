"""Test movie file detection fix"""
from ramses_ingest.scanner import scan_directory

test_dir = r"X:\Geteilte Ablagen\2025-04-30_InSicknessAndInHealth\01-FROM_CLIENT\2025-09-20\TO VFX 092025 - Batch 2"

clips = scan_directory(test_dir)
print(f"Found {len(clips)} clips:\n")

for clip in clips:
    print(f"Name: {clip.base_name}.{clip.extension}")
    print(f"  Is sequence: {clip.is_sequence}")
    print(f"  Frame count: {clip.frame_count}")
    print(f"  First file: {clip.first_file}")
    print()
