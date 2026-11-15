"""Offline privacy checks; no real credentials or network access."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vela_privacy', ROOT / 'deploy/vela/privacy_audit.py')
privacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)


class PrivacyAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True)
        (self.repo / '.dockerignore').write_text('\n'.join(sorted(privacy.REQUIRED_DOCKER_IGNORES)) + '\n')
        (self.repo / 'Dockerfile').write_text('FROM scratch\nCOPY . .\n')
        (self.repo / 'src').mkdir()
        (self.repo / 'src' / 'main.go').write_text('package main\n')

    def stage(self):
        subprocess.run(['git', 'add', '.'], cwd=self.repo, check=True)

    def test_clean_source_passes(self):
        self.stage()
        self.assertEqual(privacy.audit(self.repo), [])

    def test_git_tracked_token_blocked_and_redacted(self):
        fake_token = '123456789:' + 'X' * 35
        (self.repo / 'src' / 'config.go').write_text('token = "' + fake_token + '"')
        self.stage()
        findings = privacy.audit(self.repo)
        self.assertTrue(any('Telegram bot token' in label for _, label in findings), findings)
        self.assertNotIn(fake_token, repr(findings))

    def test_tracked_private_file_blocked(self):
        (self.repo / 'secrets').mkdir()
        (self.repo / 'secrets' / 'mytoken').write_text('not a real token')
        self.stage()
        self.assertTrue(any('sensitive filename' in label for _, label in privacy.audit(self.repo)))

    def test_dockerignore_without_secret_rules_blocked(self):
        (self.repo / '.dockerignore').write_text('.git\nnode_modules\n')
        self.stage()
        self.assertTrue(any('.dockerignore' == path for path, _ in privacy.audit(self.repo)))

    def test_untracked_secret_in_source_blocked(self):
        self.stage()
        (self.repo / 'src' / 'private.key').write_text('placeholder')
        self.assertTrue(any('private.key' in path for path, _ in privacy.audit(self.repo)))

    def test_known_ignored_local_secret_folder_does_not_fail(self):
        self.stage()
        (self.repo / 'secrets').mkdir()
        (self.repo / 'secrets' / 'vela_bot_token').write_text('local only')
        self.assertEqual(privacy.audit(self.repo), [])

    def test_untracked_private_key_header_blocked(self):
        self.stage()
        (self.repo / 'src' / 'harmless.txt').write_text('-----BEGIN ' + 'PRIVATE KEY-----\ntest-only\n')
        self.assertTrue(any('private key' in label for _, label in privacy.audit(self.repo)))

    def test_generic_dockerignore_reinclude_is_blocked(self):
        with (self.repo / '.dockerignore').open('a') as f:
            f.write('!*\n')
        self.stage()
        findings = privacy.audit(self.repo)
        self.assertTrue(any('re-include' in label for _, label in findings))

    def test_dockerignore_risky_reinclude_blocked(self):
        with (self.repo / '.dockerignore').open('a') as f:
            f.write('!secrets/\n')
        self.stage()
        self.assertTrue(any('re-include' in label for _, label in privacy.audit(self.repo)))


if __name__ == '__main__':
    unittest.main()
