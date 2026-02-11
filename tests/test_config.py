# -*- coding: utf-8 -*-
"""Tests for ramses_ingest.config."""

import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "lib"))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from ramses_ingest.config import load_rules, save_rules, DEFAULT_RULES_PATH
from ramses_ingest.matcher import NamingRule


class TestLoadRules(unittest.TestCase):
    def test_load_default_rules(self):
        rules, studio = load_rules()
        self.assertIsInstance(rules, list)
        self.assertGreaterEqual(len(rules), 2)
        self.assertIsInstance(rules[0], NamingRule)
        self.assertIsInstance(studio, str)

    def test_load_from_explicit_path(self):
        rules, studio = load_rules(DEFAULT_RULES_PATH)
        self.assertGreaterEqual(len(rules), 2)

    def test_load_missing_file_returns_empty(self):
        rules, studio = load_rules("/nonexistent/path.yaml")
        self.assertEqual(rules, [])
        self.assertEqual(studio, "Ramses Studio")

    def test_rule_fields_populated(self):
        rules, studio = load_rules()
        first = rules[0]
        self.assertTrue(len(first.pattern) > 0)

    def test_parent_dir_rule(self):
        rules, studio = load_rules()
        dir_rule = [r for r in rules if r.use_parent_dir_as_sequence]
        self.assertEqual(len(dir_rule), 1)


class TestSaveRules(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_round_trip(self):
        rules = [
            NamingRule(pattern=r"(?P<sequence>\w+)_(?P<shot>\w+)", sequence_prefix="SEQ"),
            NamingRule(pattern=r"(?P<shot>\w+)", use_parent_dir_as_sequence=True),
        ]
        path = os.path.join(self.tmpdir, "rules.yaml")
        save_rules(rules, path, studio_name="Custom Studio")

        loaded_rules, loaded_studio = load_rules(path)
        self.assertEqual(len(loaded_rules), 2)
        self.assertEqual(loaded_rules[0].sequence_prefix, "SEQ")
        self.assertTrue(loaded_rules[1].use_parent_dir_as_sequence)
        self.assertEqual(loaded_studio, "Custom Studio")

    def test_save_creates_directory(self):
        path = os.path.join(self.tmpdir, "sub", "rules.yaml")
        save_rules([NamingRule(pattern="test")], path)
        self.assertTrue(os.path.isfile(path))


if __name__ == "__main__":
    unittest.main()