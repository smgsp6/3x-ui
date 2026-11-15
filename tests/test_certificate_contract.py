"""Offline contract checks against the actual phase-10 source bundle.

These are narrow static integration guards. They don't replace Go/React builds.
"""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CertificateIntegrationTests(unittest.TestCase):
    def test_status_envelope_retains_opt_in_alert_flag(self):
        handler = (ROOT / "internal/web/controller/miniapp.go").read_text()
        ui = (ROOT / "frontend/src/pages/certificates/CertificatesPage.tsx").read_text()
        self.assertIn('"obj": gin.H{', handler)
        self.assertIn('"alertsEnabled": tgminiapp.CertAlertsEnabled()', handler)
        self.assertIn('"certificates": []tgminiapp.CertificateStatus{', handler)
        self.assertIn('response.obj.certificates', ui)
        self.assertIn('response.obj.alertsEnabled', ui)
        self.assertNotIn('response.alertsEnabled', ui)
        self.assertNotIn('"alertsEnabled": tgminiapp.CertAlertsEnabled(), "obj": []', handler)

    def test_tls_reload_only_when_vela_enabled(self):
        patch = (ROOT / "apply_to_repo.py").read_text()
        self.assertIn('if tgminiapp.Enabled()', patch)
        self.assertIn('tgminiapp.NewTLSCertificateReloader(certFile, keyFile, cert)', patch)
        self.assertIn('c.GetCertificate = reloader.GetCertificate', patch)
        self.assertIn('c.Certificates = nil', patch)
        self.assertIn('"internal/web/service/tgminiapp/tls_reloader.go"', patch)
        self.assertIn('"internal/web/service/tgminiapp/tls_reloader_test.go"', patch)

    def test_no_key_paths_in_certificate_status_json(self):
        source = (ROOT / 'internal/web/service/tgminiapp/certificates.go').read_text()
        model = source[source.index('type CertificateStatus struct {'):source.index('\n}', source.index('type CertificateStatus struct {'))]
        for private_field in ('certPath', 'keyPath', 'privateKey', 'fileName', 'token'):
            self.assertNotIn(private_field, model)


if __name__ == '__main__':
    unittest.main()
