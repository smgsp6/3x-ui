package tgbot

import (
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/mhsanaei/3x-ui/v3/internal/web/global"
)

// Reload can replace the shared callback store while an old Telegram worker
// is formatting a keyboard or decoding a previously issued callback.
func TestCallbackStoreReplacementIsRaceSafe(t *testing.T) {
	previous := currentHashStorage()
	t.Cleanup(func() { setHashStorage(previous) })
	setHashStorage(global.NewHashStorage(time.Minute))

	var workers sync.WaitGroup
	workers.Add(2)
	go func() {
		defer workers.Done()
		for i := 0; i < 200; i++ {
			setHashStorage(global.NewHashStorage(time.Minute))
		}
	}()
	go func() {
		defer workers.Done()
		b := &Tgbot{}
		for i := 0; i < 200; i++ {
			key := b.encodeQuery(strings.Repeat("x", 80))
			if key != "" {
				_, _ = b.decodeQuery(key)
			}
		}
	}()
	workers.Wait()
}

func TestCallbackStoreUnavailableFailsClosed(t *testing.T) {
	previous := currentHashStorage()
	t.Cleanup(func() { setHashStorage(previous) })
	setHashStorage(nil)
	b := &Tgbot{}
	if got := b.encodeQuery(strings.Repeat("x", 80)); got != "" {
		t.Fatal("an unavailable hash store cannot issue a usable callback")
	}
	if _, err := b.decodeQuery("restart"); err == nil {
		t.Fatal("an unavailable callback store must not accept callbacks")
	}
}
