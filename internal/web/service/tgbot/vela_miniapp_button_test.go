package tgbot

import (
	"testing"

	"github.com/mymmrac/telego"
)

func miniAppLaunchButtons(rows [][]telego.InlineKeyboardButton) []telego.InlineKeyboardButton {
	var found []telego.InlineKeyboardButton
	for _, row := range rows {
		for _, button := range row {
			if button.WebApp != nil {
				found = append(found, button)
			}
		}
	}
	return found
}

func TestVelaPrivateAdminGetsOfficialWebAppLaunchButton(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1001")
	t.Setenv("XUI_TG_MINIAPP_URL", "https://panel.vela-ci.example.test/private/")
	b := (&Tgbot{}).homeRows(1001)
	found := miniAppLaunchButtons(b)
	if len(found) != 1 || found[0].WebApp.URL != "https://panel.vela-ci.example.test/private/" {
		t.Fatal("allowlisted private Telegram admin must see one correct official WebApp button")
	}
}

// Verify the actual /start -> screen rendering -> Telegram Bot API payload,
// not only a keyboard builder. This is offline: recordingServer is loopback.
func TestVelaAdminStartSendsOfficialWebAppButtonToTelegramAPI(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1001")
	t.Setenv("XUI_TG_MINIAPP_URL", "https://panel.vela-ci.example.test/private/")
	_, calls := newScreenTgbot(t, false)
	bot := initReportDB(t)
	setTestAdmins(t, 1001)
	bot.resolveScreenArt()
	bot.answerCommand(&telego.Message{
		MessageID: 420,
		Chat: telego.Chat{ID: 1001, Type: "private"},
		From: &telego.User{ID: 1001},
		Text: "/start",
	}, 1001, true)
	found := false
	for _, call := range calls() {
		if call.Method != "sendPhoto" && call.Method != "sendMessage" {
			continue
		}
		markup, ok := call.Payload["reply_markup"].(map[string]any)
		if !ok {
			continue
		}
		rows, ok := markup["inline_keyboard"].([]any)
		if !ok {
			continue
		}
		for _, rawRow := range rows {
			buttons, ok := rawRow.([]any)
			if !ok {
				continue
			}
			for _, rawButton := range buttons {
				button, ok := rawButton.(map[string]any)
				if !ok {
					continue
				}
				webApp, ok := button["web_app"].(map[string]any)
				if !ok {
					continue
				}
				if webApp["url"] != "https://panel.vela-ci.example.test/private/" {
					t.Fatal("Telegram /start sent an unexpected WebApp destination")
				}
				found = true
			}
		}
	}
	if !found {
		t.Fatal("Telegram /start did not send official web_app payload")
	}
}

func TestVelaLaunchButtonNeverAppearsInGroupOrUnapprovedChat(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1001")
	t.Setenv("XUI_TG_MINIAPP_URL", "https://panel.vela-ci.example.test/private/")
	bot := &Tgbot{}
	for _, tc := range []struct {
		name string
		chatID int64
	}{
		{"group chat", -10012345},
		{"unapproved private", 1002},
		{"missing actor", 0},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if got := miniAppLaunchButtons(bot.homeRows(tc.chatID)); len(got) != 0 {
				t.Fatal("Vela launch button escaped admin-only private-chat scope")
			}
		})
	}
	if len(miniAppLaunchButtons(bot.homeRows())) != 0 {
		t.Fatal("legacy menu call without chat identity must not expose WebApp")
	}
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "false")
	if got := miniAppLaunchButtons(bot.homeRows(1001)); len(got) != 0 {
		t.Fatal("disabled Mini App must retain original Telegram keyboard")
	}
}
