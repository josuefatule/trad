import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from app.environment import load_project_env
from app.translation import TranslationConfig


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.temp_root = Path(__file__).resolve().parents[1] / "logs" / "tests"
        self.temp_root.mkdir(parents=True, exist_ok=True)

    def test_quoted_key_and_translation_settings(self):
        with TemporaryDirectory(dir=self.temp_root) as directory, patch.dict(os.environ, {}, clear=True):
            path = Path(directory) / ".env"
            path.write_text('DEEPL_API_KEY="test-secret"\nTRANSLATION_ENABLED=1\n'
                            'TRANSLATION_PROVIDER=deepl\n', encoding="utf-8")
            load_project_env(path)
            config = TranslationConfig.from_env()
            self.assertEqual(config.deepl_auth_key, "test-secret")
            self.assertTrue(config.enabled)
            self.assertEqual(config.provider, "deepl")
            self.assertNotIn("test-secret", repr(config))

    def test_terminal_precedence_single_quotes_comments_and_legacy_key(self):
        with TemporaryDirectory(dir=self.temp_root) as directory, patch.dict(os.environ, {
                "TRANSLATION_ENABLED": "0"}, clear=True):
            path = Path(directory) / ".env"
            path.write_text("# comment\nTRANSLATION_ENABLED=1\n"
                            "DEEPL_AUTH_KEY='legacy-secret' # comment\n", encoding="utf-8-sig")
            load_project_env(path)
            config = TranslationConfig.from_env()
            self.assertFalse(config.enabled)
            self.assertEqual(config.deepl_auth_key, "legacy-secret")

    def test_missing_file_is_optional(self):
        with TemporaryDirectory(dir=self.temp_root) as directory:
            load_project_env(Path(directory) / ".env")
