package tgbot

import (
	"sync"
	"testing"
)

// Replacing a pool during a worker callback must not send on one generation
// and release from another. This is race-checked without Telegram networking.
func TestWorkerPoolReplacementKeepsSlotsBalanced(t *testing.T) {
	old := currentBotWorkerPool()
	t.Cleanup(func() { setBotWorkerPool(old) })
	first := make(chan struct{}, 1)
	second := make(chan struct{}, 1)
	setBotWorkerPool(first)
	entered := make(chan struct{})
	release := make(chan struct{})
	finished := make(chan struct{})
	go func() {
		runBotHandler(func() {
			close(entered)
			<-release
		})
		close(finished)
	}()
	<-entered
	setBotWorkerPool(second)
	close(release)
	<-finished
	if len(first) != 0 || len(second) != 0 {
		t.Fatal("worker returned its token to the wrong pool")
	}
}

func TestWorkerPoolRotationUnderConcurrentHandlers(t *testing.T) {
	old := currentBotWorkerPool()
	t.Cleanup(func() { setBotWorkerPool(old) })
	setBotWorkerPool(make(chan struct{}, 10))
	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		for i := 0; i < 300; i++ {
			setBotWorkerPool(make(chan struct{}, 10))
		}
	}()
	go func() {
		defer wg.Done()
		for i := 0; i < 300; i++ {
			runBotHandler(func() {})
		}
	}()
	wg.Wait()
}
