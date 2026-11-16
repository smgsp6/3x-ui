package tgbot

import (
	"sync"
	"testing"
)

func TestBotHostnameSnapshotsAreRaceSafeDuringReload(t *testing.T) {
	previous := currentBotHostname()
	t.Cleanup(func() { setBotHostname(previous) })
	var wg sync.WaitGroup
	wg.Add(2)
	go func() {
		defer wg.Done()
		for i := 0; i < 500; i++ {
			setBotHostname("synthetic.local")
		}
	}()
	go func() {
		defer wg.Done()
		for i := 0; i < 500; i++ {
			_ = currentBotHostname()
		}
	}()
	wg.Wait()
	if currentBotHostname() != "synthetic.local" {
		t.Fatal("concurrent Bot reload lost its hostname")
	}
}
