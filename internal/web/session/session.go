package session

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/gob"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/mhsanaei/3x-ui/v3/internal/database"
	"github.com/mhsanaei/3x-ui/v3/internal/database/model"
	"github.com/mhsanaei/3x-ui/v3/internal/logger"
	"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"

	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"
)

const (
	loginUserKey             = "LOGIN_USER"
	loginEpochKey            = "LOGIN_EPOCH"
	apiAuthUserKey           = "api_auth_user"
	telegramMiniAppUserKey   = "TELEGRAM_MINIAPP_USER_ID"
	telegramMiniAppPolicyKey = "TELEGRAM_MINIAPP_POLICY_NONCE"
	sessionCookieName        = "3x-ui"
)

// A Mini App cookie is bound to this process and the configured allowlist.
// Changing the allowlist invalidates existing cookies; restarting also issues
// a fresh nonce. Never reuse an old signed cookie after an admin revocation.
// This intentionally does not support load-balanced panel replicas sharing a
// cookie store without a shared revocation mechanism.
var miniAppPolicy = struct {
	sync.Mutex
	allowlist string
	tokenHash [sha256.Size]byte
	nonce     string
}{}

func miniAppPolicyNonce() string {
	return miniAppPolicyNonceForToken("")
}

// A nonempty verifiedToken binds issuance to the Secret used for HMAC
// validation, even if the file was rotated before the session was issued.
func miniAppPolicyNonceForToken(verifiedToken string) string {
	// A Bot Token rotation revokes old Mini App credentials just like an
	// administrator allowlist change. Store only the token fingerprint, never
	// the credential itself in session metadata or logs.
	miniAppPolicy.Lock()
	defer miniAppPolicy.Unlock()
	token := tgminiapp.BotToken()
	if token == "" {
		// If the Secret disappears, fail closed and prevent replay even if
		// the identical Secret is later restored.
		miniAppPolicy.nonce = ""
		miniAppPolicy.tokenHash = [sha256.Size]byte{}
		return ""
	}
	fingerprint := sha256.Sum256([]byte(token))
	allowlist := os.Getenv("XUI_TG_MINIAPP_ADMIN_IDS")
	if miniAppPolicy.nonce == "" || miniAppPolicy.allowlist != allowlist ||
		miniAppPolicy.tokenHash != fingerprint {
		var random [32]byte
		if _, err := rand.Read(random[:]); err != nil {
			miniAppPolicy.nonce = ""
			return "" // fail closed if secure randomness is unavailable
		}
		miniAppPolicy.allowlist = allowlist
		miniAppPolicy.tokenHash = fingerprint
		miniAppPolicy.nonce = base64.RawURLEncoding.EncodeToString(random[:])
	}
	if verifiedToken != "" && subtle.ConstantTimeCompare([]byte(verifiedToken), []byte(token)) != 1 {
		return ""
	}
	return miniAppPolicy.nonce
}

func init() {
	gob.Register(model.User{})
}

func SetLoginUser(c *gin.Context, user *model.User) error {
	if user == nil {
		return nil
	}
	s := sessions.Default(c)
	// Credential rotation from within Mini App must retain the signed Telegram
	// identity. A legacy caller cannot mint a Vela session via this function.
	var tgID int64
	var policyNonce, newSessionID string
	// Even the legacy login path must retire a previous Mini App session.
	// Disabling Vela must never preserve a stolen signed Telegram cookie.
	oldSessionID, _ := s.Get(telegramMiniAppSessionKey).(string)
	if tgminiapp.Enabled() {
		id, ok := s.Get(telegramMiniAppUserKey).(int64)
		policyNonce = miniAppPolicyNonce()
		if !ok || !tgminiapp.AllowedUserID(id) || policyNonce == "" ||
			s.Get(telegramMiniAppPolicyKey) != policyNonce ||
			!miniAppSessionActive(oldSessionID) {
			return http.ErrNoCookie
		}
		tgID = id
		var err error
		newSessionID, err = issueMiniAppSession()
		if err != nil {
			return err
		}
	}
	// Anyone can mint the anonymous session this request carried and plant it in a browser,
	// so nothing in it, the CSRF token above all, outlives the privilege change.
	s.Clear()
	s.Set(loginUserKey, user.Id)
	s.Set(loginEpochKey, user.LoginEpoch)
	if tgminiapp.Enabled() {
		s.Set(telegramMiniAppUserKey, tgID)
		s.Set(telegramMiniAppPolicyKey, policyNonce)
		s.Set(telegramMiniAppSessionKey, newSessionID)
	}
	if err := s.Save(); err != nil {
		revokeMiniAppSession(newSessionID)
		return err
	}
	revokeMiniAppSession(oldSessionID)
	return nil
}

// SetTelegramMiniAppLoginUser binds a signed Telegram identity to the same
// normal panel user session; changing the admin allowlist revokes access.
func SetTelegramMiniAppLoginUser(c *gin.Context, user *model.User, telegramID int64, verifiedToken string) error {
	if !tgminiapp.Enabled() || user == nil || verifiedToken == "" || telegramID <= 0 || !tgminiapp.AllowedUserID(telegramID) {
		return http.ErrNoCookie
	}
	policyNonce := miniAppPolicyNonceForToken(verifiedToken)
	if policyNonce == "" {
		return http.ErrNoCookie
	}
	sessionID, err := issueMiniAppSession()
	if err != nil {
		return err
	}
	s := sessions.Default(c)
	priorSession, _ := s.Get(telegramMiniAppSessionKey).(string)
	s.Clear()
	s.Set(loginUserKey, user.Id)
	s.Set(loginEpochKey, user.LoginEpoch)
	s.Set(telegramMiniAppUserKey, telegramID)
	s.Set(telegramMiniAppPolicyKey, policyNonce)
	s.Set(telegramMiniAppSessionKey, sessionID)
	if err := s.Save(); err != nil {
		revokeMiniAppSession(sessionID)
		return err
	}
	revokeMiniAppSession(priorSession)
	return nil
}

func SetAPIAuthUser(c *gin.Context, user *model.User) {
	if user == nil {
		return
	}
	c.Set(apiAuthUserKey, user)
}

func GetLoginUser(c *gin.Context) *model.User {
	if v, ok := c.Get(apiAuthUserKey); ok {
		if u, ok2 := v.(*model.User); ok2 {
			return u
		}
	}
	s := sessions.Default(c)
	if !tgminiapp.Enabled() && (s.Get(telegramMiniAppUserKey) != nil ||
		s.Get(telegramMiniAppSessionKey) != nil || s.Get(telegramMiniAppPolicyKey) != nil) {
		// A Telegram-origin cookie must not become an ordinary password login
		// merely because the Mini App feature was disabled. Revoke its
		// server-side ID so toggling the feature back on cannot resurrect it.
		id, _ := s.Get(telegramMiniAppSessionKey).(string)
		revokeMiniAppSession(id)
		s.Clear()
		if err := s.Save(); err != nil {
			logger.Warning("session: failed to retire disabled Mini App cookie:", err)
		}
		return nil
	}
	if tgminiapp.Enabled() {
		telegramID, ok := s.Get(telegramMiniAppUserKey).(int64)
		nonce, hasNonce := s.Get(telegramMiniAppPolicyKey).(string)
		sessionID, hasSessionID := s.Get(telegramMiniAppSessionKey).(string)
		currentNonce := miniAppPolicyNonce()
		if !ok || !tgminiapp.AllowedUserID(telegramID) || !hasNonce || !hasSessionID ||
			currentNonce == "" || subtle.ConstantTimeCompare([]byte(nonce), []byte(currentNonce)) != 1 ||
			!miniAppSessionActive(sessionID) {
			// Retire a formerly authenticated browser cookie; do not destroy
			// a new anonymous session's CSRF token during Mini App login.
			if s.Get(loginUserKey) != nil || s.Get(telegramMiniAppUserKey) != nil {
				revokeMiniAppSession(sessionID)
				s.Clear()
				if err := s.Save(); err != nil {
					logger.Warning("session: failed to retire revoked Mini App cookie:", err)
				}
			}
			return nil
		}
	}
	obj := s.Get(loginUserKey)
	if obj == nil {
		return nil
	}
	userID, ok := sessionUserID(obj)
	if !ok {
		s.Delete(loginUserKey)
		s.Delete(loginEpochKey)
		if err := s.Save(); err != nil {
			logger.Warning("session: failed to drop stale user payload:", err)
		}
		return nil
	}
	if legacyUserID, ok := legacySessionUserID(obj); ok {
		s.Set(loginUserKey, legacyUserID)
		if err := s.Save(); err != nil {
			logger.Warning("session: failed to migrate legacy user payload:", err)
		}
	}
	user, err := getUserByID(userID)
	if err != nil {
		logger.Warning("session: failed to load user:", err)
		s.Delete(loginUserKey)
		s.Delete(loginEpochKey)
		if saveErr := s.Save(); saveErr != nil {
			logger.Warning("session: failed to drop missing user:", saveErr)
		}
		return nil
	}
	if !sessionEpochMatches(s.Get(loginEpochKey), user.LoginEpoch) {
		s.Delete(loginUserKey)
		s.Delete(loginEpochKey)
		if saveErr := s.Save(); saveErr != nil {
			logger.Warning("session: failed to drop stale epoch:", saveErr)
		}
		return nil
	}
	return user
}

func sessionEpochMatches(cookieVal any, userEpoch int64) bool {
	var got int64
	switch v := cookieVal.(type) {
	case nil:
	case int64:
		got = v
	case int:
		got = int64(v)
	case int32:
		got = int64(v)
	case float64:
		got = int64(v)
	default:
		return false
	}
	return got == userEpoch
}

func IsLogin(c *gin.Context) bool {
	return GetLoginUser(c) != nil
}

// IsTelegramMiniAppLogin requires the validated, revocable Telegram session,
// not merely an enabled Mini App deployment. Never expose Telegram UI or SDK
// to ordinary panel logins just because the server feature flag is set.
func IsTelegramMiniAppLogin(c *gin.Context) bool {
	if !tgminiapp.Enabled() {
		return false
	}
	// Scoped API-token and mTLS identities are intentionally allowed to use
	// some panel APIs, but they are NOT Telegram WebApp browser sessions.
	// GetLoginUser would otherwise short-circuit on apiAuthUserKey before
	// checking the cookie nonce, epoch and revocation registry.
	if _, apiIdentity := c.Get(apiAuthUserKey); apiIdentity {
		return false
	}
	if GetLoginUser(c) == nil {
		return false
	}
	id, ok := sessions.Default(c).Get(telegramMiniAppUserKey).(int64)
	return ok && tgminiapp.AllowedUserID(id)
}

func sessionUserID(obj any) (int, bool) {
	switch v := obj.(type) {
	case int:
		return v, v > 0
	case int64:
		return int(v), v > 0
	case int32:
		return int(v), v > 0
	case float64:
		id := int(v)
		return id, v == float64(id) && id > 0
	case model.User:
		return v.Id, v.Id > 0
	case *model.User:
		if v == nil {
			return 0, false
		}
		return v.Id, v.Id > 0
	default:
		return 0, false
	}
}

func legacySessionUserID(obj any) (int, bool) {
	switch v := obj.(type) {
	case model.User:
		return v.Id, v.Id > 0
	case *model.User:
		if v == nil {
			return 0, false
		}
		return v.Id, v.Id > 0
	default:
		return 0, false
	}
}

func getUserByID(id int) (*model.User, error) {
	db := database.GetDB()
	if db == nil {
		return nil, http.ErrServerClosed
	}
	user := &model.User{}
	if err := db.Model(model.User{}).Where("id = ?", id).First(user).Error; err != nil {
		return nil, err
	}
	return user, nil
}

func ClearSession(c *gin.Context) error {
	s := sessions.Default(c)
	// Logout must invalidate server-side Mini App sessions even if the
	// feature was disabled between authentication and this request.
	sessionID, _ := s.Get(telegramMiniAppSessionKey).(string)
	revokeMiniAppSession(sessionID)
	s.Clear()
	cookiePath := c.GetString("base_path")
	if cookiePath == "" {
		cookiePath = "/"
	}
	secure := c.Request.TLS != nil || tgminiapp.Enabled()
	s.Options(sessions.Options{
		Path:     cookiePath,
		MaxAge:   -1,
		HttpOnly: true,
		Secure:   secure,
		SameSite: http.SameSiteLaxMode,
	})
	if err := s.Save(); err != nil {
		return err
	}
	if cookiePath != "/" {
		http.SetCookie(c.Writer, &http.Cookie{
			Name:     sessionCookieName,
			Value:    "",
			Path:     "/",
			MaxAge:   -1,
			Expires:  time.Unix(0, 0),
			HttpOnly: true,
			Secure:   secure,
			SameSite: http.SameSiteLaxMode,
		})
	}
	return nil
}
