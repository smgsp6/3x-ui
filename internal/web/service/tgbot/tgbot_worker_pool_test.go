package tgbot

import (
	"context"
	"sync"
	"testing"
	"time"
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
		runBotHandler(context.Background(), currentBotWorkerPool(), func() {
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
			runBotHandler(context.Background(), currentBotWorkerPool(), func() {})
		}
	}()
	wg.Wait()
}

func TestCanceledReceiverDropsQueuedWorker(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	t.Cleanup(cancel)
	pool := make(chan struct{}, 1)
	pool <- struct{}{}
	ran := make(chan struct{}, 1)
	finished := make(chan struct{})
	go func() {
		runBotHandler(ctx, pool, func() { ran <- struct{}{} })
		close(finished)
	}()
	cancel()
	select {
	case <-finished:
	case <-time.After(time.Second):
		t.Fatal("canceled receiver left its worker waiting for a slot")
	}
	if len(ran) != 0 || len(pool) != 1 {
		t.Fatal("canceled receiver processed an update or released another worker's slot")
	}

	<-pool
	runBotHandler(ctx, pool, func() { ran <- struct{}{} })
	if len(ran) != 0 || len(pool) != 0 {
		t.Fatal("canceled receiver used a free worker slot to process an update")
	}
}
