package tgbot

import (
	"slices"
	"testing"
)

// A revoked Telegram ID must lose privileged Bot commands and be removed from
// every notification recipient snapshot, even before the receiver is restarted.
func TestVelaBotRevocationTakesEffectWithoutReload(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "111,222")
	tgBotMutex.Lock()
	previous := adminIds
	adminIds = []int64{111, 222}
	tgBotMutex.Unlock()
	t.Cleanup(func() {
		tgBotMutex.Lock()
		adminIds = previous
		tgBotMutex.Unlock()
	})

	if !checkAdmin(111) || !checkAdmin(222) {
		t.Fatal("valid allowlisted administrators were unexpectedly denied")
	}
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "222")
	if checkAdmin(111) || !checkAdmin(222) {
		t.Fatal("revoked Bot administrator retained privilege")
	}
	if got := adminSnapshot(); !slices.Equal(got, []int64{222}) {
		t.Fatalf("notice recipients included a revoked user: %v", got)
	}
	// Invalid allowlist means no one is authorized, including cached admins.
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "222,222")
	if checkAdmin(111) || checkAdmin(222) || len(adminSnapshot()) != 0 {
		t.Fatal("malformed Mini App allowlist must revoke all cached Bot privileges")
	}
}

// The regular upstream Telegram notification mode keeps its original chat ID
// list (including supergroups); Vela-specific filtering is opt-in only.
func TestLegacyTelegramRecipientsRemainUnchanged(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "false")
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "")
	tgBotMutex.Lock()
	previous := adminIds
	adminIds = []int64{-1001234, 111}
	tgBotMutex.Unlock()
	t.Cleanup(func() {
		tgBotMutex.Lock()
		adminIds = previous
		tgBotMutex.Unlock()
	})
	if got := adminSnapshot(); !slices.Equal(got, []int64{-1001234, 111}) {
		t.Fatalf("legacy Bot recipient behavior changed: %v", got)
	}
}
