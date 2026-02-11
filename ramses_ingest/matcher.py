# -*- coding: utf-8 -*-
"""Filename-to-shot/sequence matching.

Responsibilities:
    - Apply configurable regex rules to extract sequence and shot identifiers
      from clip base names or directory structure.
    - Support auto-detection heuristics for common naming conventions.
    - Return a ``MatchResult`` for each clip.
"""

from __future__ import annotations

import os
import re
import logging
from dataclasses import dataclass
from typing import Optional

from ramses_ingest.scanner import Clip


# Validation patterns for extracted IDs (security: prevent path traversal and injection)
_VALID_ID_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,64}$')
_VALID_STEP_PATTERN = re.compile(r'^[A-Z0-9_]{1,20}$')

# Cache for compiled regex patterns to avoid recompiling on every match
_PATTERN_CACHE: dict[str, re.Pattern] = {}

logger = logging.getLogger(__name__)


def _validate_id(value: str, field_name: str, pattern: re.Pattern = _VALID_ID_PATTERN) -> str:
    """Validate and sanitize extracted IDs.

    Args:
        value: The extracted value from regex
        field_name: Name of the field (for error reporting)
        pattern: Regex pattern to validate against

    Returns:
        Validated value or empty string if invalid

    Security: Prevents path traversal (../, ../../etc/passwd) and injection attacks
    """
    if not value:
        return ""

    # Remove whitespace
    value = value.strip()

    # Explicit path traversal check
    if ".." in value or "/" in value or "\\" in value:
        logger.warning(f"Potential path traversal in {field_name}: '{value}'")
        return ""

    # Check against pattern
    if not pattern.match(value):
        logger.warning(f"Invalid {field_name} format: '{value}'. Must match {pattern.pattern}")
        return ""  # Reject invalid IDs, but log it

    return value


@dataclass
class MatchResult:
    """The result of matching a clip to a shot/sequence identity."""

    clip: Clip
    sequence_id: str = ""
    shot_id: str = ""
    version: Optional[int] = None
    step_id: str = ""
    project_id: str = ""
    resource: str = ""
    
    matched: bool = False
    """True if the matcher was able to extract both identifiers."""


@dataclass
class NamingRule:
    """A configurable rule for extracting shot/sequence from a clip name.

    The ``pattern`` must contain named groups ``(?P<sequence>...)`` and/or
    ``(?P<shot>...)``.  Optional prefixes are prepended to the raw extracted
    values (e.g. prefix ``SH`` turns capture ``010`` into ``SH010``).
    """

    pattern: str
    name: str = ""
    """Optional user-friendly name for this rule (e.g., 'RO9S Project')."""
    sequence_prefix: str = ""
    shot_prefix: str = ""
    use_parent_dir_as_sequence: bool = False
    """If True, ignore the regex for sequence and use the parent directory name."""

    def compile(self) -> re.Pattern:
        """Compile the pattern, using cache to avoid redundant compilation."""
        if self.pattern not in _PATTERN_CACHE:
            _PATTERN_CACHE[self.pattern] = re.compile(self.pattern, re.IGNORECASE)
        return _PATTERN_CACHE[self.pattern]


class EDLMapper:
    """Maps clip names to shot IDs based on a CMX 3600 EDL file."""

    def __init__(self, edl_path: str) -> None:
        self.mappings: dict[str, str] = {} # clip_name -> shot_id
        self._parse(edl_path)

    def _parse(self, path: str) -> None:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"EDL file not found: {path}")
        
        # Simple CMX 3600 Parser
        with open(path, "r", encoding="utf-8") as f:
            last_clip = ""
            for line in f:
                line = line.strip()
                if line.startswith("* FROM CLIP NAME:"):
                    last_clip = line.split(":")[-1].strip().upper()
                    # Default: map clip to itself if no comment found later
                    self.mappings[last_clip] = last_clip
                elif line.startswith("* COMMENT:"):
                    comment = line.split(":")[-1].strip()
                    if last_clip:
                        # If we have a comment like '* COMMENT: SH010', map the clip to it
                        # Shot IDs are usually short alphanumeric strings
                        if re.match(r"^[A-Za-z0-9_-]+$", comment):
                            self.mappings[last_clip] = comment


    def get_shot_id(self, clip_name: str) -> str | None:
        return self.mappings.get(clip_name.upper())


# -- Built-in heuristics -----------------------------------------------------

# SEQ010_SH010  or  SEQ010_SH010_v01
RULE_SEQ_SHOT = NamingRule(
    pattern=r"(?P<sequence>[A-Za-z]*\d+)[_-](?P<shot>[A-Za-z]*\d+)",
)

# Directory-based: parent folder = sequence, filename prefix = shot
RULE_DIR_SEQUENCE = NamingRule(
    pattern=r"(?P<shot>[A-Za-z]*\d+)",
    use_parent_dir_as_sequence=True,
)

BUILTIN_RULES = [RULE_SEQ_SHOT, RULE_DIR_SEQUENCE]


def match_clip(clip: Clip, rules: list[NamingRule] | None = None) -> MatchResult:
    """Try to match *clip* against *rules* (falls back to built-in heuristics).

    Returns the first successful ``MatchResult``, or an unmatched result.
    """
    if rules is None:
        rules = BUILTIN_RULES

    for rule in rules:
        result = _try_rule(clip, rule)
        if result.matched:
            return result

    return MatchResult(clip=clip)


def match_clips(
    clips: list[Clip],
    rules: list[NamingRule] | None = None,
) -> list[MatchResult]:
    """Match a list of clips in bulk."""
    return [match_clip(c, rules) for c in clips]


def _try_rule(clip: Clip, rule: NamingRule) -> MatchResult:
    compiled = rule.compile()
    m = compiled.search(clip.base_name)
    if not m:
        return MatchResult(clip=clip)

    groups = m.groupdict()
    shot_raw = groups.get("shot", "")
    seq_raw = groups.get("sequence", "")

    if rule.use_parent_dir_as_sequence:
        seq_raw = clip.directory.name

    # Validate extracted IDs (security: prevent injection)
    shot_raw = _validate_id(shot_raw, "shot")
    seq_raw = _validate_id(seq_raw, "sequence")

    shot_id = (rule.shot_prefix + shot_raw) if shot_raw else ""
    seq_id = (rule.sequence_prefix + seq_raw) if seq_raw else ""

    # Capture Architect-specific tokens if present in regex
    ver_raw = groups.get("version", "")
    version = None
    if ver_raw:
        # Strip prefixes (like 'v') if they were caught in the group
        try:
            digits = re.search(r"(\d+)", ver_raw)
            if digits:
                version = int(digits.group(1))
            else:
                # Log warning if version group captured something but no digits found (e.g. "vBad")
                logger.warning(f"Could not parse version from '{ver_raw}'")
        except (ValueError, IndexError):
            # Log warning but don't fail the entire match just for version
            logger.warning(f"Could not parse version from '{ver_raw}'")

    # Validate additional fields
    step_raw = _validate_id(groups.get("step", ""), "step", _VALID_STEP_PATTERN)
    project_raw = _validate_id(groups.get("project", ""), "project")
    resource_raw = _validate_id(groups.get("resource", ""), "resource")

    matched = bool(shot_id)  # Shot is mandatory
    return MatchResult(
        clip=clip,
        sequence_id=seq_id,
        shot_id=shot_id,
        version=version,
        step_id=step_raw,
        project_id=project_raw,
        resource=resource_raw,
        matched=matched,
    )
