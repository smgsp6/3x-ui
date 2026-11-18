package tgminiapp

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"net/url"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"
)

func signedData(values url.Values, token string) string {
	keys := make([]string, 0, len(values))
	for k := range values {
		if k != "hash" {
			keys = append(keys, k)
		}
	}
	sort.Strings(keys)
	var parts []string
	for _, k := range keys {
		parts = append(parts, k+"="+values.Get(k))
	}
	a := hmac.New(sha256.New, []byte("WebAppData"))
	a.Write([]byte(token))
	b := hmac.New(sha256.New, a.Sum(nil))
	b.Write([]byte(strings.Join(parts, "\n")))
	values.Set("hash", hex.EncodeToString(b.Sum(nil)))
	return values.Encode()
}

func TestVerify(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1234567")
	now := time.Unix(1794672000, 0)
	mk := func(id, date string) url.Values {
		return url.Values{
			"auth_date": {date}, "user": {`{"id":` + id + `,"first_name":"Example"}`}, "query_id": {"AAA"},
		}
	}
	valid := signedData(mk("1234567", "1794672000"), "12345:secret")
	user, err := Verify(valid, "12345:secret", now)
	if err != nil || user.ID != 1234567 {
		t.Fatalf("valid: %+v, %v", user, err)
	}
	modern := mk("1234567", "1794672000")
	modern.Set("signature", "synthetic-ed25519-field")
	signedModern := signedData(modern, "12345:secret")
	if _, err := Verify(signedModern, "12345:secret", now); err != nil {
		t.Fatal("valid HMAC containing Telegram's signature field was rejected")
	}
	tests := []struct {
		name, raw, token string
		at               time.Time
	}{
		{"wrong token", valid, "bad:token", now},
		{"changed signature", strings.Replace(signedModern, "synthetic-ed25519-field", "changed-field", 1), "12345:secret", now},
		{"ambiguous canonical field", signedData(func() url.Values {
			v := mk("1234567", "1794672000")
			v.Set("query_id", "one\ntwo=three")
			return v
		}(), "12345:secret"), "12345:secret", now},
		{"changed user", strings.Replace(valid, "1234567", "7654321", 1), "12345:secret", now},
		{"expired", valid, "12345:secret", now.Add(6 * time.Minute)},
		{"future", valid, "12345:secret", now.Add(-2 * time.Minute)},
		{"invalid user", signedData(mk("22222", "1794672000"), "12345:secret"), "12345:secret", now},
		{"group launch", signedData(func() url.Values { v := mk("1234567", "1794672000"); v.Set("chat_type", "group"); return v }(), "12345:secret"), "12345:secret", now},
		{"chat payload", signedData(func() url.Values { v := mk("1234567", "1794672000"); v.Set("chat", `{"id":123}`); return v }(), "12345:secret"), "12345:secret", now},
		{"duplicate keys", valid + "&auth_date=1794672000", "12345:secret", now},
		{"no hash", mk("1234567", "1794672000").Encode(), "12345:secret", now},
		{"empty token", valid, "", now},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if _, err := Verify(tt.raw, tt.token, tt.at); err == nil {
				t.Fatal("authentication must fail")
			}
		})
	}
}

func TestInvalidAllowlistFailsClosed(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1234567,not_a_number")
	if AllowedUserID(1234567) {
		t.Fatal("malformed allowlist must deny")
	}
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "")
	if AllowedUserID(1234567) {
		t.Fatal("empty allowlist must deny")
	}
}

func TestMiniAppURL(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	for _, tt := range []struct {
		raw  string
		good bool
	}{
		{"https://admin.vela-ci.org/", true},
		{"https://admin.vela-ci.org:8443/panel/", true},
		{"https://vela.example.test/", false},
		{"https://vela.example.com/", false},
		{"https://panel.example.net/", false},
		{"https://example.org/", false},
		{"https://localhost/", false},
		{"https://127.0.0.1/", false},
		{"https://127.1/", false},
		{"https://127.0.1/", false},
		{"https://0x7f.0.0.1/", false},
		{"https://panel.123/", false},
		{"https://-panel.vela-ci.org/", false},
		{"https://panel-.vela-ci.org/", false},
		{"https://panel..vela-ci.org/", false},
		{"https://panel.vela-ci.org./", false},
		{"https://admin.vela-ci.org:99999/", false},
		{"https://admin.vela-ci.org:0/", false},
		{"http://vela.example.test/", false},
		{"https://admin:pass@vela.example.test/", false},
		{"https://vela.example.test/?token=secret", false},
		{"https://vela.example.test/#section", false},
		{"javascript:alert(1)", false},
		{"", false},
	} {
		t.Setenv("XUI_TG_MINIAPP_URL", tt.raw)
		got := MiniAppURL()
		if (got != "") != tt.good {
			t.Errorf("url %q: got %q good=%v", tt.raw, got, tt.good)
		}
	}
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "false")
	t.Setenv("XUI_TG_MINIAPP_URL", "https://vela.example.test/")
	if got := MiniAppURL(); got != "" {
		t.Fatal("disabled Mini App URL must be empty")
	}
}

func TestTokenRequiresSecretFileAndRejectsSymlinks(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN", "env-token-must-not-be-used")
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", "")
	if BotToken() != "" {
		t.Fatal("token from environment must never authenticate")
	}
	dir := t.TempDir()
	file := filepath.Join(dir, "real-token")
	if err := os.WriteFile(file, []byte("12345:abc"), 0600); err != nil {
		t.Fatal(err)
	}
	link := filepath.Join(dir, "symlink-token")
	if err := os.Symlink(file, link); err != nil {
		t.Fatal(err)
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", link)
	if BotToken() != "" {
		t.Fatal("symlink token files must be denied")
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", file)
	if err := os.WriteFile(file, make([]byte, 513), 0600); err != nil {
		t.Fatal(err)
	}
	if BotToken() != "" {
		t.Fatal("oversized token files must be denied")
	}
}

func TestBotTokenRejectsSymlinkedPathAncestors(t *testing.T) {
	dir := t.TempDir()
	secrets := filepath.Join(dir, "secrets")
	if err := os.Mkdir(secrets, 0700); err != nil {
		t.Fatal(err)
	}
	secretFile := filepath.Join(secrets, "vela_bot_token")
	if err := os.WriteFile(secretFile, []byte("12345:fixture"), 0600); err != nil {
		t.Fatal(err)
	}
	alias := filepath.Join(dir, "secret-alias")
	if err := os.Symlink(secrets, alias); err != nil {
		t.Fatal(err)
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", filepath.Join(alias, "vela_bot_token"))
	if token := BotToken(); token != "" {
		t.Fatal("Bot Token reader followed a symlinked parent directory")
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", secretFile)
	if token := BotToken(); token != "12345:fixture" {
		t.Fatal("regular Secret path was unexpectedly rejected")
	}
	// Do not accept ambiguous relative and traversal spellings.
	for _, path := range []string{
		filepath.Join("secrets", "vela_bot_token"),
		secrets + "/../secrets/vela_bot_token",
	} {
		t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", path)
		if token := BotToken(); token != "" {
			t.Fatal("unsafe Docker Secret path accepted")
		}
	}
}

func TestBotTokenRejectsWritableSecretDirectory(t *testing.T) {
	dir := filepath.Join(t.TempDir(), "unsafe")
	if err := os.Mkdir(dir, 0700); err != nil {
		t.Fatal(err)
	}
	file := filepath.Join(dir, "bot_token")
	if err := os.WriteFile(file, []byte("12345:sample"), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", file)
	if err := os.Chmod(dir, 0777); err != nil {
		t.Fatal(err)
	}
	if BotToken() != "" {
		t.Fatal("group/world writable Secret directory accepted")
	}
	if err := os.Chmod(dir, 0700); err != nil {
		t.Fatal(err)
	}
	if BotToken() != "12345:sample" {
		t.Fatal("secure Secret directory should be accepted")
	}
}

func TestBotTokenRejectsLoosePermissions(t *testing.T) {
	file := filepath.Join(t.TempDir(), "token")
	if err := os.WriteFile(file, []byte("12345:sample"), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", file)
	for _, mode := range []os.FileMode{0644, 0660, 0604} {
		if err := os.Chmod(file, mode); err != nil {
			t.Fatal(err)
		}
		if BotToken() != "" {
			t.Fatalf("insecure file mode %o accepted", mode)
		}
	}
	if err := os.Chmod(file, 0600); err != nil {
		t.Fatal(err)
	}
	for _, raw := range []string{"12345:one\n12345:two", "12345:bad token", "12345:bad\x00token"} {
		if err := os.WriteFile(file, []byte(raw), 0600); err != nil {
			t.Fatal(err)
		}
		if BotToken() != "" {
			t.Fatal("multiline or control-character secret accepted")
		}
	}
	if err := os.WriteFile(file, []byte("12345:valid\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if got := BotToken(); got != "12345:valid" {
		t.Fatal("single newline should work")
	}
}

func TestBotTokenSecretFile(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN", "ENV_TOKEN_SHOULD_NOT_WIN")
	path := filepath.Join(t.TempDir(), "bot_token")
	if err := os.WriteFile(path, []byte("12345:secret-token\n"), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", path)
	if got := BotToken(); got != "12345:secret-token" {
		t.Fatalf("file credential not loaded")
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", path+".absent")
	if got := BotToken(); got != "" {
		t.Fatal("missing file must fail closed")
	}
}

// A malformed token must not be interpolated into /bot<TOKEN>/ requests.
func TestBotTokenRejectsMalformedBotIdentifiers(t *testing.T) {
	file := filepath.Join(t.TempDir(), "token")
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", file)
	for _, raw := range []string{
		"0:secret", "001:secret", "not-id:secret", "123:bad/secret",
		"123:bad?secret", "123:bad:extra", "123:", ":secret",
		"9223372036854775808:secret", "123:secret\r", "123:token\xff",
	} {
		if err := os.WriteFile(file, []byte(raw), 0600); err != nil {
			t.Fatal(err)
		}
		if token := BotToken(); token != "" {
			t.Fatal("malformed Telegram Bot Token accepted")
		}
	}
	for _, raw := range []string{"123:valid_Secret-09", "123:valid_Secret-09\n"} {
		if err := os.WriteFile(file, []byte(raw), 0600); err != nil {
			t.Fatal(err)
		}
		if token := BotToken(); token != "123:valid_Secret-09" {
			t.Fatal("valid Telegram Bot Token was rejected")
		}
	}
}

func TestAdminAllowlistRejectsAmbiguityAndOverCapacity(t *testing.T) {
	for _, value := range []string{
		"1234567,1234567",
		"01234567",
		"1234567,0",
		"1234567,",
		strings.Repeat("1234567,", 33) + "1234568",
		strings.Repeat("7", 1100),
	} {
		t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", value)
		if AllowedUserID(1234567) {
			t.Fatal("invalid allowlist granted Mini App admin access")
		}
		if _, err := AdminUserIDs(); err == nil {
			t.Fatal("invalid allowlist accepted for Telegram Bot receiver")
		}
	}
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1234567,7654321")
	if !AllowedUserID(1234567) || !AllowedUserID(7654321) {
		t.Fatal("valid multi-admin allowlist rejected")
	}
	if ids, err := AdminUserIDs(); err != nil || len(ids) != 2 {
		t.Fatal("Bot receiver and session allowlist parsing disagree")
	}
}
