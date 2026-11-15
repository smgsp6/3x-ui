package web

import (
	"errors"
	"testing"
)

func TestTelegramMiniAppStartsBotWithoutLegacyNotificationSetting(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	for _, tt := range []struct {
		name string
		legacy bool
		err error
	}{
		{"fresh sqlite defaults", false, nil},
		{"unavailable legacy preference", false, errors.New("synthetic legacy setting unavailable")},
		{"legacy enabled", true, nil},
	} {
		t.Run(tt.name, func(t *testing.T) {
			if !shouldStartTelegramBot(tt.legacy, tt.err) {
				t.Fatal("Telegram Mini App launcher requires bot receiver")
			}
		})
	}
}

func TestOriginalTelegramBotSettingRemainsAuthoritativeOutsideMiniApp(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "false")
	if shouldStartTelegramBot(false, nil) {
		t.Fatal("upstream disabled bot must stay disabled")
	}
	if shouldStartTelegramBot(true, errors.New("synthetic settings error")) {
		t.Fatal("upstream settings failure must not start bot")
	}
	if !shouldStartTelegramBot(true, nil) {
		t.Fatal("upstream explicitly enabled bot must still start")
	}
}
