# -*- coding: utf-8 -*-
"""Batch-level validation for VFX pipeline quality checks.

Responsibilities:
    - Validate colorspace consistency across deliveries
    - Detect mixed primaries, transfer functions, and missing metadata
    - Flag potential rendering issues before ingest
    - Detect duplicate versions (Enhancement #9)
    - Validate frame ranges against EDL expectations (Enhancement #12)
"""

from __future__ import annotations

import os
import re
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ramses_ingest.publisher import IngestPlan
    from ramses_ingest.scanner import Clip

# Matches the trailing frame number in a filename: e.g. "shot.0001.exr" → 1
_RE_TRAILING_FRAME = re.compile(r"(\d+)\.[^.]+$")


def _first_frame_filename(file_list: list[str]) -> str:
    """Return the filename with the lowest frame number.

    Falls back to the alphabetically-first name if no frame numbers are found,
    so the function is safe for movie files and non-sequenced directories too.
    """
    def _sort_key(name: str):
        m = _RE_TRAILING_FRAME.search(name)
        # (has_frame_number inverted for ascending, frame_int, name)
        return (0, int(m.group(1)), name) if m else (1, 0, name)

    return min(file_list, key=_sort_key)


@dataclass
class ColorspaceIssue:
    """Represents a colorspace validation issue."""
    severity: str  # "critical", "warning", "info"
    message: str
    affected_primaries: set[str] = None

    def __post_init__(self):
        if self.affected_primaries is None:
            self.affected_primaries = set()


def validate_batch_colorspace(plans: list[IngestPlan]) -> dict[int, ColorspaceIssue]:
    """Validate colorspace consistency across a batch of plans.

    Critical issues (rendering-breaking):
        - Mixed color primaries (BT709 + BT2020)
        - Missing colorspace metadata in some clips

    Warning issues (potentially intentional):
        - Mixed transfer functions with same primaries

    Args:
        plans: List of IngestPlan objects to validate

    Returns:
        Dict mapping plan index to ColorspaceIssue (if any)
    """
    issues: dict[int, ColorspaceIssue] = {}

    if not plans:
        return issues

    # Extract colorspace profiles from matched plans only
    profiles = []
    for i, plan in enumerate(plans):
        # HERO ONLY: Auxiliary resources skip batch-level colorspace validation
        if not plan.match.matched or not plan.media_info.width or plan.resource:
            continue

        # Normalize to uppercase for consistent comparison
        profile = {
            'plan_idx': i,
            'primaries': (plan.media_info.color_primaries or "UNKNOWN").upper(),
            'transfer': (plan.media_info.color_transfer or "UNKNOWN").upper(),
            'space': (plan.media_info.color_space or "UNKNOWN").upper(),
        }
        profiles.append(profile)

    if len(profiles) < 2:
        return issues  # Single clip or all unmatched - nothing to compare

    # 1. Check for mixed primaries (CRITICAL - different color gamuts)
    primaries_set = set(p['primaries'] for p in profiles)

    # Define incompatible primaries combinations (Uppercase)
    incompatible_pairs = [
        ('BT709', 'BT2020'),
        ('BT709', 'FILM'),
        ('BT2020', 'FILM'),
        ('SMPTE170M', 'BT2020'),
    ]

    # Check if any incompatible pairs exist in the batch
    has_critical_mismatch = False
    for p1, p2 in incompatible_pairs:
        if p1 in primaries_set and p2 in primaries_set:
            has_critical_mismatch = True
            break

    if has_critical_mismatch and 'UNKNOWN' not in primaries_set:
        # Flag all clips with non-standard primaries
        most_common = max(set(p['primaries'] for p in profiles),
                         key=lambda x: sum(1 for p in profiles if p['primaries'] == x))

        for profile in profiles:
            if profile['primaries'] != most_common:
                issues[profile['plan_idx']] = ColorspaceIssue(
                    severity="critical",
                    message=f"Primaries mismatch: {profile['primaries']} (batch has mixed {', '.join(sorted(primaries_set))})",
                    affected_primaries=primaries_set
                )

    # 2. Check for missing metadata (CRITICAL - ambiguous assumptions)
    unknown_count = sum(1 for p in profiles if p['primaries'] == 'UNKNOWN')
    if unknown_count > 0 and unknown_count < len(profiles):
        # Some have metadata, some don't - this is critical
        for profile in profiles:
            if profile['primaries'] == 'UNKNOWN':
                issues[profile['plan_idx']] = ColorspaceIssue(
                    severity="critical",
                    message="Missing colorspace metadata (no VUI tags embedded in file)"
                )

    # 3. Check for transfer function mixing with same primaries (WARNING)
    # Group by primaries, then check for mixed transfers
    primaries_to_transfers: dict[str, set[str]] = {}
    for p in profiles:
        key = p['primaries']
        if key not in primaries_to_transfers:
            primaries_to_transfers[key] = set()
        primaries_to_transfers[key].add(p['transfer'])

    for primary, transfers in primaries_to_transfers.items():
        if len(transfers) > 1 and 'UNKNOWN' not in transfers and primary != 'UNKNOWN':
            # Multiple transfer functions for same primaries
            for profile in profiles:
                if profile['primaries'] == primary and profile['plan_idx'] not in issues:
                    # Only add warning if not already flagged as critical
                    issues[profile['plan_idx']] = ColorspaceIssue(
                        severity="warning",
                        message=f"Transfer function mismatch: {profile['transfer']} (primaries: {primary} has mixed transfers)"
                    )

    return issues


def check_for_duplicate_version(
    clip: Clip,
    existing_versions_dir: str,
    resource: str = "",
) -> tuple[bool, str, int]:
    """Check if a clip already exists in published versions (Enhancement #9).

    Uses a three-level check for efficiency:
    1. Resource check: match folder naming block
    2. Quick check: frame count
    3. Deep check: MD5 of first frame

    Args:
        clip: Source clip to check
        existing_versions_dir: Directory containing published versions (e.g., .../_published/)
        resource: Optional resource name to filter by.

    Returns:
        (is_duplicate, matching_version_path, matching_version_number)
        is_duplicate=False if no match found
    """
    if not os.path.isdir(existing_versions_dir):
        return False, "", 0

    # Quick check: frame count
    clip_frame_count = clip.frame_count if clip.is_sequence else 1

    # Scan existing versions
    # API Spec: [RESOURCE]_[VERSION]_[STATE]
    version_re = re.compile(r"^(?:(?P<res>[^_]+)_)?(?P<ver>\d{3})(?:_(?P<state>.*))?$")

    for item in sorted(os.listdir(existing_versions_dir)):
        match = version_re.match(item)
        if not match:
            continue

        # RESOURCE CHECK: Only compare against same resource stream
        folder_res = match.group("res") or ""
        if folder_res.upper() != resource.upper():
            continue

        version_dir = os.path.join(existing_versions_dir, item)
        if not os.path.isdir(version_dir):
            continue

        # Count frames in this version
        # Exclude metadata sidecars and completion markers
        EXCLUDE_FILES = ("_ramses_data.json", ".ramses_complete", ".DS_Store", "Thumbs.db")
        version_files = [
            f for f in os.listdir(version_dir)
            if os.path.isfile(os.path.join(version_dir, f)) and f not in EXCLUDE_FILES and not f.startswith("_")
        ]

        # Quick size check
        if len(version_files) != clip_frame_count:
            continue

        # Deep check: compare MD5 of first frame
        clip_first_md5 = _calculate_md5_safe(clip.first_file)
        if not clip_first_md5:
            continue

        # Find first frame in version directory by frame number (not alphabet)
        if version_files:
            version_first_file = os.path.join(version_dir, _first_frame_filename(version_files))
            version_first_md5 = _calculate_md5_safe(version_first_file)

            if clip_first_md5 == version_first_md5:
                version_num = int(match.group("ver"))
                return True, version_dir, version_num

    return False, "", 0


def _calculate_md5_safe(file_path: str) -> str:
    """Fast MD5 hash using strategic sampling (start, middle, end).
    
    Samples 512KB from three locations to detect duplicates while maintaining
    uniqueness even if files start with identical black leaders or color bars.
    
    NOTE: This is a probabilistic check (high confidence but not cryptographic certainty).
    It trades absolute certainty for 100x speed on large files.
    """
    try:
        if not os.path.exists(file_path):
            return ""

        size = os.path.getsize(file_path)
        chunk_size = 524288  # 512 KB
        
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            # 1. Sample start
            hash_md5.update(f.read(chunk_size))
            
            # 2. Sample middle (if file is large enough)
            if size > (chunk_size * 3):  # Need space for start, middle, and end
                f.seek(size // 2)
                hash_md5.update(f.read(chunk_size))
                
                # 3. Sample end (to catch trailing differences like burn-in)
                f.seek(max(0, size - chunk_size))
                hash_md5.update(f.read(chunk_size))
            elif size > chunk_size:
                # If file is small but bigger than 1 chunk, just read the rest
                hash_md5.update(f.read())
                
        return hash_md5.hexdigest()
    except (OSError, IOError) as e:
        # Log failure but return empty string to indicate hashing failed
        return ""


# Enhancement #12: EDL Frame Range Validation
@dataclass
class EDLExpectation:
    """Expected frame range for a clip from an EDL."""
    clip_name: str
    shot_id: str
    expected_first_frame: int
    expected_last_frame: int

    @property
    def expected_frame_count(self) -> int:
        return self.expected_last_frame - self.expected_first_frame + 1


class EDLValidator:
    """Enhanced EDL parser that extracts and validates frame ranges (Enhancement #12).

    Extends the basic EDL mapping to include frame range expectations.
    Parses CMX 3600 comments in the format: "SH010 1001-1096"
    """

    def __init__(self, edl_path: str) -> None:
        self.expectations: dict[str, EDLExpectation] = {}
        if edl_path and os.path.isfile(edl_path):
            self._parse_expectations(edl_path)

    def _parse_expectations(self, path: str) -> None:
        """Parse CMX 3600 comments like 'SH010 1001-1096' for frame ranges."""
        try:
            with open(path, "r", encoding="utf-8") as f:
                last_clip = ""
                for line in f:
                    line = line.strip()
                    if line.startswith("* FROM CLIP NAME:"):
                        last_clip = line.split(":")[-1].strip().upper()
                    elif line.startswith("* COMMENT:") and last_clip:
                        # Extract everything after the first "* COMMENT:"
                        comment = line[len("* COMMENT:"):].strip()
                        # Parse: "SH010 1001-1096" or "SH010: 1001-1096"
                        m = re.match(r"^([A-Za-z0-9_-]+)[:\s]+(\d+)-(\d+)$", comment)
                        if m:
                            shot_id, first, last = m.groups()
                            exp = EDLExpectation(
                                clip_name=last_clip,
                                shot_id=shot_id,
                                expected_first_frame=int(first),
                                expected_last_frame=int(last),
                            )
                            self.expectations[last_clip] = exp
        except Exception:
            pass

    def validate_clip(self, clip: Clip) -> tuple[bool, str]:
        """Check if clip matches EDL expectations.

        Args:
            clip: Clip to validate

        Returns:
            (is_valid, error_message) - error_message empty if valid
        """
        exp = self.expectations.get(clip.base_name.upper())
        if not exp:
            return True, ""  # No expectation = pass

        # Check frame range
        if not clip.is_sequence:
            # Movies: can't validate frame ranges from filename
            return True, ""

        if len(clip.frames) == 0:
            return False, "No frames detected"

        actual_first = clip.frames[0]
        actual_last = clip.frames[-1]
        actual_count = len(clip.frames)

        errors = []

        # Check first frame
        if actual_first != exp.expected_first_frame:
            errors.append(f"Start frame: expected {exp.expected_first_frame}, got {actual_first}")

        # Check last frame
        if actual_last != exp.expected_last_frame:
            errors.append(f"End frame: expected {exp.expected_last_frame}, got {actual_last}")

        # Check frame count (accounts for gaps)
        exp_count = exp.expected_frame_count
        if actual_count != exp_count:
            shortage = exp_count - actual_count
            errors.append(f"Frame count: expected {exp_count}, got {actual_count} ({shortage} frames short)")

        # Check for gaps
        if clip.missing_frames:
            gap_count = len(clip.missing_frames)
            if gap_count <= 5:
                errors.append(f"Missing frames: {clip.missing_frames}")
            else:
                errors.append(f"{gap_count} frames missing from range")

        if errors:
            error_msg = " | ".join(errors)
            return False, error_msg

        return True, ""


def validate_plans_against_edl(plans: list[IngestPlan], edl_path: str) -> dict[int, str]:
    """Validate all plans against EDL frame range expectations (Enhancement #12).

    Args:
        plans: List of IngestPlan objects to validate
        edl_path: Path to CMX 3600 EDL file

    Returns:
        Dict mapping plan index to error message (if validation failed)
    """
    if not edl_path or not os.path.isfile(edl_path):
        return {}

    validator = EDLValidator(edl_path)
    errors = {}

    for i, plan in enumerate(plans):
        if not plan.match.matched:
            continue

        is_valid, error = validator.validate_clip(plan.match.clip)
        if not is_valid:
            errors[i] = f"EDL validation: {error}"
            plan.error = errors[i]

    return errors
