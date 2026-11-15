package session

import (
	"net/http"
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
}
