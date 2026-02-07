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
from dataclasses import dataclass
from typing import Optional

from ramses_ingest.scanner import Clip


@dataclass
class MatchResult:
    """The result of matching a clip to a shot/sequence identity."""

    clip: Clip
    sequence_id: str = ""
    shot_id: str = ""
    version: Optional[int] = None
    step_id: str = ""
    project_id: str = ""
    
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
    sequence_prefix: str = ""
    shot_prefix: str = ""
    use_parent_dir_as_sequence: bool = False
    """If True, ignore the regex for sequence and use the parent directory name."""

    def compile(self) -> re.Pattern:
        return re.compile(self.pattern, re.IGNORECASE)


class EDLMapper:
    """Maps clip names to shot IDs based on a CMX 3600 EDL file."""

    def __init__(self, edl_path: str) -> None:
        self.mappings: dict[str, str] = {} # clip_name -> shot_id
        self._parse(edl_path)

    def _parse(self, path: str) -> None:
        if not os.path.isfile(path):
            return
        
        # Simple CMX 3600 Parser
        try:
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
        except Exception:
            pass

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

    shot_id = (rule.shot_prefix + shot_raw) if shot_raw else ""
    seq_id = (rule.sequence_prefix + seq_raw) if seq_raw else ""

    # Capture Architect-specific tokens if present in regex
    ver_raw = groups.get("version", "")
    version = None
    if ver_raw:
        # Strip prefixes (like 'v') if they were caught in the group
        digits = re.search(r"(\d+)", ver_raw)
        if digits:
            version = int(digits.group(1))

    matched = bool(shot_id)  # Shot is mandatory
    return MatchResult(
        clip=clip,
        sequence_id=seq_id,
        shot_id=shot_id,
        version=version,
        step_id=groups.get("step", ""),
        project_id=groups.get("project", ""),
        matched=matched,
    )
