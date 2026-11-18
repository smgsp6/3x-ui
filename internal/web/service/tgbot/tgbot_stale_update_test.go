package tgbot

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/mymmrac/telego"
	th "github.com/mymmrac/telego/telegohandler"
)

func TestRetiredReceiverCannotDispatchStaleUpdates(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	file := filepath.Join(t.TempDir(), "bot-token")
	if err := os.WriteFile(file, []byte(testBotToken), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", file)
	previous := liveBot()
	botMu.RLock()
	previousCheck := botCredentialAllowed
	botMu.RUnlock()
	t.Cleanup(func() {
		botMu.Lock()
		bot, botCredentialAllowed = previous, previousCheck
		botMu.Unlock()
	})
	receiver, err := telego.NewBot(testBotToken)
	if err != nil {
		t.Fatalf("NewBot: %v", err)
	}
	botMu.Lock()
	bot, botCredentialAllowed = receiver, botCredentialCheck(true, testBotToken)
	botMu.Unlock()
	h, err := th.NewBotHandler(receiver, make(chan telego.Update, 1))
	if err != nil {
		t.Fatalf("NewBotHandler: %v", err)
	}
	guardReceiverUpdates(h, receiver)
	hits := 0
	h.HandleMessage(func(*th.Context, telego.Message) error {
		hits++
		return nil
	}, th.AnyMessage())
	update := telego.Update{UpdateID: 7, Message: &telego.Message{
		Chat: telego.Chat{ID: 123, Type: telego.ChatTypePrivate},
		From: &telego.User{ID: 123},
		Text: "/start",
	}}
	if err := h.BaseGroup().HandleUpdate(context.Background(), receiver, update); err != nil {
		t.Fatalf("active Bot update: %v", err)
	}
	if hits != 1 {
		t.Fatalf("active receiver dispatched %d updates, want one", hits)
	}
	if err := os.Remove(file); err != nil {
		t.Fatal(err)
	}
	if err := h.BaseGroup().HandleUpdate(context.Background(), receiver, update); err != nil {
		t.Fatalf("update after Secret removal: %v", err)
	}
	if hits != 1 {
		t.Fatalf("receiver without a Secret executed a command (%d hits)", hits)
	}
	// Simulate reload: old HTTP connection still has a queued Telegram update.
	setTestBot(nil)
	if err := h.BaseGroup().HandleUpdate(context.Background(), receiver, update); err != nil {
		t.Fatalf("retired Bot update: %v", err)
	}
	if hits != 1 {
		t.Fatalf("retired receiver executed a command (%d hits)", hits)
	}
}
