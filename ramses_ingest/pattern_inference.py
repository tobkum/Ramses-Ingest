# -*- coding: utf-8 -*-
"""Smart pattern inference for naming rule generation.

This module provides intelligent regex pattern generation from user-annotated examples.
Instead of manually building regex patterns, users highlight parts of example filenames
and the system infers flexible patterns that work across similar naming conventions.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Union
from enum import Enum
from collections import defaultdict

# Tunable constant for pattern complexity penalty
COMPLEXITY_PENALTY_FACTOR = 0.005 

class Flexibility(Enum):
    """Pattern flexibility levels."""
    EXACT = "exact"
    SPECIFIC = "specific"
    FLEXIBLE = "flexible"
    VERY_FLEXIBLE = "very_flexible"


@dataclass
class PatternCandidate:
    """A candidate regex pattern with metadata."""
    pattern: str
    flexibility: Flexibility
    confidence: float
    description: str
    optional_fields: List[str] = field(default_factory=list)

    def __repr__(self):
        return f"PatternCandidate(pattern={self.pattern!r}, confidence={self.confidence:.2f}, optional={self.optional_fields})"


@dataclass
class Annotation:
    """User annotation of a field in an example."""
    example: str
    selected_text: str
    field_name: str
    start_pos: int
    end_pos: int


class PatternInferenceEngine:
    """Core engine for inferring regex patterns from user annotations."""
    DELIMITERS = r"_\-\.\s"

    def infer_combined_pattern(
        self,
        annotations: dict[str, Union[Annotation, list[Annotation]]],
        test_examples: Optional[List[str]] = None,
        negative_examples: Optional[List[str]] = None
    ) -> List[PatternCandidate]:
        """
        Infer a combined, intelligent regex pattern from multiple field annotations.
        """
        if not annotations:
            raise ValueError("At least one annotation is required")

        normalized_annotations: dict[str, list[Annotation]] = {}
        for field_name, ann in annotations.items():
            normalized_annotations[field_name] = ann if isinstance(ann, list) else [ann]

        first_anns = [anns[0] for anns in normalized_annotations.values()]
        example_refs = {a.example for a in first_anns}
        if len(example_refs) > 1:
            raise ValueError("All primary annotations must belong to the same example string.")

        real_annotations = {k: v for k, v in normalized_annotations.items() if not k.startswith('_ignore')}
        if not real_annotations:
            return [PatternCandidate(pattern=".*", flexibility=Flexibility.VERY_FLEXIBLE, confidence=0.1, description="Matches everything")]

        base_example = first_anns[0].example
        sorted_all_fields = sorted(normalized_annotations.items(), key=lambda x: x[1][0].start_pos)
        field_names = list(real_annotations.keys())
        
        candidates = []
        if len(real_annotations) == 1:
            field_name, field_anns = list(real_annotations.items())[0]
            candidates.extend(self._generate_candidates(field_anns))
        else:
            for flexibility in [Flexibility.FLEXIBLE, Flexibility.SPECIFIC]:
                strict_p, _ = self._build_strict_pattern(base_example, sorted_all_fields, flexibility)
                optional_fields = self._find_optional_fields(strict_p, normalized_annotations, test_examples or [], negative_examples or [])
                final_p, _ = self._build_strict_pattern(base_example, sorted_all_fields, flexibility, optional_fields)
                
                candidates.append(PatternCandidate(
                    pattern=final_p, flexibility=flexibility, confidence=0.9 if flexibility == Flexibility.FLEXIBLE else 0.8,
                    description=f"Combined ({flexibility.value})", optional_fields=optional_fields
                ))
        
        scored = self._score_combined_candidates(candidates, test_examples or [], negative_examples or [], field_names)
        scored.sort(key=lambda c: (c.confidence, -len(c.pattern)), reverse=True)
        
        unique = []
        seen = set()
        for c in scored:
            if c.pattern not in seen:
                unique.append(c); seen.add(c.pattern)
        return unique

    def infer_pattern(self, annotations: List[Annotation], test_examples: Optional[List[str]] = None) -> List[PatternCandidate]:
        ann_dict = defaultdict(list)
        for a in annotations: ann_dict[a.field_name].append(a)
        return self.infer_combined_pattern(ann_dict, test_examples=test_examples)

    def _generate_candidates(self, annotations: list[Annotation]) -> List[PatternCandidate]:
        candidates = []
        if not annotations: return candidates
        field_name = annotations[0].field_name
        selections = [a.selected_text for a in annotations]
        char_p = self._analyze_character_pattern(selections)
        first_ann = annotations[0]
        
        left_anchor = self._get_left_boundary(first_ann.example, first_ann.start_pos)
        right_anchor = self._get_right_boundary(first_ann.example, first_ann.end_pos)
        vfx_lookahead = f"(?=[{self.DELIMITERS}\\.]|$)"
        
        scenarios = [
            (left_anchor, right_anchor, 0.0), (left_anchor, vfx_lookahead, -0.05),
            ("", right_anchor, -0.1), (left_anchor, "", -0.1), ("", vfx_lookahead, -0.15), ("", "", -0.2)
        ]

        for lb, rb, adj in scenarios:
            prefix = "^" if lb == "^" else (".*?" if lb == "" else f".*?{lb}")
            for p_type in ['specific', 'flexible']:
                if char_p.get(p_type):
                    patterns_to_try = [char_p[p_type]]
                    # Use non-greedy flexible ONLY if it is a digit run or known concatenated unit
                    if p_type == 'flexible' and rb and any(c.isdigit() for c in selections[0]):
                        patterns_to_try.append(char_p[p_type] + "?")
                    
                    for p in patterns_to_try:
                        pat = f"{prefix}(?P<{field_name}>{p}){rb}"
                        try:
                            m = re.search(pat, first_ann.example)
                            if m and m.group(field_name) == first_ann.selected_text:
                                candidates.append(PatternCandidate(
                                    pattern=pat, flexibility=Flexibility(p_type), confidence=0.95 + adj if p_type == 'specific' else 0.85 + adj,
                                    description=p_type.capitalize()
                                ))
                        except re.error: continue
        return candidates

    def _build_strict_pattern(self, base_example, sorted_annotations, flexibility, optional_fields=None):
        optional_fields = optional_fields or []
        field_patterns = {}
        for name, anns in sorted_annotations:
            char_p = self._analyze_character_pattern([a.selected_text for a in anns])
            # For combined, always prefer Specific run analysis if it matches all annotated examples
            field_patterns[name] = char_p['specific'] if char_p.get('specific') else char_p.get('flexible')
        
        anns_structure = [anns[0] for _, anns in sorted_annotations]
        fragments = self._extract_context_between(base_example, anns_structure)
        parts = ["^" if not fragments['prefix'] else re.escape(fragments['prefix'])]
        for i, (name, _) in enumerate(sorted_annotations):
            sep = fragments['separators'][i-1] if i > 0 else ""
            sep_p = self._separator_to_pattern(sep, flexibility)
            if name in optional_fields: parts.append(f"(?:{sep_p}")
            elif sep_p: parts.append(sep_p)
            p = field_patterns[name]
            # Avoid greedy swallowing in concatenated fields
            if p.endswith("+") and not sep and (not (i == len(sorted_annotations)-1) or fragments['suffix']):
                p += "?"
            if name.startswith('_ignore'): parts.append(f"({p})")
            else: parts.append(f"(?P<{name}>{p})")
            if name in optional_fields: parts.append(")?")
        
        if fragments['suffix']:
            # Middle ground flexibility for suffix
            parts.append(f".*?{re.escape(fragments['suffix'][-4:])}$")
        else: parts.append(".*$")
        return "".join(parts), field_patterns

    def _find_optional_fields(self, strict_p, all_anns, test_ex, neg_ex):
        opts = []
        real_names = [k for k in all_anns.keys() if not k.startswith('_ignore')]
        base_s = self._test_pattern_performance(strict_p, real_names, test_ex, neg_ex)
        sorted_anns = sorted(all_anns.items(), key=lambda x: x[1][0].start_pos)
        base_ex = list(all_anns.values())[0][0].example
        for name in real_names:
            tmp_p, _ = self._build_strict_pattern(base_ex, sorted_anns, Flexibility.FLEXIBLE, [name])
            if self._test_pattern_performance(tmp_p, real_names, test_ex, neg_ex) > base_s: opts.append(name)
        return opts

    def _test_pattern_performance(self, p, fields, examples, neg_ex):
        if not examples: return 0.0
        try: compiled = re.compile(p)
        except re.error: return 0.0
        for ne in neg_ex:
            if compiled.search(ne): return 0.0
        match_count = 0
        extractions = defaultdict(list)
        for ex in examples:
            m = compiled.search(ex)
            if m:
                match_count += 1
                for f in fields:
                    if f in m.groupdict() and m.group(f) is not None: extractions[f].append(m.group(f))
        total_extracted = sum(len(v) for v in extractions.values())
        uniqueness = sum(len(set(v)) for v in extractions.values()) / total_extracted if total_extracted > 0 else 1.0
        return (match_count / len(examples) * 0.9) + (uniqueness * 0.1)

    def _separator_to_pattern(self, sep, flexibility):
        if not sep: return ""
        if all(c in self.DELIMITERS for c in sep): return f"[{self.DELIMITERS}]+"
        return r".*?" if flexibility == Flexibility.FLEXIBLE else re.escape(sep)

    def _extract_context_between(self, ex, anns):
        ctx = {'prefix': ex[:anns[0].start_pos], 'separators': [], 'suffix': ex[anns[-1].end_pos:]}
        for i in range(len(anns) - 1): ctx['separators'].append(ex[anns[i].end_pos:anns[i+1].start_pos])
        return ctx

    def _score_combined_candidates(self, candidates, test_ex, neg_ex, fields):
        if not test_ex: return candidates
        for c in candidates:
            score = self._test_pattern_performance(c.pattern, fields, test_ex, neg_ex)
            penalty = 1 + (len(c.pattern) * COMPLEXITY_PENALTY_FACTOR)
            c.confidence = min((c.confidence * 0.4 + score * 0.6) / penalty, 1.0)
            c.description += f" (Coverage: {score*100:.0f}%)"
        return candidates

    def _analyze_character_pattern(self, selections: Union[str, List[str]]) -> dict:
        if not selections: return {}
        if isinstance(selections, str): selections = [selections]
        lengths = [len(s) for s in selections]; min_l, max_l = min(lengths), max(lengths)
        all_text = "".join(selections)
        has_upper, has_lower, has_digit = bool(re.search(r'[A-Z]', all_text)), bool(re.search(r'[a-z]', all_text)), bool(re.search(r'\d', all_text))
        patterns = {}
        template = selections[0]
        # SPECIFIC
        if template.lower().startswith('v') and template[1:].isdigit():
            patterns['specific'] = f"{template[0]}\\d{{{min_l-1},{max_l-1}}}" if min_l != max_l else f"{template[0]}\\d{{{min_l-1}}}"
        elif has_digit and not has_upper and not has_lower and len(re.findall(r'\d', all_text)) == len(all_text):
            patterns['specific'] = f"\\d{{{min_l},{max_l}}}" if min_l != max_l else f"\\d{{{min_l}}}"
        elif has_upper and not has_lower and not has_digit and len(re.findall(r'[A-Z]', all_text)) == len(all_text):
            patterns['specific'] = f"[A-Z]{{{min_l},{max_l}}}" if min_l != max_l else f"[A-Z]{{{min_l}}}"
        else:
            parts = []; i = 0
            while i < len(template):
                char = template[i]
                if char.isupper():
                    run = re.match(r"^[A-Z]+", template[i:]).group(0); i += len(run)
                    parts.append(f"[A-Z]{{{len(run)}}}" if len(selections) == 1 else f"[A-Z]+")
                elif char.islower():
                    run = re.match(r"^[a-z]+", template[i:]).group(0); i += len(run)
                    parts.append(f"[a-z]{{{len(run)}}}" if len(selections) == 1 else f"[a-z]+")
                elif char.isdigit():
                    run = re.match(r"^\d+", template[i:]).group(0); i += len(run)
                    parts.append(f"\\d{{{len(run)}}}" if len(selections) == 1 else f"\\d+")
                else: parts.append(re.escape(char)); i += 1
            patterns['specific'] = "".join(parts)
        # FLEXIBLE
        char_sets = []
        if has_upper: char_sets.append('A-Z')
        if has_lower: char_sets.append('a-z')
        if has_digit: char_sets.append('0-9')
        for char in all_text:
            if char in self.DELIMITERS and re.escape(char) not in char_sets: char_sets.append(re.escape(char))
        patterns['flexible'] = f"[{''.join(char_sets)}]+" if char_sets else f"[^{self.DELIMITERS}\\.]+"
        return patterns

    def _get_left_boundary(self, text: str, pos: int) -> str:
        if pos == 0: return "^"
        char = text[pos-1]
        return re.escape(char) if (char in self.DELIMITERS or not char.isalnum()) else ""

    def _get_right_boundary(self, text: str, pos: int) -> str:
        if pos >= len(text): return "$"
        char = text[pos]
        return re.escape(char) if (char in self.DELIMITERS or not char.isalnum()) else ""


def test_pattern(pattern: str, examples: list[str], field_name: str) -> list[str | None]:
    results = []
    try:
        compiled = re.compile(pattern)
        for ex in examples:
            m = compiled.search(ex)
            results.append(m.group(field_name) if m and field_name in m.groupdict() else None)
    except re.error: return [None] * len(examples)
    return results
