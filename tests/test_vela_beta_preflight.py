"""Offline personal-beta preflight regression using synthetic local files only."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'deploy' / 'vela' / 'beta_preflight.py'
spec = importlib.util.spec_from_file_location('beta_preflight', SOURCE)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class BetaGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'vela'
        self.home.mkdir(mode=0o700)
        for name in ('db', 'cert', 'acme', 'secrets'):
            (self.home / name).mkdir(mode=0o700)
        self.default = (
            f'VELA_HOME={self.home}\n'
            'XUI_TG_MINIAPP_ADMIN_IDS=1001\n'
            'XUI_TG_MINIAPP_URL=https://admin.vela-safe-domain.org/app/\n'
            'XUI_PORT=2053\n'
        )
        self.put('.env', self.default)
        self.put('secrets/vela_bot_token', '12345:synthetic_only_fixture')
        self.put('image.ref', 'ghcr.io/smgsp6/3x-ui@sha256:' + 'a' * 64 + '\n')
        self.put('release.sequence', '0\n')
        self.put('compose.yml', 'services: {vela: {image: review-only}}\n', mode=0o644)
        self.template = Path(self.tmp.name) / 'reviewed.yml'
        self.template.write_bytes((self.home / 'compose.yml').read_bytes())

    def put(self, path, content, mode=0o600):
        f = self.home / path
        f.write_text(content)
        f.chmod(mode)

    def assert_refused(self, expected=None):
        with self.assertRaises(gate.PreflightFailure) as cm:
            gate.validate(self.home, self.template)
        if expected:
            self.assertIn(expected, str(cm.exception))

    def test_valid_isolated_layout(self):
        gate.validate(self.home, self.template)

    def test_runtime_example_style_does_not_require_duplicate_home(self):
        # The CLI already exports VELA_HOME for Compose. Copying the sample
        # env into an isolated synthetic directory must not require an extra
        # VELA_HOME line just to pass the read-only static preflight.
        sample = (SOURCE.parent / 'runtime.env.example').read_text(encoding='utf-8')
        self.assertNotIn('VELA_HOME=', sample)
        sample = sample.replace('https://vela.example.com/',
                                'https://admin.vela-safe-domain.org/app/')
        self.put('.env', sample)
        gate.validate(self.home, self.template)

    def test_documentation_placeholder_url_never_passes(self):
        sample = (SOURCE.parent / 'runtime.env.example').read_text(encoding='utf-8')
        self.put('.env', sample)
        self.assert_refused('placeholder')

    def test_optional_home_override_must_still_match(self):
        self.put('.env', self.default.replace(f'VELA_HOME={self.home}\\n', ''))
        gate.validate(self.home, self.template)
        self.put('.env', self.default.replace(str(self.home), '/opt/unreviewed'))
        self.assert_refused('VELA_HOME')

    def test_duplicate_admin_key_refused(self):
        self.put('.env', self.default + 'XUI_TG_MINIAPP_ADMIN_IDS=1002\n')
        self.assert_refused('duplicate')

    def test_duplicate_url_key_refused(self):
        self.put('.env', self.default + 'XUI_TG_MINIAPP_URL=https://evil.com/\n')
        self.assert_refused('duplicate')

    def test_invalid_allowlist_refused(self):
        for value in ('', '0', '1001,1001', '1001,x', str(2**63)):
            with self.subTest(value=value):
                self.put('.env', self.default.replace('=1001\n', '=' + value + '\n'))
                self.assert_refused('allowlist')

    def test_bad_urls_refused(self):
        for value in (
            'http://admin.vela-safe-domain.org/', 'https://example.com/',
            'https://localhost/', 'https://127.0.0.1/',
            'https://admin.vela-safe-domain.org/?token=x',
            'https://a:b@admin.vela-safe-domain.org/',
            'https://admin.vela-safe-domain.org:99999/',
            'https://vela.example.com/',
            'https://preview.example.net/',
            'https://panel.example.org/',
        ):
            with self.subTest(value=value):
                self.put('.env', self.default.replace(
                    'https://admin.vela-safe-domain.org/app/', value))
                self.assert_refused('Telegram')

    def test_token_symlink_and_excessive_permissions_refused(self):
        secret = self.home / 'secrets' / 'vela_bot_token'
        secret.chmod(0o644)
        self.assert_refused('bot secret')
        secret.chmod(0o600)
        other = Path(self.tmp.name) / 'target'
        other.write_text('123:fixture')
        secret.unlink()
        secret.symlink_to(other)
        self.assert_refused('bot secret')

    def test_token_parent_exposure_refused(self):
        (self.home / 'secrets').chmod(0o755)
        self.assert_refused('secrets directory')

    def test_image_digest_and_release_floor_refused(self):
        self.put('image.ref', 'ghcr.io/smgsp6/3x-ui:latest\n')
        self.assert_refused('SHA256')
        self.put('image.ref', 'ghcr.io/smgsp6/3x-ui@sha256:' + 'a' * 64 + '\n')
        self.put('release.sequence', 'nope\n')
        self.assert_refused('sequence')

    def test_compose_mutation_and_symlink_refused(self):
        self.put('compose.yml', 'services: {vela: {privileged: true}}\n', mode=0o644)
        self.assert_refused('compose')
        (self.home / 'compose.yml').unlink()
        (self.home / 'compose.yml').symlink_to(self.template)
        self.assert_refused('compose')

    def test_port_and_home_mismatch_refused(self):
        self.put('.env', self.default.replace('XUI_PORT=2053', 'XUI_PORT=70000'))
        self.assert_refused('port')
        self.put('.env', self.default.replace(str(self.home), '/opt/another-directory'))
        self.assert_refused('VELA_HOME')

    def test_registry_does_not_print_private_values(self):
        try:
            gate.validate(self.home, self.template)
        except gate.PreflightFailure as exc:
            self.assertNotIn('synthetic_only_fixture', str(exc))
            self.assertNotIn('1001', str(exc))


if __name__ == '__main__':
    unittest.main()
