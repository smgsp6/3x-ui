#!/usr/bin/env python3
"""Apply reviewed Vela development-preview changes ONLY to smgsp6/3x-ui.

Never uploads anything, never changes remotes, and refuses a dirty checkout.
Creates no Git branch or commit. Read the patch before applying it.
"""
from pathlib import Path
import argparse
import os
import re
import shutil
import subprocess
import sys

BUNDLE = Path(__file__).resolve().parent


def run(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], text=True,
                          capture_output=True, check=True).stdout.strip()


def edit_once(content, old, new, name):
    num = content.count(old)
    if num != 1:
        raise ValueError(f"{name}: expected one matching original block, found {num}; upstream may have changed")
    return content.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", help="Local checkout of github.com/smgsp6/3x-ui (NOT another repo)")
    parser.add_argument("--check", action="store_true", help="Check the patch without writing files")
    options = parser.parse_args()
    repo = Path(options.repo).resolve()
    if not (repo / ".git").exists():
        raise ValueError("not a Git checkout; clone your own smgsp6/3x-ui fork first")
    origin = run(repo, "remote", "get-url", "origin")
    if not re.fullmatch(r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)smgsp6/3x-ui(?:\.git)?/?", origin, re.I):
        raise ValueError(f"wrong origin {origin!r}; only smgsp6/3x-ui is allowed")
    # The bundle is tied to a reviewed upstream snapshot. Reject later upstream
    # revisions until this integration patch is re-reviewed against them.
    expected_head = "5297fd3c8495d80fab97ae511553fa545c69e913"
    actual_head = run(repo, "rev-parse", "HEAD")
    if actual_head != expected_head:
        raise ValueError(f"unsupported HEAD {actual_head}; expected {expected_head}, re-review after upstream sync")
    branch = run(repo, "symbolic-ref", "--short", "HEAD")
    if branch in ("main", "master"):
        raise ValueError("refusing to modify the default branch; create a feature branch based on the reviewed HEAD")
    dirty = run(repo, "status", "--porcelain")
    if dirty:
        raise ValueError("checkout has uncommitted changes; commit/stash them first")

    updates = {}

    def ensure_no_symlink_components(path):
        # Fail closed: neither a modified source nor an ancestor of a new file
        # may point outside the intended Git checkout.
        relative = path.relative_to(repo)
        current = repo
        for component in relative.parts:
            current = current / component
            if current.is_symlink():
                raise ValueError(f"unsafe symlink component: {current}")

    def modify(name, steps):
        path = repo / name
        ensure_no_symlink_components(path)
        if not path.is_file():
            raise ValueError(f"source file missing or not regular: {path}")
        s = path.read_text(encoding="utf-8")
        for old, new in steps:
            s = edit_once(s, old, new, name)
        updates[path] = s

    # Private runtime state lives on servers, never in the public Git tree.
    modify(".gitignore", [
        ("# Ignore .env (Environment Variables) file\n.env", 
         "# Ignore .env (Environment Variables) file\n.env\n.env.*\n!.env.example\n# Vela: never stage local databases, credentials, ACME accounts or certificates\nsecrets/\n.secrets/\ncert/\nacme/\ndb/\npgdata/\n*.key\n*.p12\n*.pfx\n*.pem\n__pycache__/\n.pytest_cache/"),
    ])

    # Dockerfile runs COPY . . in the builder. Prevent private runtime files
    # from entering *any* build context, intermediate layer or remote build cache.
    # Keep upstream source fixtures untouched (do not globally exclude *.pem).
    modify(".dockerignore", [
        ("*.dump", "*.dump\n# Vela: private operator data must never enter Docker build context\n.env\n.env.*\n**/.env\n**/.env.*\nsecrets/\n**/secrets/\nacme/\n**/acme/\nbackups/\n**/backups/\nfailed-updates/\n**/failed-updates/\n*.db-wal\n*.db-shm\n*.key\n*.p12\n*.pfx\n**/*private*.pem\n**/__pycache__/\n*.pyc\n.pytest_cache/"),
    ])

    # Leave upstream Docker Compose UNCHANGED. Vela has its own host-network
    # candidate template: legacy bridge port forwarding would be incompatible
    # with the Mini App's forced loopback-bound panel listener.

    modify("internal/web/session/session.go", [
        ('"github.com/mhsanaei/3x-ui/v3/internal/logger"',
         '"github.com/mhsanaei/3x-ui/v3/internal/logger"\n\t"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"'),
        ('apiAuthUserKey    = "api_auth_user"',
         'apiAuthUserKey    = "api_auth_user"\n\ttelegramMiniAppUserKey = "TELEGRAM_MINIAPP_USER_ID"'),
        ('''s := sessions.Default(c)
	// Anyone can mint the anonymous session this request carried and plant it in a browser,''',
         '''s := sessions.Default(c)
    // Credential rotation from within Mini App must retain the signed Telegram
    // identity. A legacy caller cannot mint a Vela session via this function.
    var tgID int64
    if tgminiapp.Enabled() {
        id, ok := s.Get(telegramMiniAppUserKey).(int64)
        if !ok || !tgminiapp.AllowedUserID(id) { return http.ErrNoCookie }
        tgID = id
    }
	// Anyone can mint the anonymous session this request carried and plant it in a browser,'''),
        ('''s.Set(loginEpochKey, user.LoginEpoch)
	return s.Save()
}

func SetAPIAuthUser''',
         '''s.Set(loginEpochKey, user.LoginEpoch)
    if tgminiapp.Enabled() { s.Set(telegramMiniAppUserKey, tgID) }
	return s.Save()
}

func SetAPIAuthUser'''),
        ('func SetAPIAuthUser(c *gin.Context, user *model.User) {',
         '''// SetTelegramMiniAppLoginUser binds a signed Telegram identity to the same
// normal panel user session; changing the admin allowlist revokes access.
func SetTelegramMiniAppLoginUser(c *gin.Context, user *model.User, telegramID int64) error {
    if user == nil || telegramID <= 0 || !tgminiapp.AllowedUserID(telegramID) {
        return http.ErrNoCookie
    }
    s := sessions.Default(c)
    s.Clear()
    s.Set(loginUserKey, user.Id)
    s.Set(loginEpochKey, user.LoginEpoch)
    s.Set(telegramMiniAppUserKey, telegramID)
    return s.Save()
}

func SetAPIAuthUser(c *gin.Context, user *model.User) {'''),
        ('s := sessions.Default(c)\n\tobj := s.Get(loginUserKey)',
         '''s := sessions.Default(c)
    if tgminiapp.Enabled() {
        telegramID, ok := s.Get(telegramMiniAppUserKey).(int64)
        if !ok || !tgminiapp.AllowedUserID(telegramID) { return nil }
    }
    obj := s.Get(loginUserKey)''')
    ])

    modify("internal/web/controller/index.go", [
        ('"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgbot"',
         '"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgbot"\n\t"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"'),
        ('\tserveDistPage(c, "login.html")\n}',
         '''    if tgminiapp.Enabled() {
        middleware.AllowTelegramMiniAppSDK(c)
        serveDistPage(c, "miniapp.html")
        return
    }
    serveDistPage(c, "login.html")
}'''),
        ('func (a *IndexController) login(c *gin.Context) {',
         '''func (a *IndexController) login(c *gin.Context) {
    if tgminiapp.Enabled() {
        c.AbortWithStatus(http.StatusNotFound)
        return
    }'''),
    ])

    modify("internal/web/middleware/security.go", [
        ('"net/http"', '"net/http"\n\t"strings"'),
        ('func newCSPNonce() string {',
         '''// AllowTelegramMiniAppSDK relaxes CSP ONLY for the official Mini App
// bootstrap page. It does not allow arbitrary inline scripts or HTML Widgets.
func AllowTelegramMiniAppSDK(c *gin.Context) {
    policy := c.Writer.Header().Get("Content-Security-Policy")
    const original = "script-src 'self' "
    if strings.Contains(policy, original) {
        c.Header("Content-Security-Policy", strings.Replace(policy, original,
            "script-src 'self' https://telegram.org ", 1))
    }
}

func newCSPNonce() string {''')
    ])

    modify("internal/web/web.go", [
        ('"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgbot"',
         '"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgbot"\n\t"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"'),
        ('Secure:   directHTTPS,', 'Secure:   directHTTPS || tgminiapp.Enabled(),'),
        ('\tstore.Options(sessionOptions)',
         '''    if tgminiapp.Enabled() && (sessionOptions.MaxAge == 0 || sessionOptions.MaxAge > 8*60*60) {
        sessionOptions.MaxAge = 8 * 60 * 60 // limit long-lived Mini App admin sessions
    }
    store.Options(sessionOptions)'''),
        # Host networking preserves dynamic Xray listeners while keeping
        # the HTTP management server off public interfaces by default.
        # Vela only: automatically adopt renewed cert/key after both validate.
        # No shell commands, no private data leave this machine.
        ('c := &tls.Config{\n\t\t\t\tCertificates: []tls.Certificate{cert},\n\t\t\t}',
         'c := &tls.Config{\n\t\t\t\tCertificates: []tls.Certificate{cert},\n\t\t\t}\n            if tgminiapp.Enabled() {\n                reloader := tgminiapp.NewTLSCertificateReloader(certFile, keyFile, cert)\n                c.GetCertificate = reloader.GetCertificate\n                c.Certificates = nil // callback is used even when SNI is absent\n            }'),
        ('\tlistenAddr := net.JoinHostPort(listen, strconv.Itoa(port))',
         """if tgminiapp.Enabled() {
        listen = "127.0.0.1" // HTTPS reverse proxy is required
    }
    listenAddr := net.JoinHostPort(listen, strconv.Itoa(port))"""),
        # Upstream falls back to HTTP when an explicitly configured TLS pair
        # fails to load. In Vela mode that would silently downgrade transport.
        # If no TLS pair is configured, loopback HTTP remains valid behind
        # an operator-controlled HTTPS reverse proxy.
        ('\t\t} else {\n\t\t\tlogger.Error("Error loading certificates:", err)\n\t\t\tlogger.Info("Web server running HTTP on", listener.Addr())',
         '''            } else {
                if tgminiapp.Enabled() {
                    _ = listener.Close()
                    return fmt.Errorf("Vela TLS material is invalid; refusing silent HTTP downgrade")
                }
                logger.Error("Error loading certificates:", err)
                logger.Info("Web server running HTTP on", listener.Addr())'''),
        ('\ts.index = controller.NewIndexController(g)',
         '\tcontroller.NewMiniAppController(g)\n\ts.index = controller.NewIndexController(g)'),
        # Opt-in daily alert; read settings locally and send generic text only.
        ('\tisDiscordEnabled, err := s.settingService.GetDiscordBotEnable()\n\tif (err == nil) && isDiscordEnabled && s.discordGateway != nil {',
         '''    if startTgBot && tgminiapp.CertAlertsEnabled() {
        _, addErr := s.cron.AddFunc("0 0 9 * * *", func() {
            webCert, err1 := s.settingService.GetCertFile()
            webKey, err2 := s.settingService.GetKeyFile()
            subCert, err3 := s.settingService.GetSubCertFile()
            subKey, err4 := s.settingService.GetSubKeyFile()
            if err1 != nil || err2 != nil || err3 != nil || err4 != nil {
                logger.Warning("Vela certificate monitor: settings unavailable")
                return
            }
            now := time.Now()
            statuses := []tgminiapp.CertificateStatus{
                tgminiapp.InspectCertificate("panel", webCert, webKey, now),
                tgminiapp.InspectCertificate("subscription", subCert, subKey, now),
            }
            _, notifyErr := tgminiapp.SendCertificateAlerts(now, statuses, func(chatID int64, body string) bool {
                return s.tgbotService.SendMsgToTgbot(chatID, body) != 0
            })
            if notifyErr != nil {
                // Never log paths, tokens, private IDs or domains.
                logger.Warning("Vela certificate monitor: notification state unavailable")
            }
        })
        if addErr != nil { logger.Warning("Vela certificate monitor: scheduler unavailable") }
    }

\tisDiscordEnabled, err := s.settingService.GetDiscordBotEnable()
    if (err == nil) && isDiscordEnabled && s.discordGateway != nil {''')
    ])

    modify("internal/web/controller/api.go", [
        ('"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgbot"',
         '"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgbot"\n\t"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"'),
        ('\tif matchedScope != "" {\n\t\tsetAuthenticated(matchedScope)',
         '    // In Mini App mode, legacy unrestricted API tokens are not an alternate login.\n    // Scoped monitor and node-sync tokens remain available to existing nodes.\n    if tgminiapp.Enabled() && matchedScope == model.ApiScopeAdmin { matchedScope = "" }\n    if matchedScope != "" {\n\t\tsetAuthenticated(matchedScope)'),
        ('\tcase model.ApiScopeNodeAdmin:\n\t\tif scopeAllows(',
         '    case model.ApiScopeNodeAdmin:\n        // Legacy node-admin update runs upstream update.sh; forbidden for Vela.\n        if tgminiapp.Enabled() && rel == "/server/updatePanel" { deny(); return }\n\t\tif scopeAllows('),
        ('\tapi.GET("/openapi.json", ServeOpenAPISpec)',
         '\tapi.GET("/openapi.json", ServeOpenAPISpec)\n\tNewCertificateStatusController(api)'),
        ('func (a *APIController) BackuptoTgbot(c *gin.Context) {',
         '''func (a *APIController) BackuptoTgbot(c *gin.Context) {
    if tgminiapp.Enabled() { c.AbortWithStatus(http.StatusForbidden); return }''')
    ])

    modify("internal/web/controller/server.go", [
        ('"github.com/mhsanaei/3x-ui/v3/internal/web/service/panel"',
         '"github.com/mhsanaei/3x-ui/v3/internal/web/service/panel"\n\t"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"'),
        ('func (a *ServerController) updatePanel(c *gin.Context) {',
         '''func (a *ServerController) updatePanel(c *gin.Context) {
    // The upstream updater fetches a mutable remote shell script. This would
    // replace Vela with upstream 3x-ui; Vela publishes verified Docker images instead.
    if tgminiapp.Enabled() { c.AbortWithStatus(http.StatusForbidden); return }'''),
    ])

    modify("internal/web/service/setting.go", [
        ('func (s *SettingService) GetTgbotEnabled() (bool, error) {\n\treturn s.getBool("tgBotEnable")',
         'func (s *SettingService) GetTgbotEnabled() (bool, error) {\n    if strings.EqualFold(strings.TrimSpace(os.Getenv("XUI_TG_MINIAPP_ENABLED")), "true") { return true, nil }\n\treturn s.getBool("tgBotEnable")'),
    ])

    modify("internal/web/service/tgbot/tgbot.go", [
        ('"github.com/mhsanaei/3x-ui/v3/internal/web/service"',
         '"github.com/mhsanaei/3x-ui/v3/internal/web/service"\n\t"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"'),
        ('tgBotToken, err := t.settingService.GetTgBotToken()\n\tif err != nil || tgBotToken == "" {',
         '''tgBotToken := ""
    if tgminiapp.Enabled() {
        tgBotToken = tgminiapp.BotToken() // Never read the legacy DB token in Vela mode
    } else {
        tgBotToken, err = t.settingService.GetTgBotToken()
    }
    if tgBotToken == "" && err == nil {
        err = fmt.Errorf("Vela Bot token Secret missing or invalid")
    }
\tif err != nil || tgBotToken == "" {'''),
        ('tgBotID, err := t.settingService.GetTgBotChatId()\n\tif err != nil {',
         '''tgBotID := ""
    if tgminiapp.Enabled() {
        // Fail closed before parsing Telegram chat IDs, which normally accepts
        // negative group IDs; Vela requires positive private user IDs only.
        if _, allowlistErr := tgminiapp.AdminUserIDs(); allowlistErr != nil {
            return fmt.Errorf("Vela Bot admin allowlist invalid")
        }
        tgBotID = os.Getenv("XUI_TG_MINIAPP_ADMIN_IDS")
    } else {
        tgBotID, err = t.settingService.GetTgBotChatId()
    }
\tif err != nil {''')
    ])

    # Vela's public source and published image must never include operators'
    # private runtime DB. Separately, block the legacy Bot feature that sends
    # whole DB backups and generated Xray config to Telegram; opt-in certificate
    # alerts are not equivalent to consent to export complete private data.
    modify("internal/web/service/tgbot/notices.go", [
        ('"github.com/mhsanaei/3x-ui/v3/internal/logger"',
         '"github.com/mhsanaei/3x-ui/v3/internal/logger"\n\t"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"'),
        ('func (t *Tgbot) sendBackupFile(chatID int64, data []byte, name, caption string) bool {',
         '''func (t *Tgbot) sendBackupFile(chatID int64, data []byte, name, caption string) bool {
    if tgminiapp.Enabled() { return false } // raw DB and Xray config stay local'''),
    ])

    modify("internal/web/service/tgbot/tgbot_report.go", [
        ('"github.com/mhsanaei/3x-ui/v3/internal/web/service"',
         '"github.com/mhsanaei/3x-ui/v3/internal/web/service"\n\t"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"'),
        ('func (t *Tgbot) SendReport() {',
         '''func (t *Tgbot) SendReport() {
    // Enabling a Mini App must not also opt in to legacy periodic reports.
    if tgminiapp.Enabled() { return }'''),
        ('func (t *Tgbot) SendBackupToAdmins() {',
         '''func (t *Tgbot) SendBackupToAdmins() {
    if tgminiapp.Enabled() { return } // disable automatic and API-triggered exports'''),
    ])

    modify("internal/web/service/tgbot/screen_views.go", [
        ('"github.com/mhsanaei/3x-ui/v3/internal/logger"',
         '"github.com/mhsanaei/3x-ui/v3/internal/logger"\n\t"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"'),
        ('func (t *Tgbot) sendBackupScreen(chatID int64) {',
         '''func (t *Tgbot) sendBackupScreen(chatID int64) {
    if tgminiapp.Enabled() {
        t.sendNotice(chatID, "🔒 Vela 禁止通过 Telegram 传输数据库与 Xray 私密配置。请使用本地 vela backup。")
        return
    }'''),
        ('t.homeRows()...', 't.homeRows(chatID)...'),
    ])

    modify("internal/web/service/tgbot/screen_view.go", [
        ('"github.com/mymmrac/telego"',
         '"github.com/mymmrac/telego"\n\t"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"'),
        ('func (t *Tgbot) homeRows() [][]telego.InlineKeyboardButton {\n\treturn [][]telego.InlineKeyboardButton{',
         '''func (t *Tgbot) homeRows(chatID int64) [][]telego.InlineKeyboardButton {
    rows := [][]telego.InlineKeyboardButton{}
    // WebApp inline buttons are only valid in private chats. Never show
    // this admin entry point in groups, topics or public conversations.
    if chatID > 0 && tgminiapp.AllowedUserID(chatID) {
        if appURL := tgminiapp.MiniAppURL(); appURL != "" {
            rows = append(rows, tu.InlineKeyboardRow(
                tu.InlineKeyboardButton("🚀 打开 Vela").WithWebApp(tu.WebAppInfo(appURL)),
            ))
        }
    }
    rows = append(rows, [][]telego.InlineKeyboardButton{'''),
        ('\t\ttu.InlineKeyboardRow(\n\t\t\tt.btn("tgbot.buttons.refresh", cbHome),\n\t\t),\n\t}\n}',
         '\t\ttu.InlineKeyboardRow(\n\t\t\tt.btn("tgbot.buttons.refresh", cbHome),\n\t\t),\n\t}...)\n    return rows\n}')
        ,('''\tcase "maintenance":
\t\treturn [][]telego.InlineKeyboardButton{
\t\t\ttu.InlineKeyboardRow(t.btn("tgbot.buttons.dbBackup", cbBackup)),
\t\t\ttu.InlineKeyboardRow(t.btn("tgbot.buttons.getBanLogs", cbBanLogs)),
\t\t\ttu.InlineKeyboardRow(t.btn("tgbot.buttons.restartXray", cbRestartXry)),
\t\t\ttu.InlineKeyboardRow(t.btn("tgbot.buttons.ResetAllTraffics", cbResetAll)),
\t\t\thome,
\t\t}''',
          '''\tcase "maintenance":
\t\trows := [][]telego.InlineKeyboardButton{}
\t\tif !tgminiapp.Enabled() {
\t\t\trows = append(rows, tu.InlineKeyboardRow(t.btn("tgbot.buttons.dbBackup", cbBackup)))
\t\t}
\t\treturn append(rows,
\t\t\ttu.InlineKeyboardRow(t.btn("tgbot.buttons.getBanLogs", cbBanLogs)),
\t\t\ttu.InlineKeyboardRow(t.btn("tgbot.buttons.restartXray", cbRestartXry)),
\t\t\ttu.InlineKeyboardRow(t.btn("tgbot.buttons.ResetAllTraffics", cbResetAll)),
\t\t\thome,
\t\t)'''),
    ])


    modify("internal/web/controller/spa.go", [
        ('\tg.GET("/clients", a.panelSPA)',
         '\tg.GET("/clients", a.panelSPA)\n\tg.GET("/certificates", a.panelSPA)'),
    ])

    modify("internal/web/controller/dist.go", [
        ('"github.com/mhsanaei/3x-ui/v3/internal/web/session"',
         '"github.com/mhsanaei/3x-ui/v3/internal/web/session"\n\t"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"'),
        ('if name != "login.html" {', 'if name != "login.html" && name != "miniapp.html" {'),
        ('\tscript += `;</script>`',
         '''    if name == "index.html" && tgminiapp.Enabled() {
        script += `;window.X_UI_TG_MINIAPP_MODE=true`
    }
    script += `;</script>`''')
    ])

    # Keep the PWA files in upstream locations but brand the produced assets as
    # Vela. Never delete original assets or remap upstream protocol endpoints.
    modify("frontend/public/manifest.webmanifest", [
        ('"name": "3x-ui"', '"name": "Vela"'),
        ('"short_name": "3x-ui"', '"short_name": "Vela"'),
        ('"background_color": "#0f172a"', '"background_color": "#091321"'),
        ('"theme_color": "#1677ff"', '"theme_color": "#1768bb"'),
        *[(f'icons/3x-ui-{n}.png', f'icons/vela-{n}.png') for n in (16,24,32,64,192,512)],
    ])
    modify("internal/web/controller/pwa.go", [
        ('var pwaAssets = map[string]pwaAsset{',
         'var pwaAssets = map[string]pwaAsset{\n'+
         ''.join(f'    "icons/vela-{n}.png": {{path: "dist/icons/vela-{n}.png", contentType: "image/png"}},\n' for n in (16,24,32,64,192,512))),
    ])

    modify("frontend/vite.config.js", [
        ("login: path.resolve(import.meta.dirname, 'login.html'),",
         "login: path.resolve(import.meta.dirname, 'login.html'),\n        miniapp: path.resolve(import.meta.dirname, 'miniapp.html'),")
    ])

    modify("frontend/src/routes/panelRoutes.tsx", [
        ('  SettingOutlined,', '  SafetyCertificateOutlined,\n  SettingOutlined,'),
        ("const SettingsPage = lazy(() => import('@/pages/settings/SettingsPage'));",
         "const SettingsPage = lazy(() => import('@/pages/settings/SettingsPage'));\nconst CertificatesPage = lazy(() => import('@/pages/certificates/CertificatesPage'));"),
        ("  { path: '/clients', titleKey: 'menu.clients', icon: TeamOutlined, component: ClientsPage },",
         "  { path: '/clients', titleKey: 'menu.clients', icon: TeamOutlined, component: ClientsPage },\n  { path: '/certificates', titleKey: 'menu.certificates', icon: SafetyCertificateOutlined, component: CertificatesPage },")
    ])

    modify("frontend/src/layouts/AppSidebar.tsx", [
        ("const REPO_URL = 'https://github.com/MHSanaei/3x-ui';",
         "const REPO_URL = 'https://github.com/smgsp6/3x-ui';"),
        ("import './AppSidebar.css';", "import './AppSidebar.css';\nimport velaMark from '@/assets/vela-mark.png';"),
        ("<span className=\"brand-text\">{railCollapsed ? '3X' : '3X-UI'}</span>", "<span className=\"brand-text\"><img src={velaMark} alt=\"\" width={26} height={26} style={{ borderRadius: 7, marginRight: 6, verticalAlign: 'middle' }} />{!railCollapsed && 'Vela'}</span>"),
        ('<span className="drawer-brand">3X-UI</span>', '<span className="drawer-brand">Vela</span>')
    ])

    modify("frontend/src/layouts/PanelLayout.tsx", [
        ("import CommandPalette from '@/components/command-palette/CommandPalette';",
         "import CommandPalette from '@/components/command-palette/CommandPalette';\nimport MiniAppBottomNav from '@/components/miniapp/MiniAppBottomNav';"),
        ('      <CommandPalette />', '      <CommandPalette />\n      <MiniAppBottomNav />')
    ])

    # Translate only navigation labels. Preserve all existing translations.
    for name, label in [("zh-CN.json", "证书管理"), ("en-US.json", "Certificates")]:
        path = repo / "internal/web/translation" / name
        text = path.read_text(encoding="utf-8")
        import json
        object_data = json.loads(text)
        if not isinstance(object_data.get("menu"), dict):
            raise ValueError(f"{path}: unexpected locale format")
        if "certificates" in object_data["menu"]:
            raise ValueError(f"{path}: menu.certificates already present")
        # Preserve the file's original formatting by inserting near a known key.
        match = re.search(r'(^\s*"menu"\s*:\s*\{)', text, re.M)
        if not match:
            raise ValueError(f"{path}: missing menu object")
        text = text[:match.end()] + f'\n    "certificates": "{label}",' + text[match.end():]
        json.loads(text)
        updates[path] = text

    readme_path = repo / "README.md"
    original_readme = readme_path.read_text(encoding="utf-8")
    if "MHSanaei/3x-ui" not in original_readme or "**3X-UI**" not in original_readme:
        raise ValueError("README.md no longer matches the expected upstream version")
    updates[readme_path] = (BUNDLE / "README.md").read_text(encoding="utf-8")

    additions = [
        "internal/web/controller/miniapp.go",
        "internal/web/service/tgminiapp/auth.go",
        "internal/web/service/tgminiapp/auth_test.go",
        "internal/web/service/tgminiapp/certificates.go",
        "internal/web/service/tgminiapp/certificates_test.go",
        "internal/web/service/tgminiapp/certificate_alerts.go",
        "internal/web/service/tgminiapp/certificate_alerts_test.go",
        "internal/web/service/tgminiapp/tls_reloader.go",
        "internal/web/service/tgminiapp/tls_reloader_test.go",
        "frontend/miniapp.html",
        "frontend/src/entries/miniapp.tsx",
        "frontend/src/entries/miniapp.css",
        "frontend/src/pages/certificates/CertificatesPage.tsx",
        "frontend/src/pages/certificates/CertificatesPage.css",
        "frontend/src/components/miniapp/MiniAppBottomNav.tsx",
        "frontend/src/components/miniapp/MiniAppBottomNav.css",
        "frontend/src/assets/vela-mark.png",
        "frontend/src/assets/vela-logo.png",
        "frontend/src/vela-assets.d.ts",
        "frontend/public/icons/vela-16.png",
        "frontend/public/icons/vela-24.png",
        "frontend/public/icons/vela-32.png",
        "frontend/public/icons/vela-64.png",
        "frontend/public/icons/vela-192.png",
        "frontend/public/icons/vela-512.png",
        "deploy/miniapp/compose.override.yml",
        "deploy/miniapp/env.example",
        "docs/telegram-miniapp-phase1.md",
        "deploy/vela/preflight.sh",
        "deploy/vela/security-check.sh",
        "deploy/vela/privacy_audit.py",
        "deploy/vela/git_history_audit.py",
        "docs/vela-deployment.md",
        "deploy/vela/vela",
        "deploy/vela/compose.host.yml",
        "deploy/vela/runtime.env.example",
        "docs/vela-updates.md",
        ".github/workflows/vela-pr-check.yml",
        "docs/RELEASE-GATE.md",
        "docs/PHASE5-CHANGELOG.md",
        "docs/PHASE6-CHANGELOG.md",
        "docs/PHASE7-CHANGELOG.md",
        "docs/RELEASE-SIGNING.md",
        "docs/PHASE7-TEST-REPORT.md",
        "docs/PHASE8-CHANGELOG.md",
        "docs/PHASE8-TEST-REPORT.md",
        "docs/PROJECT-CONTINUITY.md",
        "docs/PHASE9-CHANGELOG.md",
        "docs/PHASE9-TEST-REPORT.md",
        "docs/PHASE10-CHANGELOG.md",
        "docs/PHASE10-TEST-REPORT.md",
        "docs/PHASE11-CHANGELOG.md",
        "docs/PHASE11-TEST-REPORT.md",
        "docs/PHASE12-CHANGELOG.md",
        "docs/PHASE12-TEST-REPORT.md",
        "tests/test_phase12_security_contract.py",
        "tests/test_build_gate_contract.py",
        "tests/test_telegram_data_egress.py",
        "tests/test_image_layer_audit.py",
        "deploy/vela/image_layer_audit.py",
        "tests/test_certificate_contract.py",
        "tests/test_maintenance_cli.py",
        "tests/test_privacy_audit.py",
        "tests/test_git_history_audit.py",
        "tests/test_apply_to_repo.py",
        "brand/BRAND.md",
        "brand/vela-app-512.png",
        "brand/vela-logo-horizontal.png",
    ]
    for name in additions:
        src, dst = BUNDLE / name, repo / name
        ensure_no_symlink_components(dst)
        if src.is_symlink() or not src.is_file():
            raise ValueError(f"missing patch file: {src}")
        if dst.exists() or dst.is_symlink():
            raise ValueError(f"refusing to overwrite existing file or symlink: {dst}")
    # os.replace is only safe after an exclusive, non-following temp creation.
    # Check before writing ANYTHING, including the --check dry run.
    for dst in updates:
        ensure_no_symlink_components(dst)
        tmp = dst.with_name(dst.name + ".vela-tmp")
        if tmp.exists() or tmp.is_symlink():
            raise ValueError(f"unsafe pre-existing patch temporary file: {tmp}")
    print(f"Validated: {len(updates)} modifications + {len(additions)} new files in {repo}")
    if options.check:
        return
    # Roll back partial file-system writes if a copy fails. Keep file modes.
    import stat
    originals = {dst: (dst.read_bytes(), stat.S_IMODE(dst.stat().st_mode)) for dst in updates}
    new_paths = []
    try:
        for dst, content in updates.items():
            tmp = dst.with_name(dst.name + ".vela-tmp")
            flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(tmp, flags, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(tmp, originals[dst][1])
            os.replace(tmp, dst)
        for name in additions:
            dst = repo / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            new_paths.append(dst)  # include partially written destinations in rollback
            shutil.copy2(BUNDLE / name, dst)
    except Exception:
        for dst in updates:
            dst.with_name(dst.name + ".vela-tmp").unlink(missing_ok=True)
        for dst in reversed(new_paths):
            dst.unlink(missing_ok=True)
        for dst, (data, mode) in originals.items():
            dst.write_bytes(data)
            os.chmod(dst, mode)
        raise
    print("Applied to local fork. Run gofmt, Go tests and frontend build before committing.")

if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
