# -*- coding: utf-8 -*-
"""YAML rule loading and persistence for naming rules."""

from __future__ import annotations

import os
import sys
import logging
from pathlib import Path

from ramses_ingest.matcher import NamingRule

logger = logging.getLogger(__name__)

# Default rules file shipped with the tool (read-only; never written by the app)
DEFAULT_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "config", "default_rules.yaml"
)

# User-specific rules file — survives package upgrades and lives outside the
# package directory so it cannot be clobbered by a pip install.
if sys.platform == "win32":
    _cfg_base = Path(os.getenv("APPDATA", str(Path.home())))
else:
    _cfg_base = Path.home() / ".config"
USER_RULES_PATH = str(_cfg_base / "ramses_ingest" / "rules.yaml")


def load_rules(path: str | Path | None = None) -> tuple[list[NamingRule], str, str]:
    """Parse a YAML rules file into ``NamingRule`` objects, a studio name, and a logo path.

    When *path* is ``None`` the user config (``USER_RULES_PATH``) is preferred
    over the shipped defaults so that customisations survive package upgrades.

    Returns:
        tuple: (list of NamingRule instances, studio_name string, studio_logo string).
    """
    if path is None:
        path = USER_RULES_PATH if os.path.isfile(USER_RULES_PATH) else DEFAULT_RULES_PATH

    path = str(path)
    studio_name = "Ramses Studio"
    studio_logo = ""
    if not os.path.isfile(path):
        return [], studio_name, studio_logo

    import yaml

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as exc:
        # A corrupt or unreadable USER config must never brick startup — the
        # engine loads rules in its constructor. Fall back to the shipped
        # defaults so the tool still launches with working built-in rules.
        logger.warning("Could not parse rules file '%s': %s", path, exc)
        if (os.path.abspath(path) != os.path.abspath(DEFAULT_RULES_PATH)
                and os.path.isfile(DEFAULT_RULES_PATH)):
            logger.warning("Falling back to default rules at '%s'.", DEFAULT_RULES_PATH)
            return load_rules(DEFAULT_RULES_PATH)
        return [], studio_name, studio_logo

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


def save_rules(rules: list[NamingRule], path: str | Path | None = None, studio_name: str = "Ramses Studio", studio_logo: str = "") -> None:
    """Persist ``NamingRule`` objects and studio name back to a YAML file.

    When *path* is ``None`` the rules are written to ``USER_RULES_PATH`` so
    that the shipped ``default_rules.yaml`` is never modified.
    """
    if path is None:
        path = USER_RULES_PATH
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

    target = str(path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    payload = yaml.dump({
        "studio_name": studio_name,
        "studio_logo": studio_logo,
        "rules": entries
    }, default_flow_style=False, sort_keys=False)

    # Atomic write: a killed/interrupted write must not truncate rules.yaml
    # into invalid YAML (which load_rules now survives, but should never see).
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(target) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(tmp, target)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
