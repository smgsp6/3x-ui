"""Hermetic integration checks for the source-only Vela patch applier.

No network, no real git changes; it mocks git metadata and creates a fixture
whose original source blocks match the reviewed upstream snapshot.
"""
import ast
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('vela_patcher', ROOT / 'apply_to_repo.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class PatchTests(unittest.TestCase):
    def make_repo(self, root):
        repo = root / 'repo'
        (repo / '.git').mkdir(parents=True)
        nodes = {}
        for node in ast.walk(ast.parse((ROOT / 'apply_to_repo.py').read_text())):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != 'modify':
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            pathname = node.args[0].value
            if pathname not in nodes:
                nodes[pathname] = []
            if isinstance(node.args[1], ast.List):
                for pair in node.args[1].elts:
                    if not isinstance(pair, ast.Tuple) or not pair.elts:
                        continue
                    try:
                        text = ast.literal_eval(pair.elts[0])
                    except (ValueError, TypeError):
                        continue
                    if isinstance(text, str):
                        nodes[pathname].append(text)
        for path, chunks in nodes.items():
            file = repo / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('\n'.join(chunks), encoding='utf-8')
        # Manifest must have the exact upstream icon references.
        manifest = {
          'name':'3x-ui','short_name':'3x-ui',
          'background_color':'#0f172a','theme_color':'#1677ff',
          'icons':[{'src':f'icons/3x-ui-{size}.png'} for size in (16,24,32,64,192,512)]
        }
        (repo / 'frontend/public/manifest.webmanifest').write_text(json.dumps(manifest),encoding='utf-8')
        for lang in ('zh-CN','en-US'):
            loc = repo / f'internal/web/translation/{lang}.json'
            loc.parent.mkdir(parents=True,exist_ok=True)
            loc.write_text('{\n"menu": {"dashboard": "首页"}\n}',encoding='utf-8')
        (repo / '.dockerignore').write_text('db\ncert\n*.dump\n', encoding='utf-8')
        (repo / 'README.md').write_text('**3X-UI** upstream MHSanaei/3x-ui',encoding='utf-8')
        return repo

    def execute(self, repo, *args, branch='feat/vela', sha='5297fd3c8495d80fab97ae511553fa545c69e913', origin='https://github.com/smgsp6/3x-ui.git', status=''):
        def fake_run(r, *gitargs):
            switch = tuple(gitargs)
            if switch == ('remote','get-url','origin'):
                return origin
            if switch == ('rev-parse','HEAD'):
                return sha
            if switch == ('symbolic-ref','--short','HEAD'):
                return branch
            if switch == ('status','--porcelain'):
                return status
            raise AssertionError(switch)
        with patch.object(mod, 'run', side_effect=fake_run):
            with patch.object(sys, 'argv', ['apply_to_repo.py',str(repo),*args]):
                mod.main()

    def test_check_and_apply_on_reviewed_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            self.execute(repo, '--check')
            self.assertFalse((repo/'frontend/src/assets/vela-mark.png').exists())
            self.execute(repo)
            self.assertTrue((repo/'frontend/src/assets/vela-mark.png').is_file())
            self.assertTrue((repo/'frontend/public/icons/vela-512.png').is_file())
            self.assertTrue((repo/'tests/test_apply_to_repo.py').is_file())
            self.assertTrue((repo/'docs/PHASE9-TEST-REPORT.md').is_file())
            self.assertTrue((repo/'docs/PHASE10-TEST-REPORT.md').is_file())
            self.assertTrue((repo/'tests/test_certificate_contract.py').is_file())
            self.assertTrue((repo/'internal/web/service/tgminiapp/tls_reloader.go').is_file())
            self.assertIn('Vela',(repo/'frontend/public/manifest.webmanifest').read_text())
            self.assertIn('secrets/',(repo/'.gitignore').read_text())
            self.assertIn('secrets/',(repo/'.dockerignore').read_text())
            self.assertIn('**/.env', (repo/'.dockerignore').read_text())
            self.assertIn('Vela',(repo/'README.md').read_text())

    def test_telegram_button_only_private_and_token_file_only(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            self.execute(repo)
            bot = (repo/'internal/web/service/tgbot/tgbot.go').read_text()
            menu = (repo/'internal/web/service/tgbot/screen_view.go').read_text()
            caller = (repo/'internal/web/service/tgbot/screen_views.go').read_text()
            scheduler = (repo/'internal/web/web.go').read_text()
            self.assertIn('tgminiapp.BotToken()', bot)
            self.assertIn('if tgminiapp.Enabled()', bot)
            self.assertIn('tgminiapp.AdminUserIDs()', bot)
            self.assertIn('chatID > 0 && tgminiapp.AllowedUserID(chatID)', menu)
            self.assertIn('t.homeRows(chatID)...', caller)
            self.assertIn('s.cron.AddFunc("0 0 9 * * *"', scheduler)
            self.assertIn('s.tgbotService.SendMsgToTgbot(chatID, body)', scheduler)
            self.assertIn('c.GetCertificate = reloader.GetCertificate', scheduler)
            self.assertIn('tgminiapp.CertAlertsEnabled()', scheduler)

    def test_applied_bundle_passes_local_privacy_release_gate(self):
        # Checks the ACTUAL set of copied files, including the audit tool's own
        # test fixtures: high-confidence scanner rules must not block releases
        # because a test file accidentally contains a literal key header.
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            self.execute(repo)
            proc = subprocess.run(
                [sys.executable, str(repo/'deploy/vela/privacy_audit.py'), str(repo)],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_copy_failure_restores_original_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            previous = {p: p.read_bytes() for p in repo.rglob('*') if p.is_file()}
            with patch.object(mod.shutil, 'copy2', side_effect=OSError('simulated copy failure')):
                with self.assertRaisesRegex(OSError, 'simulated copy failure'):
                    self.execute(repo)
            for file, bytes_before in previous.items():
                self.assertEqual(file.read_bytes(), bytes_before, file)
            self.assertFalse((repo / 'internal/web/service/tgminiapp/auth.go').exists())

    def test_refuse_preexisting_symlink_in_new_file_location(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            outside = Path(temp)/'outside.txt'
            outside.write_text('must-not-change')
            target = repo/'internal/web/service/tgminiapp/auth.go'
            target.parent.mkdir(parents=True)
            target.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'symlink'):
                self.execute(repo)
            self.assertEqual(outside.read_text(), 'must-not-change')

    def test_partial_copy_failure_cleans_new_file(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            def partial_copy(src, dst):
                Path(dst).write_text('partially written')
                raise OSError('partial copy failure')
            with patch.object(mod.shutil, 'copy2', side_effect=partial_copy):
                with self.assertRaisesRegex(OSError, 'partial copy failure'):
                    self.execute(repo)
            self.assertFalse((repo/'internal/web/controller/miniapp.go').exists())
            self.assertIn('3X-UI', (repo/'README.md').read_text())

    def test_refuse_symlinked_temp_file_without_touching_outside(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            outside = Path(temp) / 'not-in-repository.txt'
            outside.write_text('PRIVATE OUTSIDE DATA', encoding='utf-8')
            (repo / 'README.md.vela-tmp').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'unsafe pre-existing patch temporary'):
                self.execute(repo)
            self.assertEqual(outside.read_text(), 'PRIVATE OUTSIDE DATA')
            self.assertIn('3X-UI', (repo / 'README.md').read_text())

    def test_refuse_symlink_ancestor_in_new_bundle_path(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            outside = Path(temp) / 'outside-dir'
            outside.mkdir()
            # Parent that must not become an output directory.
            (repo / 'brand').symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'unsafe symlink component'):
                self.execute(repo)
            self.assertFalse(list(outside.iterdir()))

    def test_reject_other_repo_and_unreviewed_sha(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            with self.assertRaisesRegex(ValueError,'wrong origin'):
                self.execute(repo,'--check',origin='https://github.com/someone/another-project')
            with self.assertRaisesRegex(ValueError,'unsupported HEAD'):
                self.execute(repo,'--check',sha='0'*40)
            with self.assertRaisesRegex(ValueError,'default branch'):
                self.execute(repo,'--check',branch='main')
            with self.assertRaisesRegex(ValueError,'uncommitted changes'):
                self.execute(repo,'--check',status=' M README.md')

if __name__ == '__main__':
    unittest.main()
