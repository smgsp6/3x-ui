"""Ensure the actual on-disk Vela patch includes the Phase 12 safety gates.

This test verifies the files that the patch applier copies, not only fixtures.
"""
from pathlib import Path
import tempfile
import unittest
import test_apply_to_repo as fixtures

ROOT = Path(__file__).resolve().parents[1]

class Phase12SafetyContracts(unittest.TestCase):
    def test_go_secret_reader_is_permission_checked(self):
        source = (ROOT / 'internal/web/service/tgminiapp/auth.go').read_text()
        self.assertIn('os.SameFile(info, opened)', source)
        self.assertIn('opened.Mode().Perm()&0077 != 0', source)
        self.assertIn('parent.Mode().Perm()&0022 != 0', source)
        self.assertIn('strings.ContainsAny(token,', source)
        test_code = (ROOT / 'internal/web/service/tgminiapp/auth_test.go').read_text()
        self.assertIn('TestBotTokenRejectsLoosePermissions', test_code)
        self.assertIn('TestBotTokenRejectsWritableSecretDirectory', test_code)

    def test_tls_renewal_keeps_original_identity(self):
        source = (ROOT / 'internal/web/service/tgminiapp/tls_reloader.go').read_text()
        self.assertIn('keepsCertificateIdentity(oldLeaf, newLeaf)', source)
        self.assertIn('slices.Contains(candidate.DNSNames, name)', source)
        self.assertIn('oldIP.Equal(newIP)', source)
        test_code = (ROOT / 'internal/web/service/tgminiapp/tls_reloader_test.go').read_text()
        self.assertIn('TestTLSReloadRejectsUnrelatedDomain', test_code)

    def test_applied_patch_copies_hardened_source_verbatim(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = fixtures.PatchTests()
            repo = helper.make_repo(Path(directory))
            helper.execute(repo)
            for name in ('auth.go','auth_test.go','tls_reloader.go','tls_reloader_test.go'):
                relative = Path('internal/web/service/tgminiapp')/name
                self.assertEqual((repo/relative).read_bytes(), (ROOT/relative).read_bytes(), str(relative))
            self.assertTrue((repo/'docs/PHASE12-CHANGELOG.md').is_file())
            self.assertTrue((repo/'docs/PHASE12-TEST-REPORT.md').is_file())
            self.assertTrue((repo/'tests/test_phase12_security_contract.py').is_file())

if __name__ == '__main__':
    unittest.main()
