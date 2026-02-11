# -*- coding: utf-8 -*-
"""Smart pattern inference for naming rule generation.

This module provides intelligent regex pattern generation from user-annotated examples.
Instead of manually building regex patterns, users highlight parts of example filenames
and the system infers flexible patterns that work across similar naming conventions.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple
from enum import Enum


class Flexibility(Enum):
    """Pattern flexibility levels."""
    EXACT = "exact"           # Exact string match (lowest flexibility)
    SPECIFIC = "specific"     # Character class with exact length
    FLEXIBLE = "flexible"     # Character class with variable length
    VERY_FLEXIBLE = "very_flexible"  # Broad pattern (highest flexibility)


@dataclass
class PatternCandidate:
    """A candidate regex pattern with metadata."""
    pattern: str              # The full regex pattern
    flexibility: Flexibility  # How flexible/general the pattern is
    confidence: float         # Confidence score (0.0 - 1.0)
    description: str          # Human-readable description

    def __repr__(self):
        return f"PatternCandidate(pattern={self.pattern!r}, confidence={self.confidence:.2f}, flexibility={self.flexibility.value})"


@dataclass
class Annotation:
    """User annotation of a field in an example."""
    example: str          # Full example string
    selected_text: str    # The text user selected/highlighted
    field_name: str       # Field type: "shot", "sequence", "resource"
    start_pos: int        # Start position in example
    end_pos: int          # End position in example


class PatternInferenceEngine:
    """Core engine for inferring regex patterns from user annotations."""

    # Common delimiters used in filename parsing
    DELIMITERS = r"_\-\.\s"

    def __init__(self):
        """Initialize the inference engine."""
        pass

    def infer_pattern(
        self,
        annotations: List[Annotation],
        test_examples: Optional[List[str]] = None
    ) -> List[PatternCandidate]:
        """
        Infer regex pattern(s) from user annotations.

        Args:
            annotations: List of user annotations (at least one required)
            test_examples: Optional list of examples to validate against

        Returns:
            List of PatternCandidate objects, sorted by confidence (highest first)
        """
        if not annotations:
            raise ValueError("At least one annotation is required")

        # Start with first annotation
        primary = annotations[0]

        # Generate candidates from primary annotation
        candidates = self._generate_candidates(primary)

        # If multiple annotations provided, refine patterns
        if len(annotations) > 1:
            candidates = self._refine_with_multiple_examples(candidates, annotations)

        # Test candidates against examples if provided
        if test_examples:
            candidates = self._score_candidates(candidates, test_examples, primary.field_name)

        # Sort by confidence (descending)
        candidates.sort(key=lambda c: c.confidence, reverse=True)

        return candidates

    def _generate_boundary_variations(self, right_boundary: str) -> List[str]:
        """
        Generate variations of right boundary to handle different cases.

        For example, if one example has "030.mov" and another has "030_REF.mp4",
        we need patterns that work for both.
        """
        variations = [right_boundary]  # Original boundary

        # If boundary is a specific delimiter, add variation that allows optional content
        if right_boundary in ["_", r"\.", "-"]:
            # Simpler: use lookahead to match any delimiter, dot, or end of string
            variations.append(f"(?=[{self.DELIMITERS}\\.]|$)")

        return variations

    def _generate_candidates(self, annotation: Annotation) -> List[PatternCandidate]:
        """
        Generate multiple pattern candidates from a single annotation.

        Strategy: Create patterns with varying levels of flexibility,
        from exact match to very general.
        """
        candidates = []
        example = annotation.example
        selected = annotation.selected_text
        field = annotation.field_name
        start = annotation.start_pos
        end = annotation.end_pos

        # Analyze what was selected
        char_pattern = self._analyze_character_pattern(selected)

        # Detect boundaries (what comes before/after)
        left_boundary = self._get_left_boundary(example, start)
        right_boundary = self._get_right_boundary(example, end)

        # Generate boundary variations for flexibility
        right_variations = self._generate_boundary_variations(right_boundary)

        # Generate candidates with increasing flexibility
        # For each flexibility level, try different boundary variations

        for right_b in right_variations:
            # 1. EXACT: Literal string match (useful for debugging, low confidence)
            candidates.append(PatternCandidate(
                pattern=f"{left_boundary}(?P<{field}>{re.escape(selected)}){right_b}",
                flexibility=Flexibility.EXACT,
                confidence=0.3,
                description=f"Exact match for '{selected}'"
            ))

            # 2. SPECIFIC: Character class with exact length
            if char_pattern['specific']:
                candidates.append(PatternCandidate(
                    pattern=f"{left_boundary}(?P<{field}>{char_pattern['specific']}){right_b}",
                    flexibility=Flexibility.SPECIFIC,
                    confidence=0.7,
                    description=f"Specific pattern: {char_pattern['specific']}"
                ))

            # 3. FLEXIBLE: Character class with variable length
            if char_pattern['flexible']:
                candidates.append(PatternCandidate(
                    pattern=f"{left_boundary}(?P<{field}>{char_pattern['flexible']}){right_b}",
                    flexibility=Flexibility.FLEXIBLE,
                    confidence=0.85,
                    description=f"Flexible pattern: {char_pattern['flexible']}"
                ))

            # 4. VERY_FLEXIBLE: Broad pattern (matches until delimiter)
            if char_pattern['very_flexible']:
                candidates.append(PatternCandidate(
                    pattern=f"{left_boundary}(?P<{field}>{char_pattern['very_flexible']}){right_b}",
                    flexibility=Flexibility.VERY_FLEXIBLE,
                    confidence=0.6,
                    description="Very flexible (match until delimiter)"
                ))

        return candidates

    def _analyze_character_pattern(self, text: str) -> dict:
        """
        Analyze character composition of selected text.

        Returns dict with different pattern representations:
        - specific: Exact character classes with fixed length
        - flexible: Character classes with variable length
        - very_flexible: Broad pattern (non-delimiter chars)
        """
        if not text:
            return {'specific': None, 'flexible': None, 'very_flexible': None}

        # Detect character composition
        has_upper = bool(re.search(r'[A-Z]', text))
        has_lower = bool(re.search(r'[a-z]', text))
        has_digit = bool(re.search(r'\d', text))
        has_other = bool(re.search(r'[^A-Za-z0-9]', text))

        # Count occurrences
        upper_count = len(re.findall(r'[A-Z]', text))
        lower_count = len(re.findall(r'[a-z]', text))
        digit_count = len(re.findall(r'\d', text))

        # Build patterns
        patterns = {}

        # SPECIFIC: Exact character class counts
        specific_parts = []
        if has_upper:
            specific_parts.append(f"[A-Z]{{{upper_count}}}")
        if has_lower:
            specific_parts.append(f"[a-z]{{{lower_count}}}")
        if has_digit:
            specific_parts.append(f"\\d{{{digit_count}}}")

        patterns['specific'] = ''.join(specific_parts) if specific_parts else None

        # FLEXIBLE: Variable length with character classes
        flexible_parts = []
        if has_upper and has_lower:
            # Mixed case letters
            flexible_parts.append("[A-Za-z]+")
            if has_digit:
                flexible_parts.append("\\d+")
        elif has_upper:
            flexible_parts.append("[A-Z]+")
            if has_digit:
                flexible_parts.append("\\d+")
        elif has_lower:
            flexible_parts.append("[a-z]+")
            if has_digit:
                flexible_parts.append("\\d+")
        elif has_digit:
            flexible_parts.append("\\d+")

        patterns['flexible'] = ''.join(flexible_parts) if flexible_parts else None

        # VERY_FLEXIBLE: Match anything except delimiters
        patterns['very_flexible'] = f"[^{self.DELIMITERS}]+"

        return patterns

    def _get_left_boundary(self, text: str, pos: int) -> str:
        """
        Determine the left boundary pattern for a selection.

        Args:
            text: Full text
            pos: Start position of selection

        Returns:
            Regex pattern for left boundary
        """
        if pos == 0:
            # Selection starts at beginning of string
            return "^"

        # Check what's immediately before
        prev_char = text[pos - 1]

        if prev_char in "_-.":
            # Selection follows a delimiter
            return re.escape(prev_char)
        elif prev_char == " ":
            return r"\s"
        else:
            # No clear delimiter - use lookahead for safety
            # This helps when selection is in middle of token
            return ""

    def _get_right_boundary(self, text: str, pos: int) -> str:
        """
        Determine the right boundary pattern for a selection.

        Returns the RIGHT boundary pattern seen in this specific example.
        Additional boundary variations are handled by _generate_boundary_variations().

        Args:
            text: Full text
            pos: End position of selection

        Returns:
            Regex pattern for right boundary
        """
        if pos >= len(text):
            # Selection ends at end of string
            return "$"

        # Check what's immediately after
        next_char = text[pos]

        if next_char in "_-.":
            # Selection precedes a delimiter
            return re.escape(next_char)
        elif next_char == " ":
            return r"\s"
        else:
            # No clear delimiter
            return ""

    def _refine_with_multiple_examples(
        self,
        candidates: List[PatternCandidate],
        annotations: List[Annotation]
    ) -> List[PatternCandidate]:
        """
        Refine pattern candidates using multiple annotated examples.

        This helps resolve ambiguities and increase confidence.
        """
        # For now, we'll boost confidence of patterns that work on all annotations
        # More sophisticated multi-example learning can be added later

        refined = []
        for candidate in candidates:
            match_count = 0
            for annotation in annotations:
                # Try to match the pattern and extract the field
                match = re.search(candidate.pattern, annotation.example)
                if match and annotation.field_name in match.groupdict():
                    extracted = match.group(annotation.field_name)
                    if extracted == annotation.selected_text:
                        match_count += 1

            # Boost confidence based on how many annotations it matches
            match_ratio = match_count / len(annotations)
            boosted_confidence = candidate.confidence * (0.5 + 0.5 * match_ratio)

            refined.append(PatternCandidate(
                pattern=candidate.pattern,
                flexibility=candidate.flexibility,
                confidence=boosted_confidence,
                description=candidate.description + f" (matched {match_count}/{len(annotations)} examples)"
            ))

        return refined

    def _score_candidates(
        self,
        candidates: List[PatternCandidate],
        test_examples: List[str],
        field_name: str
    ) -> List[PatternCandidate]:
        """
        Score candidates based on how well they extract from test examples.

        Good patterns should:
        1. Extract something from most/all examples
        2. Not extract duplicate values (unless genuinely same shot)
        3. Extract values of consistent format
        """
        scored = []

        for candidate in candidates:
            extractions = []
            match_count = 0

            for example in test_examples:
                match = re.search(candidate.pattern, example)
                if match and field_name in match.groupdict():
                    extracted = match.group(field_name)
                    extractions.append(extracted)
                    match_count += 1

            if not extractions:
                # Pattern doesn't extract anything - very low confidence
                scored.append(PatternCandidate(
                    pattern=candidate.pattern,
                    flexibility=candidate.flexibility,
                    confidence=0.1,
                    description=candidate.description + " (matched 0 examples)"
                ))
                continue

            # Calculate scores
            match_ratio = match_count / len(test_examples)
            unique_ratio = len(set(extractions)) / len(extractions) if extractions else 0

            # Good patterns match most examples and extract unique values
            score = candidate.confidence * (0.4 + 0.6 * match_ratio) * (0.7 + 0.3 * unique_ratio)

            scored.append(PatternCandidate(
                pattern=candidate.pattern,
                flexibility=candidate.flexibility,
                confidence=min(score, 1.0),
                description=f"{candidate.description} (matched {match_count}/{len(test_examples)}, {len(set(extractions))} unique)"
            ))

        return scored


def test_pattern(pattern: str, examples: List[str], field_name: str) -> List[Optional[str]]:
    """
    Test a pattern against examples and return extracted values.

    Args:
        pattern: Regex pattern with named capture group
        examples: List of example strings to test
        field_name: Name of the field to extract

    Returns:
        List of extracted values (None if no match)
    """
    results = []
    for example in examples:
        match = re.search(pattern, example)
        if match and field_name in match.groupdict():
            results.append(match.group(field_name))
        else:
            results.append(None)
    return results
