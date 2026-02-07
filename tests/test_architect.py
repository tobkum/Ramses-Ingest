# -*- coding: utf-8 -*-
"""Tests for ramses_ingest.architect — Token engine and regex generation."""

import unittest
from ramses_ingest.architect import ArchitectToken, TokenEngine, TokenType

class TestArchitectToken(unittest.TestCase):
    def test_separator_to_regex(self):
        token = ArchitectToken(type=TokenType.SEPARATOR, value="_")
        self.assertEqual(token.to_regex(), "_")
        
        token = ArchitectToken(type=TokenType.SEPARATOR, value=".")
        self.assertEqual(token.to_regex(), r"\.")

    def test_shot_token(self):
        token = ArchitectToken(type=TokenType.SHOT)
        regex = token.to_regex()
        self.assertIn("?P<shot>", regex)
        self.assertIn("[A-Za-z0-9]+", regex)

    def test_version_token_with_prefix(self):
        token = ArchitectToken(type=TokenType.VERSION, prefix="v", padding=3)
        regex = token.to_regex()
        self.assertIn("v", regex)
        self.assertIn(r"\d{3}", regex)
        self.assertIn("?P<version>", regex)

    def test_wildcard_token(self):
        token = ArchitectToken(type=TokenType.WILDCARD)
        self.assertEqual(token.to_regex(), ".*?")

class TestTokenEngine(unittest.TestCase):
    def test_compile_full_rule(self):
        tokens = [
            ArchitectToken(type=TokenType.SEQUENCE),
            ArchitectToken(type=TokenType.SEPARATOR, value="_"),
            ArchitectToken(type=TokenType.SHOT),
            ArchitectToken(type=TokenType.SEPARATOR, value="_"),
            ArchitectToken(type=TokenType.VERSION, prefix="v", padding=3)
        ]
        pattern = TokenEngine.compile(tokens)
        
        # Should be anchored
        self.assertTrue(pattern.startswith("^"))
        self.assertTrue(pattern.endswith(".*$"))
        
        # Test against a real filename
        import re
        filename = "SEQ010_SH010_v001.exr"
        match = re.match(pattern, filename)
        self.assertTrue(match)
        self.assertEqual(match.group("sequence"), "SEQ010")
        self.assertEqual(match.group("shot"), "SH010")
        self.assertEqual(match.group("version"), "001")

    def test_simulate_success(self):
        tokens = [
            ArchitectToken(type=TokenType.SEQUENCE),
            ArchitectToken(type=TokenType.SEPARATOR, value="_"),
            ArchitectToken(type=TokenType.SHOT),
        ]
        res = TokenEngine.simulate(tokens, "SEQ01_SH02.exr")
        self.assertEqual(res.get("sequence"), "SEQ01")
        self.assertEqual(res.get("shot"), "SH02")

    def test_guess_tokens_standard(self):
        samples = [
            "SEQ010_SH010_v001.exr",
            "SEQ010_SH020_v001.exr",
            "SEQ010_SH030_v001.exr"
        ]
        tokens = TokenEngine.guess_tokens(samples)
        
        # Verify sequence of types
        types = [t.type for t in tokens]
        self.assertIn(TokenType.SEQUENCE, types)
        self.assertIn(TokenType.SHOT, types)
        self.assertIn(TokenType.SEPARATOR, types)
        
        # Check if it correctly identified '_' as separator
        separators = [t.value for t in tokens if t.type == TokenType.SEPARATOR]
        self.assertTrue(all(s == "_" for s in separators))

    def test_guess_tokens_dots(self):
        samples = [
            "PROJ.SEQ.SH01.v01.exr",
            "PROJ.SEQ.SH02.v01.exr"
        ]
        tokens = TokenEngine.guess_tokens(samples)
        separators = [t.value for t in tokens if t.type == TokenType.SEPARATOR]
        self.assertIn(".", separators)

    def test_guess_tokens_with_prefix(self):
        samples = [
            "SH010_v001.exr",
            "SH020_v001.exr"
        ]
        tokens = TokenEngine.guess_tokens(samples)
        version_token = next((t for t in tokens if t.type == TokenType.VERSION), None)
        self.assertIsNotNone(version_token)
        self.assertEqual(version_token.prefix, "v")

if __name__ == "__main__":
    unittest.main()
