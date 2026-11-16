// Package tgminiapp validates official Telegram Mini App initData.
// It intentionally has no external dependencies and never calls Telegram APIs.
package tgminiapp

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"slices"
	"strconv"
	"strings"
	"time"
)

const MaxAuthAge = 5 * time.Minute

var ErrUnauthorized = errors.New("telegram mini app authentication failed")

type User struct {
	ID int64 `json:"id"`
}

func Enabled() bool {
	return strings.EqualFold(strings.TrimSpace(os.Getenv("XUI_TG_MINIAPP_ENABLED")), "true")
}

// AllowedUserID rejects invalid allowlists as a whole, instead of partially
// permitting users when an operator accidentally mistypes a value.
func AllowedUserID(id int64) bool {
	raw := strings.TrimSpace(os.Getenv("XUI_TG_MINIAPP_ADMIN_IDS"))
	if id <= 0 || raw == "" || len(raw) > 1024 {
		return false
	}
	parts := strings.Split(raw, ",")
	if len(parts) > 32 {
		return false
	}
	seen := make(map[int64]struct{}, len(parts))
	authorized := false
	for _, item := range parts {
		part := strings.TrimSpace(item)
		n, err := strconv.ParseInt(part, 10, 64)
		if err != nil || n <= 0 || strconv.FormatInt(n, 10) != part {
			return false
		}
		if _, duplicate := seen[n]; duplicate {
			return false
		}
		seen[n] = struct{}{}
		authorized = authorized || (n == id)
	}
	return authorized
}

// Verify checks the HMAC with the bot token, the issuance time, and the user.
// initDataUnsafe and client-supplied user IDs are NEVER trusted.
func Verify(rawInitData, botToken string, now time.Time) (User, error) {
	denied := func() (User, error) { return User{}, ErrUnauthorized }
	if len(rawInitData) == 0 || len(rawInitData) > 16*1024 || botToken == "" {
		return denied()
	}
	params, err := url.ParseQuery(rawInitData)
	if err != nil {
		return denied()
	}
	for _, values := range params {
		if len(values) != 1 {
			return denied()
		} // reject duplicate-key ambiguities
	}
	providedHash := params.Get("hash")
	if len(providedHash) != 64 {
		return denied()
	}
	actual, err := hex.DecodeString(providedHash)
	if err != nil || len(actual) != sha256.Size {
		return denied()
	}

	keys := make([]string, 0, len(params))
	for key := range params {
		if key != "hash" && key != "signature" {
			keys = append(keys, key)
		}
	}
	slices.Sort(keys)
	check := make([]string, 0, len(keys))
	for _, key := range keys {
		check = append(check, key+"="+params.Get(key))
	}
	secretMAC := hmac.New(sha256.New, []byte("WebAppData"))
	_, _ = secretMAC.Write([]byte(botToken))
	checkMAC := hmac.New(sha256.New, secretMAC.Sum(nil))
	_, _ = checkMAC.Write([]byte(strings.Join(check, "\n")))
	if !hmac.Equal(actual, checkMAC.Sum(nil)) {
		return denied()
	}

	authDate, err := strconv.ParseInt(params.Get("auth_date"), 10, 64)
	if err != nil || authDate <= 0 {
		return denied()
	}
	age := now.Sub(time.Unix(authDate, 0))
	if age > MaxAuthAge || age < -time.Minute {
		return denied()
	}
	// Group/ channel launches are not an administrative entry point. For
	// private-chat WebApp buttons this field is normally absent.
	if chatType := params.Get("chat_type"); chatType != "" && chatType != "private" && chatType != "sender" {
		return denied()
	}
	if params.Get("chat") != "" {
		return denied()
	}
	var user User
	if err := json.Unmarshal([]byte(params.Get("user")), &user); err != nil || user.ID <= 0 {
		return denied()
	}
	if !AllowedUserID(user.ID) {
		return denied()
	}
	return user, nil
}

// MiniAppURL returns the HTTPS launch URL only when explicitly configured.
// Never expose this in group chats; Telegram Mini App WebApp buttons require private chats.
func MiniAppURL() string {
	if !Enabled() {
		return ""
	}
	raw := strings.TrimSpace(os.Getenv("XUI_TG_MINIAPP_URL"))
	if raw == "" || len(raw) > 2048 {
		return ""
	}
	u, err := url.Parse(raw)
	if err != nil || u.Scheme != "https" || u.Hostname() == "" || u.User != nil || u.RawQuery != "" || u.Fragment != "" || u.Opaque != "" {
		return ""
	}
	if strings.ContainsAny(u.Host, "\r\n\t ") {
		return ""
	}
	// Fail closed even if an operator bypasses the installer. An unusable
	// localhost/IP/example URL must never become a Bot WebApp button.
	host := strings.ToLower(u.Hostname())
	if net.ParseIP(host) != nil || !strings.Contains(host, ".") ||
		strings.HasPrefix(host, ".") || strings.HasSuffix(host, ".") ||
		strings.Contains(host, "..") {
		return ""
	}
	for _, suffix := range []string{".localhost", ".local", ".test", ".invalid", ".example",
		"example.com", "example.net", "example.org"} {
		if host == strings.TrimPrefix(suffix, ".") || strings.HasSuffix(host, "."+strings.TrimPrefix(suffix, ".")) {
			return ""
		}
	}
	// Reject non-canonical/shortened numeric IPv4 aliases (e.g. 127.1)
	// and malformed DNS labels. Some URL clients resolve those to loopback
	// even though net.ParseIP does not consider them canonical IP addresses.
	labels := strings.Split(host, ".")
	if len(host) > 253 || len(labels) < 2 {
		return ""
	}
	for _, label := range labels {
		if len(label) < 1 || len(label) > 63 || label[0] == '-' || label[len(label)-1] == '-' {
			return ""
		}
		for _, ch := range label {
			if !(ch >= 'a' && ch <= 'z') && !(ch >= '0' && ch <= '9') && ch != '-' {
				return ""
			}
		}
	}
	lastLabel := labels[len(labels)-1]
	numericSuffix := true
	for _, ch := range lastLabel {
		if ch < '0' || ch > '9' {
			numericSuffix = false
			break
		}
	}
	if numericSuffix {
		return ""
	}
	if port := u.Port(); port != "" {
		value, err := strconv.Atoi(port)
		if err != nil || value < 1 || value > 65535 {
			return ""
		}
	}
	return u.String()
}

// BotToken reads ONLY a local Docker-secret file. Vela deliberately does NOT
// accept bot tokens from process environment variables (docker inspect leaks
// them to anyone with Docker access). File errors fail closed.
func BotToken() string {
	file := strings.TrimSpace(os.Getenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE"))
	if file == "" {
		return ""
	}
	// The Secret's immediate directory must not be writable by other users;
	// an attacker who can replace path components could redirect the bot.
	parent, err := os.Lstat(filepath.Dir(file))
	if err != nil || !parent.IsDir() || parent.Mode().Perm()&0022 != 0 {
		return ""
	}
	info, err := os.Lstat(file)
	if err != nil || !info.Mode().IsRegular() || info.Size() < 1 || info.Size() > 512 {
		return ""
	}
	f, err := os.Open(file)
	if err != nil {
		return ""
	}
	defer f.Close()
	// Enforce permissions in the Go backend even when the installer was bypassed.
	// Compare the opened inode against Lstat to reject a file/symlink swap.
	opened, err := f.Stat()
	if err != nil || !opened.Mode().IsRegular() || !os.SameFile(info, opened) ||
		opened.Size() < 1 || opened.Size() > 512 || opened.Mode().Perm()&0077 != 0 {
		return ""
	}
	data, err := io.ReadAll(io.LimitReader(f, 513))
	if err != nil || len(data) > 512 {
		return ""
	}
	// Secret may end in one newline, but must not contain any other whitespace
	// or control characters that could be passed to the Telegram client.
	token := strings.TrimSuffix(string(data), "\n")
	// Telegram credentials are an ASCII numeric bot ID, a colon, and a
	// URL-safe secret. Reject control characters, path separators and any
	// other unexpected byte before constructing /bot<TOKEN>/ HTTP URLs.
	id, secret, ok := strings.Cut(token, ":")
	if !ok || id == "" || secret == "" {
		return ""
	}
	for _, c := range id {
		if c < '0' || c > '9' {
			return ""
		}
	}
	for _, c := range secret {
		if !(c >= 'a' && c <= 'z') && !(c >= 'A' && c <= 'Z') &&
			!(c >= '0' && c <= '9') && c != '-' && c != '_' {
			return ""
		}
	}
	return token
}
