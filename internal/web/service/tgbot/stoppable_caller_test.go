package tgbot

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mymmrac/telego"
	ta "github.com/mymmrac/telego/telegoapi"
	"github.com/valyala/fasthttp"
)

// With Telegram unreachable a send hangs for its whole fasthttp timeout, and
// the event bus, so the panel restart behind it, waited that long.
func TestStopBotEndsInFlightTelegramCall(t *testing.T) {
	arrived := make(chan struct{}, 1)
	release := make(chan struct{})
	hang := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		arrived <- struct{}{}
		<-release
	}))
	t.Cleanup(func() { close(release); hang.Close() })

	stop := make(chan struct{})
	b, err := telego.NewBot(testBotToken, telego.WithAPIServer(hang.URL),
		telego.WithAPICaller(stoppableCaller{inner: ta.FastHTTPCaller{Client: &fasthttp.Client{}}, stopped: stop}))
	if err != nil {
		t.Fatalf("NewBot: %v", err)
	}
	origBot := liveBot()
	botMu.Lock()
	bot, botStop = b, stop
	botMu.Unlock()
	t.Cleanup(func() { setTestBot(origBot) })

	errc := make(chan error, 1)
	go func() {
		_, err := b.GetMe(context.Background())
		errc <- err
	}()
	select {
	case <-arrived:
	case <-time.After(5 * time.Second):
		t.Fatal("getMe never reached the fake Telegram API")
	}

	StopBot()
	if liveBot() != nil {
		t.Fatal("StopBot must remove the stopped Bot from the live connection")
	}
	// A receiver scheduled immediately before StopBot must not restart
	// without a connection, or panic when reading a removed Bot.
	(&Tgbot{}).OnReceive()
	if (&Tgbot{}).IsRunning() {
		t.Fatal("a delayed receiver resurrected the stopped Bot")
	}

	select {
	case err := <-errc:
		if !errors.Is(err, errBotStopped) {
			t.Fatalf("getMe returned %v, want errBotStopped", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("getMe still blocked 2s after StopBot")
	}
	if _, err := b.GetMe(context.Background()); !errors.Is(err, errBotStopped) {
		t.Fatalf("call after StopBot returned %v, want errBotStopped", err)
	}
	select {
	case <-arrived:
		t.Fatal("a call after StopBot still went out to Telegram")
	default:
	}
}

type blockedTelegramCaller struct {
	started chan struct{}
	release chan struct{}
	calls   atomic.Int32
}

func (c *blockedTelegramCaller) Call(context.Context, string, *ta.RequestData) (*ta.Response, error) {
	if c.calls.Add(1) == 1 {
		close(c.started)
	}
	<-c.release
	return &ta.Response{}, nil
}

func TestVelaSecretChangeRetiresInFlightAndFutureBotCalls(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	file := filepath.Join(t.TempDir(), "bot-token")
	const initial = "12345:synthetic_previous"
	if err := os.WriteFile(file, []byte(initial), 0o600); err != nil {
		t.Fatal(err)
	}
	t.Setenv("XUI_TG_MINIAPP_BOT_TOKEN_FILE", file)
	inner := &blockedTelegramCaller{started: make(chan struct{}), release: make(chan struct{})}
	t.Cleanup(func() {
		select {
		case <-inner.release:
		default:
			close(inner.release)
		}
	})
	allowed := botCredentialCheck(true, initial)
	caller := stoppableCaller{inner: inner, credentialAllowed: allowed}
	errs := make(chan error, 1)
	go func() {
		_, err := caller.Call(context.Background(), "", nil)
		errs <- err
	}()
	select {
	case <-inner.started:
	case <-time.After(3 * time.Second):
		t.Fatal("initial fixture call was unexpectedly rejected")
	}
	if err := os.WriteFile(file, []byte("12345:synthetic_replacement"), 0o600); err != nil {
		t.Fatal(err)
	}
	close(inner.release)
	select {
	case err := <-errs:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("response from the retired connection was accepted: %v", err)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("fixture request did not complete")
	}
	if err := os.WriteFile(file, []byte(initial), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := caller.Call(context.Background(), "", nil); !errors.Is(err, context.Canceled) {
		t.Fatal("restoring the old Secret reactivated a retired Bot")
	}
	if got := inner.calls.Load(); got != 1 {
		t.Fatalf("retired Bot reached the transport: %d calls", got)
	}
	if !botCredentialCheck(true, initial)() {
		t.Fatal("a fresh Bot cannot use the configured Secret")
	}
}
