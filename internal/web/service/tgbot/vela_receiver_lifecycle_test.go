package tgbot

import (
	"testing"

	"github.com/mymmrac/telego"
)

// A failed or late receiver is only allowed to retire its own connection.
// This is deliberately offline: it must never call the public Telegram API.
func TestFinishBotReceiverCannotStopReplacementConnection(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "false")
	oldBot, err := telego.NewBot(testBotToken)
	if err != nil {
		t.Fatalf("old Bot: %v", err)
	}
	replacement, err := telego.NewBot(testBotToken)
	if err != nil {
		t.Fatalf("replacement Bot: %v", err)
	}

	tgBotMutex.Lock()
	previousCancel := botCancel
	previousHandler := botHandler
	previousRunning := isRunning
	previousAdmins, previousTopics := adminIds, adminTopics
	botMu.Lock()
	previousBot, previousStop := bot, botStop
	stop := make(chan struct{})
	bot = replacement
	botStop = stop
	botMu.Unlock()
	botCancel = nil
	botHandler = nil
	isRunning = true
	adminIds = []int64{1001}
	adminTopics = map[int64]int{1001: 42}
	tgBotMutex.Unlock()
	t.Cleanup(func() {
		tgBotMutex.Lock()
		botCancel = previousCancel
		botHandler = previousHandler
		isRunning = previousRunning
		adminIds, adminTopics = previousAdmins, previousTopics
		botMu.Lock()
		bot, botStop = previousBot, previousStop
		botMu.Unlock()
		tgBotMutex.Unlock()
	})

	finishBotReceiver(oldBot)
	if liveBot() != replacement || !(&Tgbot{}).IsRunning() {
		t.Fatal("stale receiver retired the replacement Bot")
	}
	if !checkAdmin(1001) || adminTopic(1001) != 42 {
		t.Fatal("stale receiver revoked the replacement Bot's administrators")
	}
	select {
	case <-stop:
		t.Fatal("stale receiver closed the replacement Bot")
	default:
	}

	finishBotReceiver(replacement)
	if liveBot() != nil || (&Tgbot{}).IsRunning() {
		t.Fatal("exited receiver remains live or running")
	}
	if checkAdmin(1001) || adminTopic(1001) != 0 {
		t.Fatal("retired receiver retained administrator permissions or topics")
	}
	select {
	case <-stop:
	default:
		t.Fatal("retired receiver did not disable subsequent Bot API calls")
	}
}

// A receiver scheduled before a restart must not poll the replacement Bot.
func TestDelayedBotReceiverDoesNotClaimReplacement(t *testing.T) {
	oldBot, err := telego.NewBot(testBotToken)
	if err != nil {
		t.Fatal(err)
	}
	replacement, err := telego.NewBot(testBotToken)
	if err != nil {
		t.Fatal(err)
	}

	botMu.Lock()
	previous := bot
	bot = replacement
	botMu.Unlock()
	t.Cleanup(func() {
		botMu.Lock()
		bot = previous
		botMu.Unlock()
	})

	(&Tgbot{}).receive(oldBot)
	if liveBot() != replacement || (&Tgbot{}).IsRunning() {
		t.Fatal("delayed receiver changed the replacement Bot's state")
	}
}
