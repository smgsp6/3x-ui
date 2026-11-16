package tgbot

import (
	"encoding/json"
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
	t.Setenv("XUI_TG_MINIAPP_URL", "https://panel.vela-ci.org/private/")
	b := (&Tgbot{}).homeRows(1001)
	found := miniAppLaunchButtons(b)
	if len(found) != 1 || found[0].WebApp.URL != "https://panel.vela-ci.org/private/" {
		t.Fatal("allowlisted private Telegram admin must see one correct official WebApp button")
	}
}

// Verify the actual Bot API outgoing keyboard payload, not just the
// homeRows helper. Uses the repository's loopback recording server and sends
// no Telegram traffic or credentials.
func TestVelaWebAppButtonSentThroughTelegramAPI(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1001")
	t.Setenv("XUI_TG_MINIAPP_URL", "https://panel.vela-ci.org/private/")
	bot, calls := newScreenTgbot(t, false)
	bot.renderScreen(1001, bot.newScreen("main", "synthetic panel", bot.homeRows(1001)...))
	found := false
	for _, call := range calls() {
		if call.Method != "sendPhoto" && call.Method != "sendMessage" {
			continue
		}
		var markup map[string]any
		switch raw := call.Payload["reply_markup"].(type) {
		case map[string]any:
			markup = raw
		case string:
			if err := json.Unmarshal([]byte(raw), &markup); err != nil {
				t.Fatal("recorded Telegram reply markup could not be decoded")
			}
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
				if webApp["url"] != "https://panel.vela-ci.org/private/" {
					t.Fatal("outgoing Telegram WebApp destination differs from approved HTTPS URL")
				}
				found = true
			}
		}
	}
	if !found {
		t.Fatal("outgoing Telegram API message omitted the approved web_app button")
	}
}

func TestVelaLaunchButtonNeverAppearsInGroupOrUnapprovedChat(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "1001")
	t.Setenv("XUI_TG_MINIAPP_URL", "https://panel.vela-ci.org/private/")
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
