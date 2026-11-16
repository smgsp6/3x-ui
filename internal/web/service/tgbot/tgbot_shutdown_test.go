package tgbot

import (
    "context"
    "testing"

    "github.com/mymmrac/telego"
)

// A queued receiver may not yet set isRunning when panel shutdown starts.
// Closing the connection, not the running flag, is the shutdown guarantee.
func TestStopBotRetiresPendingConnection(t *testing.T) {
    StopBot()
    t.Cleanup(StopBot)
    receiver, err := telego.NewBot(testBotToken)
    if err != nil {
        t.Fatalf("NewBot: %v", err)
    }
    stopped := make(chan struct{})
    botMu.Lock()
    bot = receiver
    botStop = stopped
    botMu.Unlock()

    StopBot()
    if liveBot() != nil {
        t.Fatal("shutdown retained a pending Telegram connection")
    }
    select {
    case <-stopped:
    default:
        t.Fatal("shutdown did not close the pending connection's stop signal")
    }
    if (&Tgbot{}).IsRunning() {
        t.Fatal("shutdown left receiver marked running")
    }
}

// Cancellation and receiver cleanup must finish even when startup has not
// installed a BotHandler yet.
func TestStopBotCancelsPendingReceiver(t *testing.T) {
    StopBot()
    t.Cleanup(StopBot)
    ctx, cancel := context.WithCancel(context.Background())
    defer cancel()
    botWG.Add(1)
    finished := make(chan struct{})
    go func() {
        defer botWG.Done()
        <-ctx.Done()
        close(finished)
    }()
    tgBotMutex.Lock()
    botCancel = cancel
    isRunning = true
    tgBotMutex.Unlock()

    StopBot()
    select {
    case <-finished:
    default:
        t.Fatal("StopBot returned before pending receiver was cancelled")
    }
    if (&Tgbot{}).IsRunning() {
        t.Fatal("StopBot left the cancelled receiver marked running")
    }
}
