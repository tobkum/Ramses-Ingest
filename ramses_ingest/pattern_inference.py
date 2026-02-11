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
        - specific: Exact character classes tracking consecutive runs
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

        # Build patterns
        patterns = {}

        # SPECIFIC: Track consecutive runs of character types
        # Example: "RO9S" -> [A-Z]{2}\d{1}[A-Z]{1}
        specific_parts = []
        i = 0
        while i < len(text):
            char = text[i]
            if char.isupper():
                count = 0
                while i < len(text) and text[i].isupper():
                    count += 1
                    i += 1
                specific_parts.append(f"[A-Z]{{{count}}}")
            elif char.islower():
                count = 0
                while i < len(text) and text[i].islower():
                    count += 1
                    i += 1
                specific_parts.append(f"[a-z]{{{count}}}")
            elif char.isdigit():
                count = 0
                while i < len(text) and text[i].isdigit():
                    count += 1
                    i += 1
                specific_parts.append(f"\\d{{{count}}}")
            else:
                # Other characters
                specific_parts.append(re.escape(char))
                i += 1

        patterns['specific'] = ''.join(specific_parts) if specific_parts else None

        # FLEXIBLE: Check for interleaving
        # If letters and digits are interleaved (multiple transitions), use combined class
        transitions = 0
        prev_type = None
        for char in text:
            if char.isalpha():
                curr_type = 'alpha'
            elif char.isdigit():
                curr_type = 'digit'
            else:
                curr_type = 'other'

            if prev_type and prev_type != curr_type and prev_type != 'other' and curr_type != 'other':
                transitions += 1
            prev_type = curr_type

        # If interleaved (2+ transitions), use combined pattern
        if transitions >= 2 and (has_upper or has_lower) and has_digit:
            # Interleaved alphanumeric - use combined class
            if has_upper and has_lower:
                patterns['flexible'] = "[A-Za-z0-9]+"
            elif has_upper:
                patterns['flexible'] = "[A-Z0-9]+"
            else:
                patterns['flexible'] = "[a-z0-9]+"
        else:
            # Not interleaved - use separate classes
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


    def infer_combined_pattern(
        self,
        annotations: dict[str, Annotation],
        test_examples: Optional[List[str]] = None
    ) -> List[PatternCandidate]:
        """
        Infer a combined regex pattern from multiple field annotations.

        This method takes annotations for multiple fields (e.g., shot, sequence)
        and generates combined regex patterns that extract all fields.

        Args:
            annotations: Dict mapping field_name -> Annotation (e.g., {"shot": ann1, "sequence": ann2})
            test_examples: Optional list of examples to validate against

        Returns:
            List of PatternCandidate objects for combined patterns, sorted by confidence

        Raises:
            ValueError: If annotations is empty or annotations span different examples
        """
        if not annotations:
            raise ValueError("At least one annotation is required")

        # Ensure all annotations reference the same example
        examples = {ann.example for ann in annotations.values()}
        if len(examples) > 1:
            raise ValueError("All annotations must reference the same example string")

        base_example = list(annotations.values())[0].example

        # Sort annotations by position (left to right)
        sorted_fields = sorted(
            annotations.items(),
            key=lambda x: x[1].start_pos
        )

        # Extract context fragments between annotations
        context_fragments = self._extract_context_between(base_example, [ann for _, ann in sorted_fields])

        # Generate combined patterns at different flexibility levels
        combined_candidates = []

        # For each flexibility level, build a combined pattern
        for flexibility in [Flexibility.SPECIFIC, Flexibility.FLEXIBLE, Flexibility.VERY_FLEXIBLE]:
            # Build pattern parts for each field
            # Note: For VERY_FLEXIBLE, we use flexible patterns for fields
            # but very flexible patterns for separators
            field_patterns = {}
            for field_name, annotation in annotations.items():
                char_pattern = self._analyze_character_pattern(annotation.selected_text)

                if flexibility == Flexibility.SPECIFIC and char_pattern['specific']:
                    field_patterns[field_name] = char_pattern['specific']
                elif flexibility in [Flexibility.FLEXIBLE, Flexibility.VERY_FLEXIBLE]:
                    # Use flexible patterns for fields even in VERY_FLEXIBLE mode
                    # VERY_FLEXIBLE mainly affects separators
                    if char_pattern['flexible']:
                        field_patterns[field_name] = char_pattern['flexible']
                    else:
                        field_patterns[field_name] = char_pattern['specific'] or re.escape(annotation.selected_text)
                else:
                    # Fallback if pattern doesn't exist for this flexibility
                    field_patterns[field_name] = re.escape(annotation.selected_text)

            # Stitch together the combined pattern
            pattern_parts = []

            # Add start anchor if first annotation starts at beginning
            if sorted_fields[0][1].start_pos == 0:
                pattern_parts.append("^")
            elif context_fragments['prefix']:
                pattern_parts.append(re.escape(context_fragments['prefix']))

            # Add fields with their separators
            for i, (field_name, annotation) in enumerate(sorted_fields):
                # Add the field capture group
                pattern_parts.append(f"(?P<{field_name}>{field_patterns[field_name]})")

                # Add separator/context after this field (if not last)
                if i < len(sorted_fields) - 1:
                    separator = context_fragments['separators'][i]
                    if separator:
                        # Convert separator to flexible pattern
                        sep_pattern = self._separator_to_pattern(separator, flexibility)
                        pattern_parts.append(sep_pattern)

            # Add suffix
            if context_fragments['suffix']:
                pattern_parts.append(re.escape(context_fragments['suffix']))
            else:
                pattern_parts.append(".*$")

            combined_pattern = "".join(pattern_parts)

            # Determine confidence based on flexibility
            base_confidence = {
                Flexibility.SPECIFIC: 0.7,
                Flexibility.FLEXIBLE: 0.85,
                Flexibility.VERY_FLEXIBLE: 0.6
            }[flexibility]

            combined_candidates.append(PatternCandidate(
                pattern=combined_pattern,
                flexibility=flexibility,
                confidence=base_confidence,
                description=f"Combined {len(annotations)}-field pattern ({flexibility.value})"
            ))

        # Score candidates against test examples if provided
        if test_examples:
            combined_candidates = self._score_combined_candidates(
                combined_candidates,
                test_examples,
                list(annotations.keys())
            )

        # Sort by confidence
        combined_candidates.sort(key=lambda c: c.confidence, reverse=True)

        return combined_candidates

    def _separator_to_pattern(self, separator: str, flexibility: Flexibility) -> str:
        """
        Convert a literal separator into a flexible regex pattern.

        Args:
            separator: The literal separator text (e.g., "_A1_", "_", ".")
            flexibility: How flexible the pattern should be

        Returns:
            Regex pattern for the separator
        """
        if not separator:
            return ""

        # Detect if it's a simple delimiter (just punctuation/whitespace)
        if all(c in "_-. \t" for c in separator):
            # Simple delimiter - use literal
            return re.escape(separator)

        # Check if separator is complex (contains multiple components/tokens)
        # Example: "C013_230614_" has multiple number groups separated by _
        token_count = len(re.findall(r'[A-Za-z]+|\d+', separator))

        # If separator has many tokens (> 2), it's likely variable data
        # Use non-greedy wildcard for flexibility
        if token_count > 2:
            if flexibility == Flexibility.SPECIFIC:
                return re.escape(separator)
            else:
                # Use non-greedy wildcard to match until next field
                return r".*?"

        # Mixed content separator (contains alphanumeric)
        if flexibility == Flexibility.SPECIFIC:
            # For specific, use exact match
            return re.escape(separator)
        elif flexibility == Flexibility.FLEXIBLE:
            # For flexible, replace alphanumeric runs with character classes
            # "_A1_" -> "_[A-Z]+\d+_"
            pattern = ""
            i = 0
            while i < len(separator):
                char = separator[i]
                if char in "_-. \t":
                    pattern += re.escape(char)
                    i += 1
                elif char.isalpha():
                    # Collect consecutive letters
                    start = i
                    while i < len(separator) and separator[i].isalpha():
                        i += 1
                    letters = separator[start:i]
                    if letters.isupper():
                        pattern += "[A-Z]+"
                    elif letters.islower():
                        pattern += "[a-z]+"
                    else:
                        pattern += "[A-Za-z]+"
                elif char.isdigit():
                    # Collect consecutive digits
                    while i < len(separator) and separator[i].isdigit():
                        i += 1
                    pattern += r"\d+"
                else:
                    pattern += re.escape(char)
                    i += 1
            return pattern
        else:  # VERY_FLEXIBLE
            # For very flexible, use non-greedy wildcard
            return r".*?"

    def _extract_context_between(
        self,
        example: str,
        sorted_annotations: List[Annotation]
    ) -> dict:
        """
        Extract literal text fragments between annotations.

        Args:
            example: The full example string
            sorted_annotations: Annotations sorted by start_pos (left to right)

        Returns:
            Dict with 'prefix', 'separators' (list), and 'suffix'
        """
        context = {
            'prefix': '',
            'separators': [],
            'suffix': ''
        }

        if not sorted_annotations:
            return context

        # Prefix: text before first annotation
        first_ann = sorted_annotations[0]
        if first_ann.start_pos > 0:
            context['prefix'] = example[:first_ann.start_pos]

        # Separators: text between consecutive annotations
        for i in range(len(sorted_annotations) - 1):
            curr_ann = sorted_annotations[i]
            next_ann = sorted_annotations[i + 1]

            separator = example[curr_ann.end_pos:next_ann.start_pos]
            context['separators'].append(separator)

        # Suffix: text after last annotation
        last_ann = sorted_annotations[-1]
        if last_ann.end_pos < len(example):
            context['suffix'] = example[last_ann.end_pos:]

        return context

    def _score_combined_candidates(
        self,
        candidates: List[PatternCandidate],
        test_examples: List[str],
        field_names: List[str]
    ) -> List[PatternCandidate]:
        """
        Score combined pattern candidates based on multi-field extraction quality.

        Args:
            candidates: List of pattern candidates to score
            test_examples: Examples to test against
            field_names: List of field names that should be extracted

        Returns:
            List of scored candidates
        """
        scored = []

        for candidate in candidates:
            extractions = {field: [] for field in field_names}
            full_match_count = 0

            for example in test_examples:
                match = re.search(candidate.pattern, example)
                if match:
                    groups = match.groupdict()
                    # Check if ALL required fields were extracted
                    if all(field in groups and groups[field] for field in field_names):
                        full_match_count += 1
                        for field in field_names:
                            extractions[field].append(groups[field])

            if full_match_count == 0:
                # Pattern doesn't extract all fields from any example
                scored.append(PatternCandidate(
                    pattern=candidate.pattern,
                    flexibility=candidate.flexibility,
                    confidence=0.1,
                    description=candidate.description + " (matched 0 complete)"
                ))
                continue

            # Calculate quality scores
            match_ratio = full_match_count / len(test_examples)

            # Calculate uniqueness ratio for each field
            uniqueness_ratios = []
            for field in field_names:
                field_values = extractions[field]
                if field_values:
                    unique_ratio = len(set(field_values)) / len(field_values)
                    uniqueness_ratios.append(unique_ratio)

            avg_uniqueness = sum(uniqueness_ratios) / len(uniqueness_ratios) if uniqueness_ratios else 0

            # Combined score: weighted by match ratio and uniqueness
            score = candidate.confidence * (0.4 + 0.6 * match_ratio) * (0.7 + 0.3 * avg_uniqueness)

            scored.append(PatternCandidate(
                pattern=candidate.pattern,
                flexibility=candidate.flexibility,
                confidence=min(score, 1.0),
                description=f"{candidate.description} (matched {full_match_count}/{len(test_examples)} complete)"
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
