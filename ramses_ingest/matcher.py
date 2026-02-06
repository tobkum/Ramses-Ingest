# -*- coding: utf-8 -*-
"""Filename-to-shot/sequence matching.

Responsibilities:
    - Apply configurable regex rules to extract sequence and shot identifiers
      from clip base names or directory structure.
    - Support auto-detection heuristics for common naming conventions.
    - Return a ``MatchResult`` for each clip.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ramses_ingest.scanner import Clip


@dataclass
class MatchResult:
    """The result of matching a clip to a shot/sequence identity."""

    clip: Clip
    sequence_id: str = ""
    """Extracted sequence identifier (e.g. ``SEQ010``)."""

    shot_id: str = ""
    """Extracted shot identifier (e.g. ``SH010``)."""

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
        # Look for lines like: * FROM CLIP NAME:  SH010_PLATE
        # Followed by shot info
        current_shot = ""
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("* FROM CLIP NAME:"):
                        current_shot = line.split(":")[-1].strip()
                    elif line.startswith("* COMMENT:"):
                        # Sometimes shot IDs are in comments
                        pass
                    
                    # Store mapping if we find a clip name
                    if current_shot:
                        # Logic: Use the clip name as the key, but we might 
                        # need more logic to extract the 'real' shot ID.
                        # For now, assume CLIP NAME matches the desired Shot ID.
                        self.mappings[current_shot.upper()] = current_shot
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

    matched = bool(shot_id)  # Shot is mandatory; sequence can be defaulted later
    return MatchResult(
        clip=clip,
        sequence_id=seq_id,
        shot_id=shot_id,
        matched=matched,
    )
