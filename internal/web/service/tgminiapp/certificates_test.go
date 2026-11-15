package tgminiapp

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/json"
	"encoding/pem"
	"math/big"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func writeTestCert(t *testing.T, dir string, start, end time.Time) (string, string) {
	return writeTestCertWithName(t, dir, start, end, "example.test")
}

func writeTestCertWithName(t *testing.T, dir string, start, end time.Time, hostname string) (string, string) {
	t.Helper()
	privateKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	template := &x509.Certificate{
		SerialNumber: big.NewInt(1),
		Subject:      pkix.Name{CommonName: hostname},
		DNSNames:     []string{hostname},
		NotBefore:    start, NotAfter: end,
		KeyUsage:    x509.KeyUsageDigitalSignature,
		ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
	}
	der, err := x509.CreateCertificate(rand.Reader, template, template, &privateKey.PublicKey, privateKey)
	if err != nil {
		t.Fatal(err)
	}
	keyDER, err := x509.MarshalECPrivateKey(privateKey)
	if err != nil {
		t.Fatal(err)
	}
	certPath, keyPath := filepath.Join(dir, "cert.pem"), filepath.Join(dir, "key.pem")
	if err := os.WriteFile(certPath, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der}), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(keyPath, pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: keyDER}), 0600); err != nil {
		t.Fatal(err)
	}
	return certPath, keyPath
}

func TestInspectCertificate(t *testing.T) {
	now := time.Date(2026, 11, 15, 12, 0, 0, 0, time.UTC)
	if got := InspectCertificate("panel", "", "", now); got.Status != "unconfigured" {
		t.Fatalf("empty: %+v", got)
	}
	if got := InspectCertificate("panel", "missing.pem", "key.pem", now); got.Status != "invalid" {
		t.Fatalf("missing: %+v", got)
	}
	testCases := []struct {
		name     string
		until    time.Time
		expected string
	}{
		{"valid", now.Add(40 * 24 * time.Hour), "valid"},
		{"expiring", now.Add(5 * 24 * time.Hour), "expiring"},
		{"expired", now.Add(-24 * time.Hour), "expired"},
	}
	for _, tc := range testCases {
		t.Run(tc.name, func(t *testing.T) {
			dir := t.TempDir()
			certPath, keyPath := writeTestCert(t, dir, now.Add(-60*24*time.Hour), tc.until)
			got := InspectCertificate("panel", certPath, keyPath, now)
			if got.Status != tc.expected {
				t.Fatalf("got %s, want %s: %+v", got.Status, tc.expected, got)
			}
			if len(got.DNSNames) != 1 || got.DNSNames[0] != "example.test" {
				t.Fatalf("bad names: %+v", got.DNSNames)
			}
		})
	}
	t.Run("key mismatch", func(t *testing.T) {
		certA, keyA := writeTestCert(t, t.TempDir(), now.Add(-24*time.Hour), now.Add(90*24*time.Hour))
		_, keyB := writeTestCert(t, t.TempDir(), now.Add(-24*time.Hour), now.Add(90*24*time.Hour))
		_ = keyA
		if got := InspectCertificate("panel", certA, keyB, now); got.Status != "invalid" {
			t.Fatalf("unexpected: %+v", got)
		}
	})
}

func TestNotYetValidCertificate(t *testing.T) {
	now := time.Date(2026, 11, 15, 0, 0, 0, 0, time.UTC)
	cert, key := writeTestCert(t, t.TempDir(), now.Add(time.Hour), now.Add(90*24*time.Hour))
	got := InspectCertificate("panel", cert, key, now)
	if got.Status != "invalid" {
		t.Fatalf("future certificate must not appear valid, got %q", got.Status)
	}
}

func TestRejectOversizedCertificateFile(t *testing.T) {
	dir := t.TempDir()
	cert, key := writeTestCert(t, dir, time.Now().Add(-time.Hour), time.Now().Add(24*time.Hour))
	// A misconfigured path might point at a huge file. Inspection must reject it.
	if err := os.WriteFile(cert, make([]byte, 2<<20+1), 0600); err != nil {
		t.Fatal(err)
	}
	if got := InspectCertificate("panel", cert, key, time.Now()); got.Status != "invalid" {
		t.Fatalf("unexpected status for oversized certificate: %v", got.Status)
	}
}

func TestCertificateMetadataNeverContainsServerFilesystemPaths(t *testing.T) {
	dir := t.TempDir()
	cert, key := writeTestCert(t, dir, time.Now().Add(-time.Hour), time.Now().Add(40*24*time.Hour))
	status := InspectCertificate("panel", cert, key, time.Now())
	payload, err := json.Marshal(status)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(payload), dir) || strings.Contains(string(payload), cert) || strings.Contains(string(payload), key) || strings.Contains(string(payload), "certificateFile") {
		t.Fatalf("internal filesystem location was exposed by certificate metadata")
	}
}
