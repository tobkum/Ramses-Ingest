# -*- coding: utf-8 -*-
"""YAML rule loading and persistence for naming rules."""

from __future__ import annotations

import os
from pathlib import Path

from ramses_ingest.matcher import NamingRule

# Default rules file shipped with the tool
DEFAULT_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "default_rules.yaml"
)


def load_rules(path: str | Path | None = None) -> tuple[list[NamingRule], str]:
    """Parse a YAML rules file into ``NamingRule`` objects and a studio name.

    Returns:
        tuple: (list of NamingRule instances, studio_name string).
    """
    if path is None:
        path = DEFAULT_RULES_PATH

    path = str(path)
    studio_name = "Ramses Studio"
    if not os.path.isfile(path):
        return [], studio_name

    import yaml

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        return [], studio_name

    studio_name = data.get("studio_name", studio_name)
    rules: list[NamingRule] = []
    for entry in data.get("rules", []):
        if not isinstance(entry, dict) or "pattern" not in entry:
            continue
        rules.append(NamingRule(
            pattern=entry["pattern"],
            sequence_prefix=entry.get("sequence_prefix", ""),
            shot_prefix=entry.get("shot_prefix", ""),
            use_parent_dir_as_sequence=entry.get("use_parent_dir_as_sequence", False),
        ))

    return rules, studio_name


def save_rules(rules: list[NamingRule], path: str | Path, studio_name: str = "Ramses Studio") -> None:
    """Persist ``NamingRule`` objects and studio name back to a YAML file."""
    import yaml

    entries = []
    for rule in rules:
        entry: dict = {"pattern": rule.pattern}
        if rule.sequence_prefix:
            entry["sequence_prefix"] = rule.sequence_prefix
        if rule.shot_prefix:
            entry["shot_prefix"] = rule.shot_prefix
        if rule.use_parent_dir_as_sequence:
            entry["use_parent_dir_as_sequence"] = True
        entries.append(entry)

    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as f:
        yaml.dump({
            "studio_name": studio_name,
            "rules": entries
        }, f, default_flow_style=False, sort_keys=False)
