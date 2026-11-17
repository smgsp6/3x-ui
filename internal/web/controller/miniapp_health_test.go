package controller

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"

	"github.com/gin-gonic/gin"
)

// A broken Telegram admin allowlist must fail the deployment health gate.
// Otherwise image upgrades can appear healthy while nobody can sign in.
func TestVelaHealthRejectsMalformedAdministratorAllowlist(t *testing.T) {
	gin.SetMode(gin.TestMode)
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	t.Setenv("XUI_TG_MINIAPP_URL", "https://ci.vela-test-domain.org/")
	secret := filepath.Join(t.TempDir(), "vela_bot_token")
	if err := os.WriteFile(secret, []byte("12345:synthetic_token"), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", secret)
	for _, raw := range []string{
		"", "0", "123,123", "123,not_a_number",
		"000123", "-1001",
	} {
		t.Run("bad_allowlist", func(t *testing.T) {
			t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", raw)
			router := gin.New()
			NewMiniAppController(router.Group("/"))
			resp := httptest.NewRecorder()
			req := httptest.NewRequest(http.MethodGet, "/tg-miniapp/health", nil)
			router.ServeHTTP(resp, req)
			if resp.Code != http.StatusServiceUnavailable {
				t.Fatalf("unusable Mini App reported ready (HTTP %d)", resp.Code)
			}
		})
	}
}

 
func TestVelaHealthRejectsUnusableMiniAppLaunchURL(t *testing.T) {
	gin.SetMode(gin.TestMode)
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "12345")
	secret := filepath.Join(t.TempDir(), "vela_bot_token")
	if err := os.WriteFile(secret, []byte("12345:synthetic_token"), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", secret)
	for _, raw := range []string{
		"", "http://ci.vela-test-domain.org/", "https://localhost:2053/",
		"https://127.0.0.1:2053/", "https://example.com/",
	} {
		t.Run("invalid_url", func(t *testing.T) {
			t.Setenv("XUI_TG_MINIAPP_URL", raw)
			router := gin.New()
			NewMiniAppController(router.Group("/"))
			resp := httptest.NewRecorder()
			req := httptest.NewRequest(http.MethodGet, "/tg-miniapp/health", nil)
			router.ServeHTTP(resp, req)
			if resp.Code != http.StatusServiceUnavailable {
				t.Fatalf("invalid Mini App launch URL reported ready (HTTP %d)", resp.Code)
			}
		})
	}
}
