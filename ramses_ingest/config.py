# -*- coding: utf-8 -*-
"""YAML rule loading and persistence for naming rules."""

from __future__ import annotations

import os
import logging
from pathlib import Path

from ramses_ingest.matcher import NamingRule

logger = logging.getLogger(__name__)

# Default rules file shipped with the tool
DEFAULT_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "default_rules.yaml"
)


def load_rules(path: str | Path | None = None) -> tuple[list[NamingRule], str, str]:
    """Parse a YAML rules file into ``NamingRule`` objects, a studio name, and a logo path.

    Returns:
        tuple: (list of NamingRule instances, studio_name string, studio_logo string).
    """
    if path is None:
        path = DEFAULT_RULES_PATH

    path = str(path)
    studio_name = "Ramses Studio"
    studio_logo = ""
    if not os.path.isfile(path):
        return [], studio_name, studio_logo

    import yaml

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        logger.warning(f"Config file '{path}' is not a valid YAML dictionary")
        return [], studio_name, studio_logo

    studio_name = data.get("studio_name", studio_name)
    studio_logo = data.get("studio_logo", "")
    rules: list[NamingRule] = []
    skipped_count = 0
    
    for idx, entry in enumerate(data.get("rules", []), start=1):
        if not isinstance(entry, dict):
            logger.warning(f"Rule {idx} in '{path}' is not a dictionary - skipping")
            skipped_count += 1
            continue
            
        if "pattern" not in entry:
            logger.warning(
                f"Rule {idx} in '{path}' missing required 'pattern' field - skipping. "
                f"Entry keys: {list(entry.keys())}"
            )
            skipped_count += 1
            continue
            
        rules.append(NamingRule(
            pattern=entry["pattern"],
            name=entry.get("name", ""),
            sequence_prefix=entry.get("sequence_prefix", ""),
            shot_prefix=entry.get("shot_prefix", ""),
            use_parent_dir_as_sequence=entry.get("use_parent_dir_as_sequence", False),
        ))
    
    if skipped_count > 0:
        logger.warning(f"Skipped {skipped_count} invalid rule(s) in '{path}'")

    return rules, studio_name, studio_logo


def save_rules(rules: list[NamingRule], path: str | Path, studio_name: str = "Ramses Studio", studio_logo: str = "") -> None:
    """Persist ``NamingRule`` objects and studio name back to a YAML file."""
    import yaml

    entries = []
    for rule in rules:
        entry: dict = {"pattern": rule.pattern}
        if rule.name:
            entry["name"] = rule.name
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
            "studio_logo": studio_logo,
            "rules": entries
        }, f, default_flow_style=False, sort_keys=False)
