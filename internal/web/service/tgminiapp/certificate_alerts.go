package tgminiapp

// Certificate expiry alerts are an opt-in, local-only scheduler component.
// The only outbound payload goes to the explicitly configured private Telegram
// admin account(s). It deliberately contains NO hostnames, IPs or file paths.
// The bot token never appears in alert state or logs.

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"
)

const defaultAlertStateFile = "/etc/x-ui/vela-cert-alerts.json"

var ErrAlertStateUnsafe = errors.New("Vela certificate alert state is unavailable or unsafe")

// CertAlertsEnabled is false unless the operator explicitly opts in. Telegram
// will receive only a generic certificate purpose, expiry class and days left.
func CertAlertsEnabled() bool {
	return Enabled() && strings.EqualFold(strings.TrimSpace(os.Getenv("XUI_TG_CERT_ALERT_ENABLED")), "true")
}

// AdminUserIDs parses the FULL Telegram numeric allowlist fail-closed. Chat IDs
// and forum topics are intentionally unsupported for security notifications.
func AdminUserIDs() ([]int64, error) {
	raw := strings.TrimSpace(os.Getenv("XUI_TG_MINIAPP_ADMIN_IDS"))
	if raw == "" {
		return nil, ErrUnauthorized
	}
	seen := make(map[int64]bool)
	var ids []int64
	for _, item := range strings.Split(raw, ",") {
		v := strings.TrimSpace(item)
		if v == "" || strings.ContainsAny(v, ":+-") {
			return nil, ErrUnauthorized
		}
		id, err := strconv.ParseInt(v, 10, 64)
		if err != nil || id <= 0 {
			return nil, ErrUnauthorized
		}
		if !seen[id] {
			ids = append(ids, id)
			seen[id] = true
		}
	}
	return ids, nil
}

// certificateMilestone determines a finite set of alerts per certificate,
// rather than sending a reminder every day. Each milestone is sent at most
// once per certificate and recipient (including across panel restarts).
func certificateMilestone(c CertificateStatus, now time.Time) string {
	if c.Status == "unconfigured" || c.Status == "valid" {
		return ""
	}
	if c.Status == "invalid" {
		return "invalid"
	}
	if c.Status == "expired" {
		return "expired"
	}
	if c.Status != "expiring" || c.ValidUntil == nil {
		return ""
	}
	days := int(c.ValidUntil.Sub(now).Hours() / 24)
	if days < 0 {
		return "expired"
	}
	for _, n := range []int{1, 3, 7, 14, 30} {
		if days <= n {
			return fmt.Sprintf("%dd", n)
		}
	}
	return ""
}

func certificatePurpose(purpose string) string {
	switch purpose {
	case "panel":
		return "管理面板"
	case "subscription":
		return "订阅服务"
	default:
		return "TLS"
	}
}

func certificateAlertMessage(c CertificateStatus, milestone string) string {
	label := certificatePurpose(c.Purpose)
	switch milestone {
	case "invalid":
		return "🔐 Vela 证书提醒\n" + label + "证书配置异常，请登录 Vela → 证书管理检查。"
	case "expired":
		return "🔐 Vela 证书提醒\n" + label + "证书已过期，请尽快检查。"
	default:
		// DaysRemaining is derived from certificate validity, not from a user
		// supplied message. Never echo a hostname, file path, or cert issuer.
		days := c.DaysRemaining
		if days < 0 {
			days = 0
		}
		return "🔐 Vela 证书提醒\n" + label + "证书将在约 " + strconv.Itoa(days) + " 天后到期，请登录 Vela → 证书管理检查。"
	}
}

type alertState struct {
	Sent map[string]int64 `json:"sent"`
}

func alertStatePath() string {
	if s := strings.TrimSpace(os.Getenv("XUI_TG_CERT_ALERT_STATE_FILE")); s != "" {
		return s
	}
	return defaultAlertStateFile
}

func checkAlertStatePath(path string) error {
	if !filepath.IsAbs(path) || filepath.Base(path) != "vela-cert-alerts.json" {
		return ErrAlertStateUnsafe
	}
	// Only allow a regular state file inside a trusted, non-symlink directory.
	// 0755 is accepted for /etc/x-ui; the state file itself is mode 0600.
	parent := filepath.Dir(path)
	dir, err := os.Lstat(parent)
	if err != nil || !dir.IsDir() || dir.Mode().Perm()&0022 != 0 {
		return ErrAlertStateUnsafe
	}
	file, err := os.Lstat(path)
	if err == nil && (!file.Mode().IsRegular() || file.Mode().Perm()&0077 != 0 || file.Size() > 1<<20) {
		return ErrAlertStateUnsafe
	}
	if err != nil && !os.IsNotExist(err) {
		return ErrAlertStateUnsafe
	}
	return nil
}

func loadAlertState(path string) (alertState, error) {
	state := alertState{Sent: make(map[string]int64)}
	if err := checkAlertStatePath(path); err != nil {
		return state, err
	}
	data, err := os.ReadFile(path)
	if os.IsNotExist(err) {
		return state, nil
	}
	if err != nil || len(data) > 1<<20 || len(data) == 0 {
		return state, ErrAlertStateUnsafe
	}
	if err := json.Unmarshal(data, &state); err != nil || state.Sent == nil || len(state.Sent) > 10000 {
		return alertState{}, ErrAlertStateUnsafe
	}
	return state, nil
}

func saveAlertState(path string, state alertState) error {
	if err := checkAlertStatePath(path); err != nil {
		return err
	}
	content, err := json.Marshal(state)
	if err != nil || len(content) > 1<<20 {
		return ErrAlertStateUnsafe
	}
	// Atomic replacement; O_EXCL prevents the tmp file being a symlink. The
	// fixed filename and trusted parent directory prevent path redirection.
	f, err := os.CreateTemp(filepath.Dir(path), ".vela-cert-alerts-*")
	if err != nil {
		return ErrAlertStateUnsafe
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	if _, err = f.Write(content); err != nil {
		f.Close()
		return ErrAlertStateUnsafe
	}
	if err = f.Sync(); err != nil {
		f.Close()
		return ErrAlertStateUnsafe
	}
	if err = f.Close(); err != nil {
		return ErrAlertStateUnsafe
	}
	if err = os.Rename(tmp, path); err != nil {
		return ErrAlertStateUnsafe
	}
	return nil
}

func alertKey(userID int64, c CertificateStatus, milestone string) string {
	// Nothing identifying is stored in the on-disk state (only a SHA256 key).
	expires := "unknown"
	if c.ValidUntil != nil {
		expires = strconv.FormatInt(c.ValidUntil.Unix(), 10)
	}
	sum := sha256.Sum256([]byte(fmt.Sprintf("vela:cert:v1|%d|%s|%s|%s", userID, c.Purpose, expires, milestone)))
	return hex.EncodeToString(sum[:])
}

// SendCertificateAlerts is called by the server's daily cron job. Sender must
// deliver to a private Telegram ID and return true only on successful send.
// If state storage is missing/corrupt/unsafe, NOTHING is sent: fail closed.
// Calls must not overlap; the server's cron chain uses SkipIfStillRunning.
func SendCertificateAlerts(now time.Time, certs []CertificateStatus, sender func(chatID int64, text string) bool) (int, error) {
	if !CertAlertsEnabled() {
		return 0, nil
	}
	if sender == nil {
		return 0, ErrAlertStateUnsafe
	}
	ids, err := AdminUserIDs()
	if err != nil {
		return 0, err
	}
	path := alertStatePath()
	state, err := loadAlertState(path)
	if err != nil {
		return 0, err
	}
	count := 0
	for _, c := range certs {
		milestone := certificateMilestone(c, now)
		if milestone == "" {
			continue
		}
		for _, id := range ids {
			key := alertKey(id, c, milestone)
			if state.Sent[key] != 0 {
				continue
			}
			if !sender(id, certificateAlertMessage(c, milestone)) {
				continue // retry next scheduled check, never record failure
			}
			state.Sent[key] = now.Unix()
			// Persist per delivery. If the filesystem fails, abort rather than
			// risk flooding all recipients with duplicates on restart.
			if err := saveAlertState(path, state); err != nil {
				return count, err
			}
			count++
		}
	}
	return count, nil
}
