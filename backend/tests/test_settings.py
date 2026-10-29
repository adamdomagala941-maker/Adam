import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest.mock import patch

from backend.settings import SettingsError, load_settings, public_settings, save_settings


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / '.local' / 'settings.json'
        self.path_patch = patch('backend.settings.SETTINGS_PATH', self.path)
        self.env_patch = patch.dict(os.environ, {'DJCHEM_OPENAI_API_KEY': ''})
        self.path_patch.start()
        self.env_patch.start()
        self.addCleanup(self.directory.cleanup)
        self.addCleanup(self.path_patch.stop)
        self.addCleanup(self.env_patch.stop)

    def test_default_is_disabled_without_file(self):
        self.assertEqual(load_settings(), {'ai_enabled': False, 'openai_api_key': ''})
        self.assertEqual(public_settings(), {'ai_enabled': False, 'key_configured': False, 'key_source': ''})
        self.assertFalse(self.path.exists())

    def test_save_and_load_key_without_public_disclosure(self):
        result = save_settings(True, 'sk-test-file-key')
        self.assertEqual(result, {'ai_enabled': True, 'key_configured': True, 'key_source': 'file'})
        self.assertEqual(load_settings(), {'ai_enabled': True, 'openai_api_key': 'sk-test-file-key'})
        self.assertNotIn('sk-test-file-key', json.dumps(public_settings()))

    @unittest.skipUnless(os.name == 'posix', 'POSIX file permissions')
    def test_private_file_and_directory_permissions(self):
        save_settings(False, 'sk-test-file-key')
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)

    def test_key_presence_does_not_opt_in(self):
        save_settings(False, 'sk-test-file-key')
        self.assertFalse(load_settings()['ai_enabled'])

    def test_omitting_key_or_empty_input_preserves_it(self):
        save_settings(True, 'sk-test-file-key')
        save_settings(False)
        self.assertEqual(load_settings()['openai_api_key'], 'sk-test-file-key')
        save_settings(True, '')
        self.assertEqual(load_settings()['openai_api_key'], 'sk-test-file-key')

    def test_explicit_clear_removes_file_key(self):
        save_settings(True, 'sk-test-file-key')
        self.assertEqual(save_settings(False, clear_key=True), {'ai_enabled': False, 'key_configured': False, 'key_source': ''})
        self.assertEqual(load_settings()['openai_api_key'], '')

    def test_enabling_without_key_rejected_before_write(self):
        with self.assertRaisesRegex(SettingsError, 'dodaj klucz'):
            save_settings(True)
        self.assertFalse(self.path.exists())

    def test_clear_and_enable_rejected_preserving_existing_file(self):
        save_settings(True, 'sk-test-file-key')
        original = self.path.read_bytes()
        with self.assertRaisesRegex(SettingsError, 'dodaj klucz'):
            save_settings(True, clear_key=True)
        self.assertEqual(self.path.read_bytes(), original)

    def test_environment_overrides_file_without_being_saved(self):
        save_settings(False, 'sk-test-file-key')
        with patch.dict(os.environ, {'DJCHEM_OPENAI_API_KEY': 'sk-test-environment-key'}):
            result = save_settings(True)
            self.assertEqual(load_settings()['openai_api_key'], 'sk-test-environment-key')
            self.assertEqual(result['key_source'], 'environment')
            self.assertNotIn('sk-test-environment-key', self.path.read_text())
            self.assertNotIn('sk-test-environment-key', json.dumps(result))

    def test_environment_key_alone_still_disabled(self):
        with patch.dict(os.environ, {'DJCHEM_OPENAI_API_KEY': 'sk-test-environment-key'}):
            self.assertEqual(public_settings(), {'ai_enabled': False, 'key_configured': True, 'key_source': 'environment'})

    def test_cannot_clear_environment_key(self):
        save_settings(False, 'sk-test-file-key')
        original = self.path.read_bytes()
        with patch.dict(os.environ, {'DJCHEM_OPENAI_API_KEY': 'sk-test-environment-key'}), self.assertRaisesRegex(SettingsError, 'zmiennej DJCHEM_OPENAI_API_KEY'):
            save_settings(False, clear_key=True)
        self.assertEqual(self.path.read_bytes(), original)

    def test_failed_atomic_replace_preserves_original_and_cleans_temp(self):
        save_settings(False, 'sk-test-file-key')
        original = self.path.read_bytes()
        with patch('backend.settings.os.replace', side_effect=OSError('disk failure')), self.assertRaisesRegex(SettingsError, 'poprzedni plik'):
            save_settings(True, 'sk-new-file-key')
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ['settings.json'])

    def test_invalid_keys_never_written_or_echoed(self):
        for value in ['abc', 'sk-key withspace', 'sk-key\nnewline', 'k'*513]:
            with self.subTest(value_length=len(value)), self.assertRaises(SettingsError) as caught:
                save_settings(True, value)
            self.assertNotIn(value, str(caught.exception))
        self.assertFalse(self.path.exists())

    def test_corrupt_file_not_overwritten(self):
        self.path.parent.mkdir()
        self.path.write_text('broken JSON with secret')
        with self.assertRaisesRegex(SettingsError, 'nie nadpisze'):
            save_settings(False, 'sk-new-file-key')
        self.assertEqual(self.path.read_text(), 'broken JSON with secret')

    def test_invalid_types_and_ambiguous_clear_rejected(self):
        for args in [('false', None, False), (False, 123, False), (False, 'sk-file-key', True)]:
            with self.subTest(args=args), self.assertRaises(SettingsError):
                save_settings(*args)
        self.assertFalse(self.path.exists())

    def test_other_saved_fields_are_preserved(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps({'ai_enabled': False, 'openai_api_key': '', 'future_setting': 'keep'}))
        save_settings(False)
        self.assertEqual(json.loads(self.path.read_text())['future_setting'], 'keep')


if __name__ == '__main__':
    unittest.main()
