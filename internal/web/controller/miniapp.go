package controller

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/mhsanaei/3x-ui/v3/internal/web/middleware"
	"github.com/mhsanaei/3x-ui/v3/internal/web/service"
	"github.com/mhsanaei/3x-ui/v3/internal/web/service/panel"
	"github.com/mhsanaei/3x-ui/v3/internal/web/service/tgminiapp"
	"github.com/mhsanaei/3x-ui/v3/internal/web/session"
)

// NewMiniAppController registers an opt-in login endpoint. It reuses existing
// sessions and the existing admin user instead of bypassing the panel API ACL.
func NewMiniAppController(g *gin.RouterGroup) {
	// Only this Vela-specific handler counts as a live upgrade target.
	g.GET("/tg-miniapp/health", func(c *gin.Context) {
		c.Header("Cache-Control", "no-store")
		if !tgminiapp.Enabled() || tgminiapp.BotToken() == "" {
			c.AbortWithStatus(http.StatusServiceUnavailable)
			return
		}
		admin, err := (&panel.UserService{}).GetFirstUser()
		if err != nil || admin == nil {
			c.AbortWithStatus(http.StatusServiceUnavailable)
			return
		}
		c.Status(http.StatusNoContent)
	})
	g.POST("/tg-miniapp/auth", middleware.MaxBodyBytes(16<<10), middleware.CSRFMiddleware(getRemoteIp), func(c *gin.Context) {
		c.Header("Cache-Control", "no-store")
		if !tgminiapp.Enabled() {
			c.AbortWithStatus(http.StatusNotFound)
			return
		}
		var body struct {
			InitData string `json:"initData" binding:"required"`
		}
		if err := c.ShouldBindJSON(&body); err != nil {
			c.AbortWithStatus(http.StatusBadRequest)
			return
		}

		// Vela requires an explicit credential in a local Docker secret or env;
		// never silently authenticate with a different legacy bot token.
		token := tgminiapp.BotToken()
		if token == "" {
			c.AbortWithStatus(http.StatusServiceUnavailable)
			return
		}
		telegramUser, err := tgminiapp.Verify(body.InitData, token, time.Now())
		if err != nil {
			// Do not log auth payloads, usernames, tokens, or user identifiers.
			c.AbortWithStatus(http.StatusUnauthorized)
			return
		}
		admin, err := (&panel.UserService{}).GetFirstUser()
		if err != nil || admin == nil {
			c.AbortWithStatus(http.StatusServiceUnavailable)
			return
		}
		if err := session.SetTelegramMiniAppLoginUser(c, admin, telegramUser.ID); err != nil {
			c.AbortWithStatus(http.StatusInternalServerError)
			return
		}
		c.JSON(http.StatusOK, gin.H{"success": true})
	})
}

// NewCertificateStatusController must be registered on the already
// authenticated /panel/api group, never on the public router.
func NewCertificateStatusController(api *gin.RouterGroup) {
	api.GET("/certificates/status", func(c *gin.Context) {
		s := &service.SettingService{}
		webCert, e1 := s.GetCertFile()
		webKey, e2 := s.GetKeyFile()
		subCert, e3 := s.GetSubCertFile()
		subKey, e4 := s.GetSubKeyFile()
		if e1 != nil || e2 != nil || e3 != nil || e4 != nil {
			c.AbortWithStatus(http.StatusInternalServerError)
			return
		}
		now := time.Now()
		c.Header("Cache-Control", "no-store")
		c.JSON(http.StatusOK, gin.H{"success": true, "obj": gin.H{
			"alertsEnabled": tgminiapp.CertAlertsEnabled(),
			"certificates": []tgminiapp.CertificateStatus{
				tgminiapp.InspectCertificate("panel", webCert, webKey, now),
				tgminiapp.InspectCertificate("subscription", subCert, subKey, now),
			},
		}})
	})
}
