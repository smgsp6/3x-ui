package tgbot

import (
	"errors"
	"strings"
	"testing"
)

func TestVelaTelegramErrorsNeverExposeBotToken(t *testing.T) {
	const exampleSecret = "123456:synthetic-not-a-real-bot-token"
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	fixture := errors.New("POST https://api.telegram.org/bot" + exampleSecret + "/sendMessage: failed")
	safe := safeTelegramLogError(fixture)
	if safe == nil || strings.Contains(safe.Error(), exampleSecret) ||
		strings.Contains(safe.Error(), "/bot") {
		t.Fatal("Mini App Telegram API errors must never contain credentials")
	}
	if strings.Contains(safeTelegramLogPanic(fixture).(string), exampleSecret) {
		t.Fatal("Mini App Telegram handler panic disclosed credential")
	}
	if safeTelegramLogError(nil) != nil {
		t.Fatal("nil errors must remain nil")
	}
}

func TestOriginalBotErrorReportingUnaffectedOutsideVela(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "false")
	original := errors.New("synthetic upstream telegram request failure")
	if safeTelegramLogError(original) != original {
		t.Fatal("upstream bot mode must keep original error detail")
	}
	if safeTelegramLogPanic(original) != original {
		t.Fatal("upstream bot mode must keep original panic payload")
	}
}
