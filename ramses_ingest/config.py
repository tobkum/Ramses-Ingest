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


def load_rules(path: str | Path | None = None) -> list[NamingRule]:
    """Parse a YAML rules file into ``NamingRule`` objects.

    Args:
        path: Path to a YAML file. Defaults to ``config/default_rules.yaml``.

    Returns:
        List of ``NamingRule`` instances (may be empty on error).
    """
    if path is None:
        path = DEFAULT_RULES_PATH

    path = str(path)
    if not os.path.isfile(path):
        return []

    import yaml

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        return []

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

    return rules


def save_rules(rules: list[NamingRule], path: str | Path) -> None:
    """Persist ``NamingRule`` objects back to a YAML file."""
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
        yaml.dump({"rules": entries}, f, default_flow_style=False, sort_keys=False)
