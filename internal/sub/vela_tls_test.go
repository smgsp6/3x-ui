package sub

import (
	"path/filepath"
	"testing"

	"github.com/mhsanaei/3x-ui/v3/internal/database"
	"github.com/mhsanaei/3x-ui/v3/internal/database/model"
)

func TestVelaSubscriptionRefusesInvalidConfiguredTLS(t *testing.T) {
	initSubDB(t)
	missing := filepath.Join(t.TempDir(), "missing.pem")
	settings := []model.Setting{
		{Key: "subListen", Value: "127.0.0.1"},
		{Key: "subPort", Value: "0"},
		{Key: "subCertFile", Value: missing},
		{Key: "subKeyFile", Value: missing},
	}
	if err := database.GetDB().Create(&settings).Error; err != nil {
		t.Fatal(err)
	}

	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	server := NewServer()
	err := server.Start()
	if err == nil {
		_ = server.Stop()
		t.Fatal("subscription server fell back to HTTP")
	}
	if err.Error() != "Vela subscription TLS material is invalid; refusing silent HTTP downgrade" || server.listener != nil {
		t.Fatalf("unexpected Vela TLS startup error: %v", err)
	}
}
