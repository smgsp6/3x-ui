package tgbot

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"

	"github.com/mhsanaei/3x-ui/v3/internal/logger"

	"github.com/mymmrac/telego"
	tu "github.com/mymmrac/telego/telegoutil"
	"github.com/nicksnyder/go-i18n/v2/i18n"
)

func TestIsTelegramNotModifiedError(t *testing.T) {
	tests := []struct {
		name string
		err  error
		want bool
	}{
		{"nil error", nil, false},
		{"not modified", errors.New("Bad Request: message is not modified"), true},
		{"No fields to modify", errors.New("Bad Request: No fields to modify"), true},
		{"unrelated error", errors.New("Bad Request: message to edit not found"), false},
		{"network error", errors.New("connection reset"), false},
		{"empty string", errors.New(""), false},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := isTelegramNotModifiedError(tt.err)
			if got != tt.want {
				t.Errorf("isTelegramNotModifiedError(%v) = %v, want %v", tt.err, got, tt.want)
			}
		})
	}
}

// telego.NewBot rejects any token that does not match `^\d+:[\w-]{35}$`.
var testBotToken = "123456:" + strings.Repeat("a", 35)

func TestEditMessageTgBotSkipsNotModified(t *testing.T) {
	// Mock Telegram API that always returns "message is not modified".
	mock := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"ok":          false,
			"error_code":  400,
			"description": "Bad Request: message is not modified: specified new message content and reply markup are exactly the same as a current content and reply markup of the message.",
		})
	}))
	defer mock.Close()

	// Replace the package-level bot only while holding its mutex.
	origBot := liveBot()
	t.Cleanup(func() { setTestBot(origBot) })
	mockBot, err := telego.NewBot(testBotToken, telego.WithAPIServer(mock.URL))
	if err != nil {
		t.Fatalf("NewBot: %v", err)
	}
	setTestBot(mockBot)

	// Snapshot warning count before the edit call.
	before := logger.GetLogs(100, "warning")

	tb := &Tgbot{}
	tb.editMessageTgBot(123, 456, "<b>hello</b>")

	after := logger.GetLogs(100, "warning")
	if len(after) > len(before) {
		t.Errorf("editMessageTgBot logged %d new warnings, want 0; new entries: %v",
			len(after)-len(before), after[len(before):])
	}
}

func TestEditMessageCallbackTgBotSkipsNotModified(t *testing.T) {
	mock := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{
			"ok":          false,
			"error_code":  400,
			"description": "Bad Request: message is not modified",
		})
	}))
	defer mock.Close()

	origBot := liveBot()
	t.Cleanup(func() { setTestBot(origBot) })
	mockBot, err := telego.NewBot(testBotToken, telego.WithAPIServer(mock.URL))
	if err != nil {
		t.Fatalf("NewBot: %v", err)
	}
	setTestBot(mockBot)

	before := logger.GetLogs(100, "warning")

	tb := &Tgbot{}
	kb := tu.InlineKeyboard(tu.InlineKeyboardRow(
		tu.InlineKeyboardButton("btn").WithCallbackData("test"),
	))
	tb.editMessageCallbackTgBot(123, 456, kb)

	after := logger.GetLogs(100, "warning")
	if len(after) > len(before) {
		t.Errorf("editMessageCallbackTgBot logged %d new warnings, want 0; new entries: %v",
			len(after)-len(before), after[len(before):])
	}
}

func TestPageMessageSplitsLinkListWithoutBlankLines(t *testing.T) {
	var message strings.Builder
	message.WriteString("Individual links:\r\n")
	for range 50 {
		message.WriteString("<code>vless://" + strings.Repeat("a", 300) + "</code>\r\n")
	}

	pages := pageMessage(message.String(), telegramPageLimit)
	if len(pages) < 2 {
		t.Fatalf("pageMessage() returned %d page, want multiple", len(pages))
	}

	links := 0
	for index, page := range pages {
		if len(page) > telegramPageLimit {
			t.Errorf("page %d has %d bytes, want at most %d", index, len(page), telegramPageLimit)
		}
		openingTags := strings.Count(page, "<code>")
		closingTags := strings.Count(page, "</code>")
		if openingTags != closingTags {
			t.Errorf("page %d has %d opening tags and %d closing tags", index, openingTags, closingTags)
		}
		links += openingTags
	}
	if links != 50 {
		t.Errorf("pages contain %d links, want 50", links)
	}
}

// Regression test: callback answers are shown as plain text, so the entities
// I18nBot escapes for HTML-parsed messages must not surface in them.
func TestCallbackAnswerIsPlainText(t *testing.T) {
	var mu sync.Mutex
	var texts []string
	mock := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/bot"+testBotToken+"/answerCallbackQuery" {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		var body struct {
			Text string `json:"text"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		mu.Lock()
		texts = append(texts, body.Text)
		mu.Unlock()
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"ok": true, "result": true})
	}))
	defer mock.Close()
	swapTestBot(t, mock.URL)
	draftLocalizer(t, &i18n.Message{ID: "tgbot.answers.canceled", Other: "❌ {{ .Email }}: Operation canceled."})

	tb := &Tgbot{}
	tb.sendCallbackAnswerTgBot("q1", tb.I18nBot("tgbot.answers.canceled", "Email==a&b<c>"))

	mu.Lock()
	defer mu.Unlock()
	if len(texts) != 1 || texts[0] != "❌ a&b<c>: Operation canceled." {
		t.Errorf("answerCallbackQuery texts = %q, want the e-mail shown verbatim", texts)
	}
}


// Regression: StopBot may remove the live Bot between IsRunning and an API
// send. Simulate this state without any network or Telegram credentials.
func TestBotShutdownDoesNotDereferenceNilConnection(t *testing.T) {
	original := liveBot()
	tgBotMutex.Lock()
	originalRunning := isRunning
	isRunning = true
	tgBotMutex.Unlock()
	botMu.Lock()
	bot = nil
	botMu.Unlock()
	t.Cleanup(func() {
		botMu.Lock()
		bot = original
		botMu.Unlock()
		tgBotMutex.Lock()
		isRunning = originalRunning
		tgBotMutex.Unlock()
	})
	service := &Tgbot{}
	if id := service.SendMsgToTgbot(1001, "synthetic test"); id != 0 {
		t.Fatalf("stopped Bot returned message ID %d, want 0", id)
	}
	service.sendCallbackAnswerTgBot("synthetic-callback", "ok")
	service.editMessageTgBot(1001, 42, "synthetic test")
	service.deleteMessageTgBot(1001, 42)
	service.editMessageCallbackTgBot(1001, 42, nil)
}


// The panel can surface TestConnection errors to an operator. Telegram HTTP
// errors may contain the Bot Token, so the return value must be redacted,
// not merely the logger output. This exercises a loopback Bot API stub.
func TestVelaConnectionCheckNeverReturnsBotCredentials(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	mock := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusUnauthorized)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"ok": false, "error_code": 401,
			"description": "synthetic upstream error containing " + testBotToken,
		})
	}))
	defer mock.Close()
	swapTestBot(t, mock.URL)
	err := (&Tgbot{}).TestConnection()
	if err == nil {
		t.Fatal("synthetic Telegram API rejection must not succeed")
	}
	if strings.Contains(err.Error(), testBotToken) ||
		strings.Contains(err.Error(), "synthetic upstream error") ||
		strings.Contains(err.Error(), "/bot") {
		t.Fatal("Vela connection check returned private Bot API error details")
	}
}


// A Bot API gateway returning ok=true with a null result must not make Vela
// claim that Telegram connectivity is healthy.
func TestConnectionRejectsMalformedEmptyBotIdentity(t *testing.T) {
	mock := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{"ok": true, "result": nil})
	}))
	t.Cleanup(mock.Close)
	swapTestBot(t, mock.URL)
	if err := (&Tgbot{}).TestConnection(); err == nil {
		t.Fatal("empty Telegram bot identity was accepted as a healthy connection")
	}
}


// A 200/ok response with no real bot identity must never convince the
// control panel that Telegram authentication/network connectivity is healthy.
func TestConnectionRejectsMalformedSuccessIdentity(t *testing.T) {
	for _, tc := range []struct {
		name string
		result any
	}{
		{name: "null", result: nil},
		{name: "zero identity", result: map[string]any{"id": 0, "is_bot": false}},
		{name: "not a bot", result: map[string]any{"id": 42, "is_bot": false}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				_ = json.NewEncoder(w).Encode(map[string]any{"ok": true, "result": tc.result})
			}))
			t.Cleanup(srv.Close)
			swapTestBot(t, srv.URL)
			if err := (&Tgbot{}).TestConnection(); err == nil {
				t.Fatal("malformed getMe response was accepted as a live Telegram connection")
			}
		})
	}
}
