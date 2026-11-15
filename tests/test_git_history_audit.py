"""Offline history-audit tests; synthetic tokens never leave the test directory."""
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'deploy/vela'))
spec = importlib.util.spec_from_file_location('history_audit', ROOT/'deploy/vela/git_history_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class GitHistoryAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git('init', '-q')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'user.name', 'Vela audit fixture')
        (self.repo/'readme.txt').write_text('public document')
        self.git('add', '.')
        self.git('commit', '-qm', 'initial')

    def git(self, *args):
        subprocess.run(['git', *args], cwd=self.repo, check=True, capture_output=True)

    def test_clean_history_passes(self):
        findings, count = audit.audit_history(self.repo)
        self.assertEqual(findings, [])
        self.assertGreater(count, 0)

    def test_secret_removed_from_head_is_still_detected(self):
        secret = '123456789:' + 'A'*35
        (self.repo/'readme.txt').write_text('embedded test credential: ' + secret)
        self.git('add', '.')
        self.git('commit', '-qm', 'accidentally committed token')
        (self.repo/'readme.txt').write_text('public document')
        self.git('add', '.')
        self.git('commit', '-qm', 'removed from latest HEAD')
        findings, _ = audit.audit_history(self.repo)
        self.assertTrue(any('Telegram bot token' in item for item in findings))
        self.assertNotIn(secret, '\n'.join(findings))

    def test_historical_sensitive_filename_detected(self):
        (self.repo/'prod-private.key').write_text('placeholder only')
        self.git('add', '.')
        self.git('commit', '-qm', 'historical private file')
        (self.repo/'prod-private.key').unlink()
        self.git('add', '-u')
        self.git('commit', '-qm', 'delete private file')
        findings, _ = audit.audit_history(self.repo)
        self.assertTrue(any('historical sensitive filename' in item for item in findings))


if __name__ == '__main__':
    unittest.main()
