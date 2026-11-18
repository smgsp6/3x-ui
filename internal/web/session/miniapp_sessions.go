package session

import (
	"crypto/rand"
	"encoding/base64"
	"errors"
	"sync"
	"time"
)

// The upstream Gin cookie store signs client-side state. Clearing the browser
// cookie alone cannot revoke a stolen copy. Vela tracks only randomly issued
// Mini App session IDs in process memory so a copied cookie can be revoked.
// This is deliberately scoped to a single panel process; multi-replica Vela
// requires a shared server-side session store before it can be supported.
const telegramMiniAppSessionKey = "TELEGRAM_MINIAPP_SESSION_ID"
const miniAppSessionLifetime = 8 * time.Hour
const maxMiniAppSessions = 4096

var miniAppSessions = struct {
	sync.Mutex
	policy string
	active map[string]time.Time
}{active: make(map[string]time.Time)}

// Called with the policy mutex held. The registry never acquires that mutex.
func setMiniAppSessionPolicy(nonce string) {
	miniAppSessions.Lock()
	defer miniAppSessions.Unlock()
	if miniAppSessions.policy != nonce {
		miniAppSessions.policy = nonce
		clear(miniAppSessions.active)
	}
}

func issueMiniAppSession(nonce string) (string, error) {
	var random [32]byte
	if _, err := rand.Read(random[:]); err != nil {
		return "", err
	}
	id := base64.RawURLEncoding.EncodeToString(random[:])
	now := time.Now()
	miniAppSessions.Lock()
	defer miniAppSessions.Unlock()
	if nonce == "" || nonce != miniAppSessions.policy {
		return "", errors.New("Mini App session policy changed")
	}
	// Prune on issue, rather than scheduling a goroutine or putting any
	// Telegram identifiers in the registry. An overloaded registry fails
	// closed instead of growing without bound.
	for key, until := range miniAppSessions.active {
		if !now.Before(until) {
			delete(miniAppSessions.active, key)
		}
	}
	if len(miniAppSessions.active) >= maxMiniAppSessions {
		return "", errors.New("too many active Mini App sessions")
	}
	miniAppSessions.active[id] = now.Add(miniAppSessionLifetime)
	return id, nil
}

func miniAppSessionActive(id string) bool {
	if len(id) != 43 {
		return false
	}
	miniAppSessions.Lock()
	defer miniAppSessions.Unlock()
	until, found := miniAppSessions.active[id]
	if !found {
		return false
	}
	if !time.Now().Before(until) {
		delete(miniAppSessions.active, id)
		return false
	}
	return true
}

func revokeMiniAppSession(id string) {
	if id == "" {
		return
	}
	miniAppSessions.Lock()
	delete(miniAppSessions.active, id)
	miniAppSessions.Unlock()
}
