package tgminiapp

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func configureCertAlertTest(t *testing.T) string {
	t.Helper()
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	t.Setenv("XUI_TG_CERT_ALERT_ENABLED", "true")
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "123456789,987654321")
	path := filepath.Join(t.TempDir(), "vela-cert-alerts.json")
	t.Setenv("XUI_TG_CERT_ALERT_STATE_FILE", path)
	return path
}

func expiringTestCert(now time.Time) CertificateStatus {
	expires := now.Add(5 * 24 * time.Hour)
	return CertificateStatus{
		Purpose: "panel", DNSNames: []string{"private-node.example.test"},
		Issuer: "Private Example CA", ValidUntil: &expires,
		DaysRemaining: 5, Status: "expiring",
	}
}

func TestCertAlertsOffByDefault(t *testing.T) {
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	t.Setenv("XUI_TG_CERT_ALERT_ENABLED", "")
	n, err := SendCertificateAlerts(time.Now(), []CertificateStatus{{Status: "expired"}}, func(int64, string) bool {
		t.Fatal("must never send by default")
		return true
	})
	if err != nil || n != 0 {
		t.Fatalf("disabled alert: count=%d err=%v", n, err)
	}
}

func TestCertAlertDeduplicatesAcrossRestartsAndKeepsDetailsPrivate(t *testing.T) {
	path := configureCertAlertTest(t)
	now := time.Date(2026, 11, 15, 0, 0, 0, 0, time.UTC)
	certs := []CertificateStatus{expiringTestCert(now)}
	sent := map[int64]int{}
	sender := func(id int64, body string) bool {
		sent[id]++
		for _, secret := range []string{"private-node.example.test", "Private Example CA", "/etc/x-ui/", "123456789", "987654321"} {
			if strings.Contains(body, secret) {
				t.Fatalf("private data in telegram message")
			}
		}
		return true
	}
	for i, want := range []int{2, 0} {
		count, err := SendCertificateAlerts(now.Add(time.Duration(i)*time.Hour), certs, sender)
		if err != nil || count != want {
			t.Fatalf("run %d: got %d, err %v", i, count, err)
		}
	}
	for id, count := range sent {
		if count != 1 {
			t.Fatalf("recipient %d got %d sends", id, count)
		}
	}
	state, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(state), "123456789") || strings.Contains(string(state), "private-node") || strings.Contains(string(state), "Private Example") {
		t.Fatal("state contains private data")
	}
	info, err := os.Stat(path)
	if err != nil || info.Mode().Perm() != 0600 {
		t.Fatalf("state permissions: %v %v", info, err)
	}
}

func TestCertAlertFailureRetriesOnlyFailedRecipient(t *testing.T) {
	configureCertAlertTest(t)
	now := time.Date(2026, 11, 15, 0, 0, 0, 0, time.UTC)
	first, err := SendCertificateAlerts(now, []CertificateStatus{expiringTestCert(now)}, func(id int64, _ string) bool { return id == 123456789 })
	if err != nil || first != 1 {
		t.Fatalf("first send: %d / %v", first, err)
	}
	var ids []int64
	second, err := SendCertificateAlerts(now, []CertificateStatus{expiringTestCert(now)}, func(id int64, _ string) bool { ids = append(ids, id); return true })
	if err != nil || second != 1 || len(ids) != 1 || ids[0] != 987654321 {
		t.Fatalf("retry: count %d ids %v err %v", second, ids, err)
	}
}

func TestCertAlertThresholds(t *testing.T) {
	configureCertAlertTest(t)
	now := time.Date(2026, 11, 15, 0, 0, 0, 0, time.UTC)
	cert := expiringTestCert(now)
	total := 0
	for _, day := range []int{0, 1, 2, 3, 4, 5, 6, 7} {
		sent, err := SendCertificateAlerts(now.Add(time.Duration(day)*24*time.Hour), []CertificateStatus{cert}, func(int64, string) bool { return true })
		if err != nil {
			t.Fatal(err)
		}
		total += sent
	}
	// Five days -> 7-day milestone, three days -> 3-day milestone,
	// one day -> 1-day milestone, then expired. Each delivered to two IDs.
	if total != 8 {
		t.Fatalf("milestones count got %d want 8", total)
	}
}

func TestCertAlertRejectsUnsafeStateAndInvalidAllowlist(t *testing.T) {
	path := configureCertAlertTest(t)
	now := time.Now()
	certs := []CertificateStatus{expiringTestCert(now)}
	blocked := func(int64, string) bool { t.Fatal("must not send"); return true }
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "123456789,-1001")
	if _, err := SendCertificateAlerts(now, certs, blocked); err == nil {
		t.Fatal("group chat must be rejected")
	}
	t.Setenv("XUI_TG_MINIAPP_ADMIN_IDS", "123456789")
	if err := os.WriteFile(path, []byte("not json"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := SendCertificateAlerts(now, certs, blocked); err == nil {
		t.Fatal("corrupt state must fail closed")
	}
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	outside := filepath.Join(t.TempDir(), "outside")
	if err := os.WriteFile(outside, []byte(`{"sent":{}}`), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.Symlink(outside, path); err != nil {
		t.Fatal(err)
	}
	if _, err := SendCertificateAlerts(now, certs, blocked); err == nil {
		t.Fatal("symlink state must be refused")
	}
}

func TestCertAlertUnconfiguredOrHealthyNeverSends(t *testing.T) {
	configureCertAlertTest(t)
	certs := []CertificateStatus{{Purpose: "panel", Status: "unconfigured"}, {Purpose: "subscription", Status: "valid"}}
	count, err := SendCertificateAlerts(time.Now(), certs, func(int64, string) bool { t.Fatal("must not send"); return true })
	if err != nil || count != 0 {
		t.Fatalf("count %d err %v", count, err)
	}
}
