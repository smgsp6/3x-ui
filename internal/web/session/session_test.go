package session

import (
	"net/http"
	"os"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"github.com/mhsanaei/3x-ui/v3/internal/database"
	"github.com/mhsanaei/3x-ui/v3/internal/database/dbtest"
	"github.com/mhsanaei/3x-ui/v3/internal/database/model"

	"github.com/gin-contrib/sessions"
	"github.com/gin-contrib/sessions/cookie"
	"github.com/gin-gonic/gin"
)

func TestSetLoginUserStoresOnlyUserID(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(sessions.Sessions(sessionCookieName, cookie.NewStore([]byte("01234567890123456789012345678901"))))
	router.GET("/", func(c *gin.Context) {
		if err := SetLoginUser(c, &model.User{Id: 7, Username: "admin", Password: "hash"}); err != nil {
			t.Fatal(err)
		}
		got := sessions.Default(c).Get(loginUserKey)
		if got != 7 {
			t.Fatalf("stored session payload = %#v, want user id only", got)
		}
		c.Status(http.StatusNoContent)
	})

	rec := httptest.NewRecorder()
	req := httptest.NewRequest(http.MethodGet, "/", nil)
	router.ServeHTTP(rec, req)
	if rec.Code != http.StatusNoContent {
		t.Fatalf("status = %d, want %d", rec.Code, http.StatusNoContent)
	}
}

func TestSessionUserIDSupportsLegacyUserPayload(t *testing.T) {
	id, ok := sessionUserID(model.User{Id: 11, Username: "admin", Password: "hash"})
	if !ok || id != 11 {
		t.Fatalf("legacy session payload resolved to (%d, %v), want (11, true)", id, ok)
	}
	id, ok = sessionUserID(&model.User{Id: 12, Username: "admin", Password: "hash"})
	if !ok || id != 12 {
		t.Fatalf("legacy pointer session payload resolved to (%d, %v), want (12, true)", id, ok)
	}
}

// Anyone can fetch an anonymous session with its CSRF token and plant that cookie in a
// browser from a sibling host; the token must not survive the login it was planted for.
func TestSetLoginUserReplacesThePreLoginCSRFToken(t *testing.T) {
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(sessions.Sessions(sessionCookieName, cookie.NewStore([]byte("01234567890123456789012345678901"))))
	var planted, afterLogin string
	router.GET("/csrf", func(c *gin.Context) {
		planted, _ = EnsureCSRFToken(c)
		c.Status(http.StatusNoContent)
	})
	router.GET("/login", func(c *gin.Context) {
		if err := SetLoginUser(c, &model.User{Id: 7}); err != nil {
			t.Fatal(err)
		}
		afterLogin, _ = EnsureCSRFToken(c)
		c.Status(http.StatusNoContent)
	})
	first := httptest.NewRecorder()
	router.ServeHTTP(first, httptest.NewRequest(http.MethodGet, "/csrf", nil))
	req := httptest.NewRequest(http.MethodGet, "/login", nil)
	for _, cookie := range first.Result().Cookies() {
		req.AddCookie(cookie)
	}
	router.ServeHTTP(httptest.NewRecorder(), req)
	if planted == "" || afterLogin == "" || afterLogin == planted {
		t.Fatalf("CSRF token before login %q, after login %q; want a fresh token", planted, afterLogin)
	}
}

 // TestMiniAppRevocationCannotResurrectOldCookies verifies actual signed Gin
 // cookies and the migrated SQLite admin. All identities and state are local.
func TestMiniAppRevocationCannotResurrectOldCookies(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	configureMiniAppTestBotToken(t)
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1001")
	dbtest.InitDB(t, filepath.Join(t.TempDir(), "x-ui.db"))

	var admin model.User
	if err := database.GetDB().First(&admin).Error; err != nil {
		t.Fatal(err)
	}
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(sessions.Sessions(sessionCookieName, cookie.NewStore([]byte("01234567890123456789012345678901"))))
	router.GET("/login", func(c *gin.Context) {
		if err := SetTelegramMiniAppLoginUser(c, &admin, 1001); err != nil {
			c.Status(http.StatusForbidden)
			return
		}
		c.Status(http.StatusNoContent)
	})
	router.GET("/protected", func(c *gin.Context) {
		if IsLogin(c) {
			c.Status(http.StatusNoContent)
		} else {
			c.Status(http.StatusUnauthorized)
		}
	})
	router.GET("/rotate", func(c *gin.Context) {
		if err := SetLoginUser(c, &admin); err != nil {
			c.Status(http.StatusForbidden)
			return
		}
		c.Status(http.StatusNoContent)
	})
	router.GET("/logout", func(c *gin.Context) {
		if err := ClearSession(c); err != nil {
			c.Status(http.StatusInternalServerError)
			return
		}
		c.Status(http.StatusNoContent)
	})
	request := func(path string, sessionCookie *http.Cookie) (*httptest.ResponseRecorder, *http.Cookie) {
		t.Helper()
		req := httptest.NewRequest(http.MethodGet, path, nil)
		if sessionCookie != nil {
			req.AddCookie(sessionCookie)
		}
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, req)
		for _, c := range rec.Result().Cookies() {
			if c.Name == sessionCookieName {
				return rec, c
			}
		}
		return rec, nil
	}
	checkStatus := func(want int, rec *httptest.ResponseRecorder) {
		t.Helper()
		if rec.Code != want {
			t.Fatalf("HTTP status = %d, want %d", rec.Code, want)
		}
	}

	login, originalCookie := request("/login", nil)
	checkStatus(http.StatusNoContent, login)
	if originalCookie == nil {
		t.Fatal("signed admin session cookie was not set")
	}
	authorized, _ := request("/protected", originalCookie)
	checkStatus(http.StatusNoContent, authorized)

	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1002")
	revoked, _ := request("/protected", originalCookie)
	checkStatus(http.StatusUnauthorized, revoked)

	// Even replaying a copy of the original signed cookie must not work
	// after an observed allowlist change has rolled the process nonce.
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1001")
	resurrected, _ := request("/protected", originalCookie)
	checkStatus(http.StatusUnauthorized, resurrected)

	fresh, freshCookie := request("/login", nil)
	checkStatus(http.StatusNoContent, fresh)
	if freshCookie == nil {
		t.Fatal("fresh login after reauthorization did not set a cookie")
	}
	rotated, rotatedCookie := request("/rotate", freshCookie)
	checkStatus(http.StatusNoContent, rotated)
	if rotatedCookie == nil {
		t.Fatal("credential rotation lost the Mini App session")
	}
	allowed, _ := request("/protected", rotatedCookie)
	checkStatus(http.StatusNoContent, allowed)

	// Original signed cookie must not regain its privilege after session
	// rotation, even if it was captured before the new cookie was delivered.
	preRotationReplay, _ := request("/protected", freshCookie)
	checkStatus(http.StatusUnauthorized, preRotationReplay)
	loggedOut, _ := request("/logout", rotatedCookie)
	checkStatus(http.StatusNoContent, loggedOut)
	// Replay the exact original signed cookie, not the browser's deletion
	// cookie. A signed client-side store alone cannot enforce this.
	stolenCookieReplay, _ := request("/protected", rotatedCookie)
	checkStatus(http.StatusUnauthorized, stolenCookieReplay)
}

func TestMiniAppIdentityNeverTrustsScopedAPITokenOrForgedSessionField(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	configureMiniAppTestBotToken(t)
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1001")
	dbtest.InitDB(t, filepath.Join(t.TempDir(), "x-ui.db"))

	var admin model.User
	if err := database.GetDB().First(&admin).Error; err != nil {
		t.Fatal(err)
	}
	gin.SetMode(gin.TestMode)
	router := gin.New()
	router.Use(sessions.Sessions(sessionCookieName, cookie.NewStore([]byte("01234567890123456789012345678901"))))
	router.GET("/login", func(c *gin.Context) {
		if err := SetTelegramMiniAppLoginUser(c, &admin, 1001); err != nil {
			c.Status(http.StatusForbidden)
			return
		}
		c.Status(http.StatusNoContent)
	})
	router.GET("/valid", func(c *gin.Context) {
		if IsTelegramMiniAppLogin(c) {
			c.Status(http.StatusNoContent)
		} else {
			c.Status(http.StatusForbidden)
		}
	})
	router.GET("/scoped-token", func(c *gin.Context) {
		// The protected panel API may inject a monitor/node identity, but
		// that is not proof of a Telegram WebApp browser session.
		SetAPIAuthUser(c, &admin)
		sessions.Default(c).Set(telegramMiniAppUserKey, int64(1001))
		if IsTelegramMiniAppLogin(c) {
			c.Status(http.StatusNoContent)
		} else {
			c.Status(http.StatusForbidden)
		}
	})
	request := func(path string, savedCookie *http.Cookie) *httptest.ResponseRecorder {
		t.Helper()
		req := httptest.NewRequest(http.MethodGet, path, nil)
		if savedCookie != nil {
			req.AddCookie(savedCookie)
		}
		rec := httptest.NewRecorder()
		router.ServeHTTP(rec, req)
		return rec
	}

	if code := request("/scoped-token", nil).Code; code != http.StatusForbidden {
		t.Fatalf("forged Telegram ID + scoped API identity returned %d, want 403", code)
	}
	auth := request("/login", nil)
	if auth.Code != http.StatusNoContent {
		t.Fatalf("signed Mini App login returned %d", auth.Code)
	}
	var cookie *http.Cookie
	for _, candidate := range auth.Result().Cookies() {
		if candidate.Name == sessionCookieName {
			cookie = candidate
		}
	}
	if cookie == nil {
		t.Fatal("signed Telegram login did not issue cookie")
	}
	if code := request("/valid", cookie).Code; code != http.StatusNoContent {
		t.Fatalf("valid Telegram WebApp session returned %d, want 204", code)
	}
	if code := request("/scoped-token", cookie).Code; code != http.StatusForbidden {
		t.Fatalf("scoped API token bypassed Telegram session check: %d", code)
	}
}

// Every positive Vela test uses a synthetic file-backed token, exactly like
// production: an environment variable containing raw credentials is not used.
func configureMiniAppTestBotToken(t *testing.T) string {
	t.Helper()
	file := filepath.Join(t.TempDir(), "bot-token")
	if err := os.WriteFile(file, []byte("12345:synthetic_token"), 0600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", file)
	return file
}

func TestMiniAppPolicyNonceTracksBotTokenRotation(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1001")
	file := configureMiniAppTestBotToken(t)
	original := miniAppPolicyNonce()
	if original == "" {
		t.Fatal("a valid Mini App Secret failed to establish a policy")
	}
	if err := os.WriteFile(file, []byte("12345:rotated_token"), 0600); err != nil {
		t.Fatal(err)
	}
	rotated := miniAppPolicyNonce()
	if rotated == "" || rotated == original {
		t.Fatal("Bot Token rotation did not revoke existing sessions")
	}
	if err := os.Remove(file); err != nil {
		t.Fatal(err)
	}
	if nonce := miniAppPolicyNonce(); nonce != "" {
		t.Fatal("missing Bot Secret cannot retain session authorization")
	}
	if err := os.WriteFile(file, []byte("12345:synthetic_token"), 0600); err != nil {
		t.Fatal(err)
	}
	if restored := miniAppPolicyNonce(); restored == "" || restored == original || restored == rotated {
		t.Fatal("restoring an old Bot Secret resurrected a stale session")
	}
}
