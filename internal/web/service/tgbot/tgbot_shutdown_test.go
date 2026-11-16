package tgbot

import (
	"context"
	"testing"
	"time"

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
	tgBotMutex.Lock()
	adminIds = []int64{918273}
	adminTopics = map[int64]int{918273: 5}
	tgBotMutex.Unlock()

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
	if len(adminSnapshot()) != 0 {
		t.Fatal("shutdown retained prior Telegram administrator permissions")
	}
}

// Cancellation and receiver cleanup must finish even when startup has not
// installed a BotHandler yet.
func TestStopBotCancelsPendingReceiver(t *testing.T) {
	StopBot()
	t.Cleanup(StopBot)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan struct{})
	finished := make(chan struct{})
	go func() {
		<-ctx.Done()
		close(finished)
		close(done)
	}()
	tgBotMutex.Lock()
	botReceiverDone = done
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

// A shutdown must never wait for a NEW polling generation after the old
// generation has been cancelled. That made reloads hang indefinitely with
// the old package-global WaitGroup.
func TestStopBotWaitsOnlyForRetiredGeneration(t *testing.T) {
	StopBot()
	t.Cleanup(StopBot)
	oldCtx, oldCancel := context.WithCancel(context.Background())
	defer oldCancel()
	oldDone := make(chan struct{})
	tgBotMutex.Lock()
	botCancel = oldCancel
	botReceiverDone = oldDone
	isRunning = true
	tgBotMutex.Unlock()

	returned := make(chan struct{})
	go func() {
		StopBot()
		close(returned)
	}()
	// Cancellation proves StopBot has released the receiver lock.
	select {
	case <-oldCtx.Done():
	case <-time.After(3 * time.Second):
		t.Fatal("StopBot did not cancel the old receiver")
	}

	// Simulate another reload installing a fresh receiver while the old
	// generation has not yet finished cleanup.
	_, newCancel := context.WithCancel(context.Background())
	defer newCancel()
	newDone := make(chan struct{})
	tgBotMutex.Lock()
	botCancel = newCancel
	botReceiverDone = newDone
	isRunning = true
	tgBotMutex.Unlock()
	close(oldDone)
	select {
	case <-returned:
	case <-time.After(3 * time.Second):
		close(newDone)
		t.Fatal("StopBot waited for the replacement receiver")
	}
	close(newDone)
}

// Startup holds the lifecycle lock until its connection is fully installed.
// StopBot must not complete while a startup is still in that protected region.
func TestStopBotWaitsForStartupCriticalSection(t *testing.T) {
	StopBot()
	startupLocked := make(chan struct{})
	releaseStartup := make(chan struct{})
	go func() {
		botLifecycleMu.Lock()
		close(startupLocked)
		<-releaseStartup
		botLifecycleMu.Unlock()
	}()
	<-startupLocked
	stopped := make(chan struct{})
	go func() {
		StopBot()
		close(stopped)
	}()
	select {
	case <-stopped:
		close(releaseStartup)
		t.Fatal("StopBot overtook an in-progress startup")
	case <-time.After(25 * time.Millisecond):
	}
	close(releaseStartup)
	select {
	case <-stopped:
	case <-time.After(3 * time.Second):
		t.Fatal("StopBot failed to complete after startup lock was released")
	}
}

func TestAwaitBotReceiverHonorsShutdownDeadline(t *testing.T) {
	if !awaitBotReceiver(context.Background(), nil) {
		t.Fatal("a receiver that never started should not block shutdown")
	}
	finished := make(chan struct{})
	close(finished)
	if !awaitBotReceiver(context.Background(), finished) {
		t.Fatal("an exited receiver was not recognized")
	}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if awaitBotReceiver(ctx, make(chan struct{})) {
		t.Fatal("an unresponsive receiver bypassed the shutdown deadline")
	}
}
