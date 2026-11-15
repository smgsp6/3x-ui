"""Offline integration tests of Vela lifecycle commands with fake Docker/curl.

These tests never call a Docker daemon, contact the network, or use a real VPS.
"""
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'deploy' / 'vela' / 'vela'
OLD = 'ghcr.io/smgsp6/3x-ui@sha256:' + 'a' * 64
NEW = 'ghcr.io/smgsp6/3x-ui@sha256:' + 'b' * 64


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'vela'
        self.root.mkdir()
        self.fakebin = Path(self.temp.name) / 'bin'
        self.fakebin.mkdir()
        for item in ('db', 'cert', 'acme', 'secrets'):
            (self.root / item).mkdir()
        (self.root / 'db' / 'x-ui.db').write_text('original-db')
        (self.root / 'cert' / 'panel.pem').write_text('cert bytes')
        (self.root / 'acme' / 'state').write_text('acme bytes')
        (self.root / 'secrets' / 'vela_bot_token').write_text('placeholder-token')
        (self.root / '.env').write_text('XUI_TG_MINIAPP_ADMIN_IDS=1001\nXUI_TG_MINIAPP_URL=https://vela.example.com/\n')
        (self.root / 'compose.yml').write_text('services: {vela: {image: "${VELA_IMAGE}"}}')
        (self.root / 'image.ref').write_text(OLD + '\n')
        (self.root / 'release.sequence').write_text('0\n')
        # Test-only Ed25519 key is generated inside a disposable temp dir.
        # Production CLI has a deliberately unconfigured release-key pin.
        self.signing_private = Path(self.temp.name) / 'test-signing-private.pem'
        self.signing_public = self.root / 'release-public.pem'
        subprocess.run(['openssl', 'genpkey', '-algorithm', 'Ed25519', '-out', str(self.signing_private)],
                       check=True, capture_output=True)
        subprocess.run(['openssl', 'pkey', '-in', str(self.signing_private), '-pubout',
                        '-out', str(self.signing_public)], check=True, capture_output=True)
        import hashlib
        fingerprint = hashlib.sha256(self.signing_public.read_bytes()).hexdigest()
        self.tool = Path(self.temp.name) / 'vela-under-test'
        self.tool.write_text(TOOL.read_text().replace(
            'UNCONFIGURED-RELEASE-SIGNING-KEY', fingerprint))

        (self.root / '.env').chmod(0o600)
        (self.root / 'secrets' / 'vela_bot_token').chmod(0o600)
        (self.fakebin / 'docker').write_text('''#!/usr/bin/env python3
import os, sys
from pathlib import Path
args = sys.argv[1:]
state = Path(os.environ['VELA_TEST_STATE'])
log = Path(os.environ['VELA_TEST_LOG'])
with log.open('a') as f: f.write('docker ' + ' '.join(args) + ' image=' + os.getenv('VELA_IMAGE','') + '\\n')
if args[:2] == ['compose','version']: sys.exit(0)
if args == ['info']: sys.exit(0)
if args[0] == 'inspect': print('true'); sys.exit(0)
if args[0] == 'exec':
    if os.environ.get('VELA_TEST_FAIL_HEALTH')=='1' and state.read_text().strip().endswith('b'*64): sys.exit(1)
    sys.exit(0)
if args[0] == 'compose':
    if 'pull' in args:
        if os.environ.get('VELA_TEST_FAIL_PULL') == '1': sys.exit(1)
        sys.exit(0)
    if 'up' in args:
        image = os.environ['VELA_IMAGE']
        state.write_text(image)
        if image.endswith('b'*64):
            Path(os.environ['VELA_HOME'],'db','x-ui.db').write_text('migrated-db')
        sys.exit(0)
    if 'start' in args and os.environ.get('VELA_TEST_WRITES_ON_RESTART') == '1':
        Path(os.environ['VELA_HOME'],'db','x-ui.db').write_text('late-write-after-backup')
    if 'stop' in args or 'start' in args or 'config' in args or 'ps' in args or 'logs' in args: sys.exit(0)
sys.exit(2)
''')
        (self.fakebin / 'curl').write_text('''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
if os.environ.get('VELA_TEST_FAIL_DOWNLOAD') == '1': sys.exit(22)
dest = args[args.index('-o')+1]
url = args[-1]
if url.endswith('.sig'):
    if os.environ.get('VELA_TEST_UNSIGNED') == '1': sys.exit(22)
    if os.environ.get('VELA_TEST_BAD_SIGNATURE') == '1':
        Path(dest).write_bytes(b'invalid-signature')
    else:
        subprocess.run(['openssl','pkeyutl','-sign','-rawin',
                        '-inkey',os.environ['VELA_TEST_SIGNING_PRIVATE'],
                        '-in',os.environ['VELA_TEST_MANIFEST_FILE'],
                        '-out',dest],check=True,capture_output=True)
else:
    channel = 'hacked' if os.environ.get('VELA_TEST_BAD_MANIFEST') == '1' else 'stable'
    Path(dest).write_text(json.dumps({'repository':'smgsp6/3x-ui','channel':channel,
             'image':'ghcr.io/smgsp6/3x-ui@sha256:' + 'b'*64,
             'releaseSequence': (True if os.environ.get('VELA_TEST_BOOL_SEQUENCE')=='1'
                    else int(os.environ.get('VELA_TEST_RELEASE_SEQUENCE', '1')))}))
    Path(os.environ['VELA_TEST_MANIFEST_FILE']).write_bytes(Path(dest).read_bytes())
''')
        (self.fakebin / 'tar').write_text('''#!/usr/bin/env python3
import os, sys
if os.environ.get('VELA_TEST_FAIL_TAR') == '1': sys.exit(2)
os.execv('/usr/bin/tar', ['/usr/bin/tar', *sys.argv[1:]])
''')
        for cmd in ('docker', 'curl', 'tar'):
            (self.fakebin / cmd).chmod(0o755)
        self.log = Path(self.temp.name) / 'docker.log'
        self.state = Path(self.temp.name) / 'state'
        self.state.write_text(OLD)
        self.env = dict(os.environ, VELA_HOME=str(self.root),
                        VELA_TEST_LOG=str(self.log), VELA_TEST_STATE=str(self.state),
                        PATH=str(self.fakebin) + os.pathsep + os.environ['PATH'],
                        VELA_HEALTH_ATTEMPTS='1', VELA_HEALTH_RETRY_SECS='0',
                        VELA_TEST_SIGNING_PRIVATE=str(self.signing_private),
                        VELA_TEST_MANIFEST_FILE=str(Path(self.temp.name)/'manifest-for-signing.json'))

    def run_cli(self, *args, **env):
        return subprocess.run(['bash', str(self.tool), *args], env={**self.env, **env},
                              text=True, capture_output=True, timeout=45)

    def test_update_refuses_unconfigured_signing_key(self):
        # Shipping the preview CLI without a pinned release key must not update.
        raw = self.tool.read_text()
        self.tool.write_text(raw.replace(
            __import__('hashlib').sha256(self.signing_public.read_bytes()).hexdigest(),
            'UNCONFIGURED-RELEASE-SIGNING-KEY'))
        result = self.run_cli('update')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('签名公钥尚未启用', result.stderr)
        self.assertFalse(self.log.exists() and 'stop' in self.log.read_text())

    def test_update_rejects_missing_signature_before_pull(self):
        result = self.run_cli('update', VELA_TEST_UNSIGNED='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('独立签名', result.stderr)
        self.assertNotIn('stop', self.log.read_text() if self.log.exists() else '')

    def test_update_rejects_tampered_signature_before_pull(self):
        result = self.run_cli('update', VELA_TEST_BAD_SIGNATURE='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('签名不合法', result.stderr)
        self.assertNotIn('pull', self.log.read_text() if self.log.exists() else '')

    def test_update_rejects_changed_local_public_key(self):
        self.signing_public.write_text('tampered-public-key')
        result = self.run_cli('update')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('公钥指纹', result.stderr)

    def prepare_reviewed_doctor_fixture(self):
        # The real doctor intentionally needs the reviewed preflight bundle.
        # Keep other lifecycle tests' mocked compose.yaml untouched.
        deploy = ROOT / 'deploy' / 'vela'
        for basename in ('beta_preflight.py', 'compose.host.yml'):
            (self.tool.parent / basename).write_bytes((deploy / basename).read_bytes())
        (self.root / 'compose.yml').write_bytes((deploy / 'compose.host.yml').read_bytes())
        (self.root / 'compose.yml').chmod(0o644)
        (self.root / '.env').write_text(
            'XUI_TG_MINIAPP_ADMIN_IDS=1001\n'
            'XUI_TG_MINIAPP_URL=https://admin.vela-safe-domain.org/app/\n'
            'XUI_PORT=2053\n',
            encoding='utf-8')
        (self.root / '.env').chmod(0o600)
        (self.root / 'secrets' / 'vela_bot_token').write_text('12345:synthetic_only_fixture')
        self.root.chmod(0o700)
        for name in ('db', 'cert', 'acme', 'secrets'):
            (self.root / name).chmod(0o700)
        for name in ('secrets/vela_bot_token', 'image.ref', 'release.sequence'):
            (self.root / name).chmod(0o600)

    def test_doctor_and_reject_unpinned_image(self):
        self.prepare_reviewed_doctor_fixture()
        okay = self.run_cli('doctor')
        self.assertEqual(okay.returncode, 0, okay.stderr)
        self.assertIn('个人内测文件安全', okay.stdout)
        (self.root / 'image.ref').write_text('ghcr.io/smgsp6/3x-ui:latest')
        bad = self.run_cli('doctor')
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('image.ref', bad.stderr)

    def test_doctor_rejects_unsafe_env_before_compose(self):
        self.prepare_reviewed_doctor_fixture()
        with (self.root / '.env').open('a') as out:
            out.write('XUI_TG_MINIAPP_BOT_TOKEN=synthetic-only-not-a-secret\n')
        bad = self.run_cli('doctor')
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('个人内测文件预检未通过', bad.stderr)
        self.assertNotIn(' config', self.log.read_text() if self.log.exists() else '')
        self.assertNotIn('synthetic-only-not-a-secret', bad.stdout + bad.stderr)

    def test_doctor_rejects_symlinked_parent_path(self):
        self.prepare_reviewed_doctor_fixture()
        alias = Path(self.temp.name) / 'alias'
        alias.symlink_to(self.root.parent, target_is_directory=True)
        bad = self.run_cli('doctor', VELA_HOME=str(alias / 'vela'))
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('个人内测文件预检未通过', bad.stderr)
        self.assertNotIn(' config', self.log.read_text() if self.log.exists() else '')

    def test_doctor_rejects_modified_compose_template(self):
        self.prepare_reviewed_doctor_fixture()
        (self.root / 'compose.yml').write_text('services: {vela: {privileged: true}}')
        bad = self.run_cli('doctor')
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('个人内测文件预检未通过', bad.stderr)
        self.assertNotIn(' config', self.log.read_text() if self.log.exists() else '')

    def test_doctor_fails_closed_without_companion_preflight(self):
        self.prepare_reviewed_doctor_fixture()
        (self.tool.parent / 'beta_preflight.py').unlink()
        bad = self.run_cli('doctor')
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn('缺少已审核的个人内测预检文件', bad.stderr)
        self.assertNotIn(' config', self.log.read_text() if self.log.exists() else '')

    def test_reject_loose_secret_permissions(self):
        (self.root / 'secrets' / 'vela_bot_token').chmod(0o644)
        result = self.run_cli('backup')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

    def test_backup_preserves_database_and_certificates(self):
        run = self.run_cli('backup')
        self.assertEqual(run.returncode, 0, run.stderr)
        archives = list((self.root / 'backups').glob('*.tar.gz'))
        self.assertEqual(len(archives), 1)
        self.assertEqual(archives[0].stat().st_mode & 0o777, 0o600)
        with tarfile.open(archives[0], 'r:gz') as tf:
            entries = tf.getnames()
            self.assertIn('db/x-ui.db', entries)
            self.assertIn('cert/panel.pem', entries)
            self.assertIn('acme/state', entries)
            self.assertNotIn('secrets/vela_bot_token', entries)
        self.assertEqual((self.root / 'db' / 'x-ui.db').read_text(), 'original-db')
        self.assertIn('stop', self.log.read_text())
        self.assertIn('start', self.log.read_text())

    def test_health_check_follows_custom_miniapp_base_path(self):
        (self.root / '.env').write_text('XUI_TG_MINIAPP_ADMIN_IDS=1001\nXUI_TG_MINIAPP_URL=https://vela.example.com/private/\n')
        result = self.run_cli('update')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('VELA_HEALTH_PATH=/private/', self.log.read_text())

    def test_custom_health_port_is_checked_without_sourcing_env(self):
        (self.root / '.env').write_text(
            'XUI_TG_MINIAPP_ADMIN_IDS=1001\n'
            'XUI_TG_MINIAPP_URL=https://vela.example.com/private/\n'
            'XUI_PORT=28443\n'
        )
        result = self.run_cli('update')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('VELA_HEALTH_PORT=28443', self.log.read_text())

    def test_bad_port_rejected_before_any_deployment(self):
        (self.root / '.env').write_text(
            'XUI_TG_MINIAPP_ADMIN_IDS=1001\n'
            'XUI_TG_MINIAPP_URL=https://vela.example.com/\n'
            'XUI_PORT=$(touch /tmp/never-run-vela)\n'
        )
        result = self.run_cli('status')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('无效管理端口', result.stderr)

    def test_reject_world_writable_home_and_symlink_backup_directory(self):
        self.root.chmod(0o777)
        unsafe = self.run_cli('backup')
        self.assertNotEqual(unsafe.returncode, 0)
        self.assertIn('VELA_HOME', unsafe.stderr)
        self.root.chmod(0o755)
        destination = Path(self.temp.name)/'outside-backup'
        destination.mkdir()
        (self.root/'backups').symlink_to(destination, target_is_directory=True)
        unsafe = self.run_cli('backup')
        self.assertNotEqual(unsafe.returncode, 0)
        self.assertIn('符号链接', unsafe.stderr)
        self.assertFalse(any(destination.iterdir()))

    def test_non_destructive_status_and_logs(self):
        for command in ('status', 'logs'):
            result = self.run_cli(command)
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'db' / 'x-ui.db').read_text(), 'original-db')
        self.assertIn(' ps', self.log.read_text())
        self.assertIn(' logs', self.log.read_text())

    def test_backup_failure_restarts_old_service_without_switching(self):
        result = self.run_cli('update', VELA_TEST_FAIL_TAR='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('start', self.log.read_text())
        self.assertEqual((self.root / 'image.ref').read_text().strip(), OLD)
        self.assertEqual((self.root / 'db' / 'x-ui.db').read_text(), 'original-db')

    def test_update_does_not_restart_old_service_after_snapshot(self):
        result = self.run_cli('update', VELA_TEST_WRITES_ON_RESTART='1', VELA_TEST_FAIL_HEALTH='1')
        self.assertNotEqual(result.returncode, 0)
        # The updater must not resume write traffic between the backup and
        # candidate deployment; otherwise these writes would disappear on rollback.
        log = self.log.read_text().splitlines()
        first_up = next(i for i, line in enumerate(log) if ' up -d' in line)
        self.assertFalse(any(' start' in line for line in log[:first_up]), log)
        self.assertEqual((self.root / 'db' / 'x-ui.db').read_text(), 'original-db')

    def test_health_is_specific_to_vela_endpoint(self):
        result = self.run_cli('update')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('tg-miniapp/health', self.log.read_text())

    def test_preflight_uses_compose_secret_path_by_default(self):
        checker = ROOT / 'deploy' / 'vela' / 'preflight.sh'
        result = subprocess.run(['bash', str(checker), str(self.root/'.env')],
                                env=self.env, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        (self.root / 'secrets' / 'vela_bot_token').unlink()
        missing = subprocess.run(['bash', str(checker), str(self.root/'.env')],
                                 env=self.env, text=True, capture_output=True, timeout=20)
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn('Bot Token', missing.stderr)

    def test_update_invalid_manifest_never_touches_existing_data(self):
        result = self.run_cli('update', VELA_TEST_BAD_MANIFEST='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('stop', self.log.read_text())
        self.assertEqual((self.root / 'db' / 'x-ui.db').read_text(), 'original-db')
        self.assertEqual((self.root / 'image.ref').read_text().strip(), OLD)

    def test_update_pull_failure_does_not_stop_server(self):
        result = self.run_cli('update', VELA_TEST_FAIL_PULL='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('stop', self.log.read_text())
        self.assertEqual((self.root / 'db' / 'x-ui.db').read_text(), 'original-db')

    def _seed_real_sqlite(self):
        """Use an actual SQLite database, never an uploaded customer snapshot."""
        import sqlite3
        db = self.root / 'db' / 'x-ui.db'
        # The existing offline CLI fixture contains placeholder text, not SQLite.
        # Replace only this temporary test fixture with a real database.
        db.unlink()
        with sqlite3.connect(db) as connection:
            connection.execute('CREATE TABLE vela_ci_only (id INTEGER PRIMARY KEY, value TEXT NOT NULL)')
            connection.executemany(
                'INSERT INTO vela_ci_only(id, value) VALUES (?, ?)',
                [(1, 'before-snapshot'), (2, 'retain-second-row')],
            )
        db.chmod(0o600)
        return db

    def _assert_real_sqlite_restored(self, db):
        import sqlite3
        self.assertEqual(db.stat().st_mode & 0o777, 0o600)
        with sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True) as connection:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone(), ('ok',))
            rows = connection.execute('SELECT id, value FROM vela_ci_only ORDER BY id').fetchall()
        self.assertEqual(rows, [(1, 'before-snapshot'), (2, 'retain-second-row')])

    def test_real_sqlite_signed_candidate_failure_restores_snapshot(self):
        db = self._seed_real_sqlite()
        result = self.run_cli('update', VELA_TEST_FAIL_HEALTH='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('恢复旧镜像', result.stdout)
        self._assert_real_sqlite_restored(db)
        self.assertEqual((self.root / 'image.ref').read_text().strip(), OLD)
        self.assertEqual((self.root / 'release.sequence').read_text().strip(), '0')
        self.assertFalse((self.root / '.pending-update').exists())
        archived = list((self.root / 'backups').glob('vela-*.tar.gz'))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].stat().st_mode & 0o777, 0o600)
        with tarfile.open(archived[0], 'r:gz') as tf:
            names = set(tf.getnames())
            self.assertTrue({'db/x-ui.db', 'cert/panel.pem', 'acme/state'} <= names)
            self.assertFalse(any(x.startswith('secrets/') for x in names))
        quarantined = list((self.root / 'failed-updates').glob('*/db/x-ui.db'))
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(quarantined[0].read_text(), 'migrated-db')

    def test_real_sqlite_interrupted_upgrade_recovery_restores_exact_rows(self):
        import sqlite3
        db = self._seed_real_sqlite()
        snapshot_result = self.run_cli('backup')
        self.assertEqual(snapshot_result.returncode, 0, snapshot_result.stderr)
        archive = next((self.root / 'backups').glob('vela-*.tar.gz'))
        (self.root / '.pending-update').write_text(
            OLD + '\n' + NEW + '\n' + str(archive) + '\n0\n')
        (self.root / '.pending-update').chmod(0o600)
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE vela_ci_only SET value='candidate-write' WHERE id=1")
        (self.root / 'image.ref').write_text(NEW + '\n')
        self.state.write_text(NEW)
        result = self.run_cli('recover')
        self.assertEqual(result.returncode, 0, result.stderr)
        self._assert_real_sqlite_restored(db)
        self.assertFalse((self.root / '.pending-update').exists())
        self.assertEqual((self.root / 'image.ref').read_text().strip(), OLD)
        self.assertEqual((self.root / 'release.sequence').read_text().strip(), '0')
        self.assertEqual((self.root / 'cert' / 'panel.pem').read_text(), 'cert bytes')
        self.assertEqual((self.root / 'acme' / 'state').read_text(), 'acme bytes')
        preserved = list((self.root / 'failed-updates').glob('*/db/x-ui.db'))
        self.assertEqual(len(preserved), 1)
        with sqlite3.connect(preserved[0]) as connection:
            state = connection.execute(
                'SELECT value FROM vela_ci_only WHERE id=1').fetchone()
        self.assertEqual(state, ('candidate-write',))

    def test_invalid_archive_refuses_real_sqlite_recovery_without_data_loss(self):
        import sqlite3
        db = self._seed_real_sqlite()
        snapshot_result = self.run_cli('backup')
        self.assertEqual(snapshot_result.returncode, 0, snapshot_result.stderr)
        archive = next((self.root / 'backups').glob('vela-*.tar.gz'))
        archive.write_bytes(b'synthetic-corrupted-archive')
        (self.root / '.pending-update').write_text(
            OLD + '\n' + NEW + '\n' + str(archive) + '\n0\n')
        (self.root / '.pending-update').chmod(0o600)
        with sqlite3.connect(db) as connection:
            connection.execute("UPDATE vela_ci_only SET value='current-precious-state' WHERE id=1")
        before = db.read_bytes()
        result = self.run_cli('recover')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.root / '.pending-update').exists())
        self.assertEqual(db.read_bytes(), before)
        self.assertFalse((self.root / 'failed-updates').exists())
        self.assertEqual((self.root / 'image.ref').read_text().strip(), OLD)
        self.assertNotIn(' up -d', self.log.read_text())

    def test_update_bad_health_restores_both_image_and_database(self):
        result = self.run_cli('update', VELA_TEST_FAIL_HEALTH='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('恢复旧镜像', result.stdout)
        self.assertEqual((self.root / 'image.ref').read_text().strip(), OLD)
        self.assertEqual((self.root / 'db' / 'x-ui.db').read_text(), 'original-db')
        saved = list((self.root / 'failed-updates').glob('*/db/x-ui.db'))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_text(), 'migrated-db')

    def test_successful_update_keeps_backup_and_installs_digest(self):
        result = self.run_cli('update')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'image.ref').read_text().strip(), NEW)
        self.assertEqual((self.root / 'db' / 'x-ui.db').read_text(), 'migrated-db')
        self.assertEqual(len(list((self.root / 'backups').glob('*.tar.gz'))), 1)

    def test_pending_upgrade_blocks_another_update(self):
        (self.root / '.pending-update').write_text(OLD + '\n' + NEW + '\n\n')
        result = self.run_cli('update')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('vela recover', result.stderr)
        self.assertFalse(self.log.exists())

    def test_recover_pre_backup_interrupt_restarts_old(self):
        (self.root / '.pending-update').write_text(OLD + '\n' + NEW + '\n\n')
        result = self.run_cli('recover')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'image.ref').read_text().strip(), OLD)
        self.assertFalse((self.root / '.pending-update').exists())
        self.assertIn(' up -d', self.log.read_text())

    def test_recover_interrupted_update_restores_snapshot(self):
        initial = self.run_cli('backup')
        self.assertEqual(initial.returncode, 0, initial.stderr)
        snapshot = next((self.root / 'backups').glob('vela-*.tar.gz'))
        (self.root / '.pending-update').write_text(OLD + '\n' + NEW + '\n' + str(snapshot) + '\n')
        (self.root / 'image.ref').write_text(NEW + '\n')
        (self.root / 'db' / 'x-ui.db').write_text('migration-before-crash')
        self.state.write_text(NEW)
        result = self.run_cli('recover')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'db' / 'x-ui.db').read_text(), 'original-db')
        self.assertEqual((self.root / 'image.ref').read_text().strip(), OLD)
        self.assertFalse((self.root / '.pending-update').exists())
        self.assertTrue(list((self.root / 'failed-updates').glob('*/db/x-ui.db')))

    def test_malformed_recovery_record_fails_closed(self):
        (self.root / '.pending-update').write_text('$(echo insecure)\n' + NEW + '\n\n')
        result = self.run_cli('recover')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('镜像摘要', result.stderr)
        self.assertNotIn(' stop', self.log.read_text())

    def test_normal_update_clears_recovery_record(self):
        result = self.run_cli('update')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.root / '.pending-update').exists())

    def test_failed_update_after_rollback_clears_record(self):
        result = self.run_cli('update', VELA_TEST_FAIL_HEALTH='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / '.pending-update').exists())

    def test_recover_after_power_loss_mid_restore(self):
        initial = self.run_cli('backup')
        self.assertEqual(initial.returncode, 0, initial.stderr)
        snapshot = next((self.root / 'backups').glob('vela-*.tar.gz'))
        (self.root / '.pending-update').write_text(OLD + '\n' + NEW + '\n' + str(snapshot) + '\n')
        # Simulate a reboot after the old DB has been moved to failed-updates,
        # but before cert/acme have been moved or the backup extracted.
        partial = self.root / 'failed-updates' / 'interrupted'
        partial.mkdir(parents=True)
        (self.root / 'db').rename(partial / 'db')
        self.state.write_text(NEW)
        result = self.run_cli('recover')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'db' / 'x-ui.db').read_text(), 'original-db')
        self.assertEqual((self.root / 'cert' / 'panel.pem').read_text(), 'cert bytes')
        self.assertEqual((self.root / 'acme' / 'state').read_text(), 'acme bytes')
        self.assertFalse((self.root / '.pending-update').exists())

    def test_recover_rejects_archive_path_traversal(self):
        import io
        initial = self.run_cli('backup')
        self.assertEqual(initial.returncode, 0, initial.stderr)
        snapshot = next((self.root / 'backups').glob('vela-*.tar.gz'))
        with tarfile.open(snapshot, 'w:gz') as tf:
            payload = b'not real data'
            item = tarfile.TarInfo('db/../../escape.dat')
            item.size = len(payload)
            tf.addfile(item, io.BytesIO(payload))
        (self.root / '.pending-update').write_text(OLD + '\n' + NEW + '\n' + str(snapshot) + '\n')
        self.state.write_text(NEW)
        (self.root / 'db' / 'x-ui.db').write_text('current-data')
        result = self.run_cli('recover')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('备份不可信', result.stderr)
        self.assertEqual((self.root / 'db' / 'x-ui.db').read_text(), 'current-data')
        self.assertTrue((self.root / '.pending-update').exists())
        self.assertFalse((self.root.parent / 'escape.dat').exists())

    def test_backup_rejects_symlink_to_external_private_file(self):
        external = Path(self.temp.name) / 'external-secret'
        external.write_text('private-value')
        (self.root / 'cert' / 'unsafe-link').symlink_to(external)
        result = self.run_cli('backup')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('备份完整性/路径安全', result.stderr)
        self.assertFalse(list((self.root / 'backups').glob('*.tar.gz')))
        self.assertEqual(external.read_text(), 'private-value')
        self.assertIn(' start', self.log.read_text())


    def test_signed_old_sequence_replay_rejected_without_pull(self):
        (self.root / 'release.sequence').write_text('7\n')
        result = self.run_cli('update', VELA_TEST_RELEASE_SEQUENCE='6')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('旧签名发布清单', result.stderr)
        self.assertNotIn(' pull', self.log.read_text())
        self.assertEqual((self.root / 'db' / 'x-ui.db').read_text(), 'original-db')

    def test_signed_sequence_type_confusion_rejected(self):
        result = self.run_cli('update', VELA_TEST_BOOL_SEQUENCE='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('发行序号', result.stderr)
        self.assertNotIn(' pull', self.log.read_text())

    def test_signed_sequence_advances_after_success(self):
        result = self.run_cli('update', VELA_TEST_RELEASE_SEQUENCE='12')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'release.sequence').read_text().strip(), '12')
        self.assertFalse((self.root / '.pending-update').exists())

    def test_failed_candidate_restores_previous_sequence(self):
        (self.root / 'release.sequence').write_text('3\n')
        result = self.run_cli('update', VELA_TEST_RELEASE_SEQUENCE='4', VELA_TEST_FAIL_HEALTH='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / 'release.sequence').read_text().strip(), '3')
        self.assertEqual((self.root / 'image.ref').read_text().strip(), OLD)

    def test_recovery_after_crash_restores_previous_sequence(self):
        (self.root / 'release.sequence').write_text('5\n')
        initial = self.run_cli('backup')
        self.assertEqual(initial.returncode, 0, initial.stderr)
        snapshot = next((self.root / 'backups').glob('vela-*.tar.gz'))
        (self.root / '.pending-update').write_text(
            OLD + '\n' + NEW + '\n' + str(snapshot) + '\n5\n')
        (self.root / 'image.ref').write_text(NEW + '\n')
        (self.root / 'release.sequence').write_text('6\n')
        self.state.write_text(NEW)
        result = self.run_cli('recover')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.root / 'release.sequence').read_text().strip(), '5')
        self.assertEqual((self.root / 'image.ref').read_text().strip(), OLD)

    def test_missing_sequence_file_blocks_even_signed_update(self):
        (self.root / 'release.sequence').unlink()
        result = self.run_cli('update')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('缺少发行版本序号', result.stderr)
        self.assertFalse(self.log.exists())

    def test_same_sequence_different_digest_rejected(self):
        (self.root / 'release.sequence').write_text('1\n')
        result = self.run_cli('update', VELA_TEST_RELEASE_SEQUENCE='1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('相同发行序号指向不同镜像', result.stderr)
        self.assertNotIn(' pull', self.log.read_text())

    def test_sequence_symlink_fails_closed(self):
        sequence_external = Path(self.temp.name) / 'external-sequence'
        sequence_external.write_text('12\n')
        (self.root / 'release.sequence').unlink()
        (self.root / 'release.sequence').symlink_to(sequence_external)
        result = self.run_cli('update')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('版本序号文件不安全', result.stderr)
        self.assertEqual(sequence_external.read_text(), '12\n')


if __name__ == '__main__':
    unittest.main()
