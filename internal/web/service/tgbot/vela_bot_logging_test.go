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

func TestMiniAppIgnoresLegacyBotTransportOverrides(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	proxy, api := botConnectionOptions(
		"http://legacy-proxy.invalid:8080",
		"https://legacy-bot-api.invalid/bot{token}/",
	)
	if proxy != "" || api != "" {
		t.Fatal("private Vela Bot Token must never flow to legacy DB-configured transport")
	}
}

func TestUpstreamBotTransportOverridesPreserved(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "false")
	const proxy = "socks5://127.0.0.1:1080"
	const api = "https://legacy-telegram-api.example.org/"
	actualProxy, actualAPI := botConnectionOptions(proxy, api)
	if actualProxy != proxy || actualAPI != api {
		t.Fatal("existing upstream Telegram Bot transport must not change")
	}
}

func TestVelaBroadcastLogNeverPrintsPrivateChatOrMessageID(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	if safeTelegramLogID(987654321) != 0 || safeTelegramLogMessageIDs([]int{123, 456}) != nil {
		t.Fatal("Vela broadcast log contains private Telegram identifiers")
	}
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "false")
	if safeTelegramLogID(987654321) != 987654321 ||
		len(safeTelegramLogMessageIDs([]int{123, 456})) != 2 {
		t.Fatal("upstream broadcast logging behavior must remain available")
	}
}
