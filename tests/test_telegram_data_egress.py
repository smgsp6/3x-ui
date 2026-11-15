"""Verify the legacy Telegram DB/Xray export surfaces are blocked in Vela.

These are source-level contract tests on the fully *applied* patch. They do not
claim that every outbound data path in the whole upstream project is audited.
"""
from pathlib import Path
import tempfile
import unittest
import test_apply_to_repo as patch_helpers

class PrivateDataEgressTests(unittest.TestCase):
    def test_raw_backup_exports_are_blocked_at_all_known_entrypoints(self):
        with tempfile.TemporaryDirectory() as d:
            h = patch_helpers.PatchTests()
            repo = h.make_repo(Path(d))
            h.execute(repo)
            bot = (repo / 'internal/web/service/tgbot')
            files = {
                'notices': (bot / 'notices.go').read_text(),
                'report': (bot / 'tgbot_report.go').read_text(),
                'screens': (bot / 'screen_views.go').read_text(),
                'menu': (bot / 'screen_view.go').read_text(),
                'api': (repo / 'internal/web/controller/api.go').read_text(),
            }
            self.assertIn('if tgminiapp.Enabled() { return false }',files['notices'])
            self.assertIn('func (t *Tgbot) SendBackupToAdmins() {\n    if tgminiapp.Enabled() { return }',files['report'])
            self.assertIn('func (t *Tgbot) SendReport() {\n    // Enabling a Mini App',files['report'])
            self.assertIn('func (t *Tgbot) sendBackupScreen(chatID int64) {\n    if tgminiapp.Enabled()',files['screens'])
            self.assertIn('if !tgminiapp.Enabled() {\n\t\t\trows = append(rows',files['menu'])
            self.assertIn('func (a *APIController) BackuptoTgbot(c *gin.Context) {\n    if tgminiapp.Enabled()',files['api'])
            # The new audit logic must reference the same feature switch as the
            # Mini App and must never introduce the old unrestricted exporter.
            for name in ('notices','report','screens'):
                self.assertIn('"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"',files[name])

if __name__ == '__main__':
    unittest.main()
