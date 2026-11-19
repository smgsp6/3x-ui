package tgminiapp

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestTLSCertificateReloaderKeepsGoodCertDuringPartialRenewal(t *testing.T) {
	now := time.Now()
	dir := t.TempDir()
	certPath, keyPath := writeTestCert(t, dir, now.Add(-time.Hour), now.Add(30*24*time.Hour))
	initial, err := tls.LoadX509KeyPair(certPath, keyPath)
	if err != nil {
		t.Fatal(err)
	}
	r := NewTLSCertificateReloader(certPath, keyPath, initial)
	previous := r.currentAt(now).Certificate[0]

	// An ACME implementation may replace its certificate before its key.
	newDir := t.TempDir()
	updatedCert, updatedKey := writeTestCert(t, newDir, now.Add(-time.Hour), now.Add(85*24*time.Hour))
	certBytes, err := os.ReadFile(updatedCert)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(certPath, certBytes, 0600); err != nil {
		t.Fatal(err)
	}
	observed := r.currentAt(now.Add(31 * time.Second))
	if string(observed.Certificate[0]) != string(previous) {
		t.Fatal("half-written renewal replaced a valid certificate")
	}

	keyBytes, err := os.ReadFile(updatedKey)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(keyPath, keyBytes, 0600); err != nil {
		t.Fatal(err)
	}
	observed = r.currentAt(now.Add(62 * time.Second))
	if string(observed.Certificate[0]) == string(previous) {
		t.Fatal("complete renewal was not loaded")
	}
	leaf, err := x509.ParseCertificate(observed.Certificate[0])
	if err != nil {
		t.Fatal(err)
	}
	if leaf.NotAfter.Before(now.Add(80 * 24 * time.Hour)) {
		t.Fatal("new certificate expiry not observed")
	}
	if _, err := r.GetCertificate(nil); err != nil {
		t.Fatal(err)
	}
}

func TestLoadServerTLSKeyPairRejectsExpiredVelaCertificate(t *testing.T) {
	now := time.Now()
	certPath, keyPath := writeTestCert(t, t.TempDir(), now.Add(-48*time.Hour), now.Add(-24*time.Hour))
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "false")
	if _, err := LoadServerTLSKeyPair(certPath, keyPath); err != nil {
		t.Fatalf("legacy loader rejected a PEM pair: %v", err)
	}
	t.Setenv("XUI_TG_MINIAPP_ENABLED", "true")
	if _, err := LoadServerTLSKeyPair(certPath, keyPath); err == nil {
		t.Fatal("Vela accepted an expired PEM pair at startup")
	}
}

func TestTLSCertificateReloaderRejectsInvalidRenewal(t *testing.T) {
	now := time.Now()
	dir := t.TempDir()
	certPath, keyPath := writeTestCert(t, dir, now.Add(-time.Hour), now.Add(90*24*time.Hour))
	initial, err := tls.LoadX509KeyPair(certPath, keyPath)
	if err != nil {
		t.Fatal(err)
	}
	r := NewTLSCertificateReloader(certPath, keyPath, initial)
	original := r.currentAt(now)
	if err := os.WriteFile(certPath, make([]byte, maxTLSPEMBytes+1), 0600); err != nil {
		t.Fatal(err)
	}
	if got := r.currentAt(now.Add(31 * time.Second)); got != original {
		t.Fatal("oversize renewal should not replace last valid certificate")
	}
	if _, err := safeLoadTLSKeyPair(filepath.Join(dir, "missing"), keyPath); err == nil {
		t.Fatal("missing certificate accepted")
	}
}

func TestTLSCertificateReloaderConcurrentHandshakes(t *testing.T) {
	now := time.Now()
	dir := t.TempDir()
	certPath, keyPath := writeTestCert(t, dir, now.Add(-time.Hour), now.Add(90*24*time.Hour))
	initial, err := tls.LoadX509KeyPair(certPath, keyPath)
	if err != nil {
		t.Fatal(err)
	}
	r := NewTLSCertificateReloader(certPath, keyPath, initial)
	done := make(chan struct{})
	for i := 0; i < 20; i++ {
		go func() {
			defer func() { done <- struct{}{} }()
			for j := 0; j < 50; j++ {
				cert, err := r.GetCertificate(nil)
				if err != nil || cert == nil || len(cert.Certificate) == 0 {
					panic("missing cert")
				}
			}
		}()
	}
	for i := 0; i < 20; i++ {
		<-done
	}
}

// Verifies the actual crypto/tls selection path for a connection that omits
// SNI; the original static Certificates list must be empty in Vela mode.
func TestTLSReloadWithoutClientSNI(t *testing.T) {
	now := time.Now()
	dir := t.TempDir()
	certPath, keyPath := writeTestCert(t, dir, now.Add(-time.Hour), now.Add(40*24*time.Hour))
	initial, err := tls.LoadX509KeyPair(certPath, keyPath)
	if err != nil {
		t.Fatal(err)
	}
	r := NewTLSCertificateReloader(certPath, keyPath, initial)
	listener, err := tls.Listen("tcp", "127.0.0.1:0", &tls.Config{
		GetCertificate: r.GetCertificate,
		MinVersion:     tls.VersionTLS12,
	})
	if err != nil {
		t.Fatal(err)
	}
	defer listener.Close()

	connect := func() *x509.Certificate {
		t.Helper()
		result := make(chan error, 1)
		go func() {
			conn, err := listener.Accept()
			if err != nil {
				result <- err
				return
			}
			defer conn.Close()
			result <- conn.(*tls.Conn).Handshake()
		}()
		client, err := tls.DialWithDialer(&net.Dialer{Timeout: 3 * time.Second}, "tcp", listener.Addr().String(), &tls.Config{
			InsecureSkipVerify: true, // local self-signed test-only certificate
			MinVersion:         tls.VersionTLS12,
		})
		if err != nil {
			t.Fatal(err)
		}
		defer client.Close()
		leaf := client.ConnectionState().PeerCertificates[0]
		if err := <-result; err != nil {
			t.Fatal(err)
		}
		return leaf
	}
	old := connect()
	updatedCert, updatedKey := writeTestCert(t, t.TempDir(), now.Add(-time.Hour), now.Add(90*24*time.Hour))
	pemCert, err := os.ReadFile(updatedCert)
	if err != nil {
		t.Fatal(err)
	}
	pemKey, err := os.ReadFile(updatedKey)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(certPath, pemCert, 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(keyPath, pemKey, 0600); err != nil {
		t.Fatal(err)
	}
	// Test-only forced clock advance through an internal method; production
	// rechecks automatically when at least 30 seconds have elapsed.
	newPair := r.currentAt(now.Add(time.Minute))
	if len(newPair.Certificate) == 0 {
		t.Fatal("invalid rotated certificate")
	}
	newLeaf := connect()
	if old.Equal(newLeaf) {
		t.Fatal("TLS handshake still served original cert")
	}
	if newLeaf.NotAfter.Before(now.Add(80 * 24 * time.Hour)) {
		t.Fatal("unexpected expiry")
	}
}

func TestTLSCertificateReloaderNeverLoadsExpiredOrDowngradedPair(t *testing.T) {
	now := time.Now()
	dir := t.TempDir()
	certPath, keyPath := writeTestCert(t, dir, now.Add(-time.Hour), now.Add(90*24*time.Hour))
	initial, err := tls.LoadX509KeyPair(certPath, keyPath)
	if err != nil {
		t.Fatal(err)
	}
	r := NewTLSCertificateReloader(certPath, keyPath, initial)
	first := r.currentAt(now)
	for i, validity := range []struct{ start, end time.Time }{
		{now.Add(-45 * 24 * time.Hour), now.Add(-24 * time.Hour)},
		{now.Add(time.Hour), now.Add(95 * 24 * time.Hour)},
		{now.Add(-time.Hour), now.Add(60 * 24 * time.Hour)},
	} {
		other, key := writeTestCert(t, t.TempDir(), validity.start, validity.end)
		b, err := os.ReadFile(other)
		if err != nil {
			t.Fatal(err)
		}
		k, err := os.ReadFile(key)
		if err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(certPath, b, 0600); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(keyPath, k, 0600); err != nil {
			t.Fatal(err)
		}
		if got := r.currentAt(now.Add(time.Duration(i+1) * time.Minute)); got != first {
			t.Fatalf("invalid/downgraded certificate %d replaced the active one", i)
		}
	}
}

// ACME can return a valid keypair for a different domain by mistake. Do not
// replace a working panel identity simply because its validity is longer.
func TestTLSReloadRejectsUnrelatedDomain(t *testing.T) {
	now := time.Now()
	dir := t.TempDir()
	certPath, keyPath := writeTestCertWithName(t, dir, now.Add(-time.Hour), now.Add(30*24*time.Hour), "original.example.test")
	initial, err := tls.LoadX509KeyPair(certPath, keyPath)
	if err != nil {
		t.Fatal(err)
	}
	r := NewTLSCertificateReloader(certPath, keyPath, initial)
	old := r.currentAt(now)
	c, k := writeTestCertWithName(t, t.TempDir(), now.Add(-time.Hour), now.Add(90*24*time.Hour), "different.example.test")
	crt, err := os.ReadFile(c)
	if err != nil {
		t.Fatal(err)
	}
	key, err := os.ReadFile(k)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(certPath, crt, 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(keyPath, key, 0600); err != nil {
		t.Fatal(err)
	}
	if got := r.currentAt(now.Add(time.Minute)); got != old {
		t.Fatal("unrelated hostname silently replaced active TLS certificate")
	}
}

func TestTLSRenewalIdentityRequiresAllPreviousSANs(t *testing.T) {
	old := &x509.Certificate{
		DNSNames:    []string{"example.test", "*.example.test"},
		IPAddresses: []net.IP{net.ParseIP("192.0.2.1")},
	}
	candidate := &x509.Certificate{
		DNSNames:    []string{"example.test", "*.example.test", "additional.example.test"},
		IPAddresses: []net.IP{net.ParseIP("192.0.2.1"), net.ParseIP("192.0.2.2")},
	}
	if !keepsCertificateIdentity(old, candidate) {
		t.Fatal("adding SANs should be allowed")
	}
	candidate.DNSNames = []string{"example.test", "additional.example.test"}
	if keepsCertificateIdentity(old, candidate) {
		t.Fatal("missing wildcard DNS SAN accepted")
	}
	candidate.DNSNames = []string{"example.test", "*.example.test"}
	candidate.IPAddresses = []net.IP{net.ParseIP("192.0.2.2")}
	if keepsCertificateIdentity(old, candidate) {
		t.Fatal("missing IP SAN accepted")
	}
	old = &x509.Certificate{Subject: pkix.Name{CommonName: "legacy.example.test"}}
	candidate = &x509.Certificate{Subject: pkix.Name{CommonName: "other.example.test"}}
	if keepsCertificateIdentity(old, candidate) {
		t.Fatal("legacy CN identity replacement accepted")
	}
}

func TestTLSReloaderRefreshesChainWithSameLeaf(t *testing.T) {
	now := time.Now()
	path, key := writeTestCert(t, t.TempDir(), now.Add(-time.Hour), now.Add(30*24*time.Hour))
	initial, err := tls.LoadX509KeyPair(path, key)
	if err != nil {
		t.Fatal(err)
	}
	caKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	ca := &x509.Certificate{
		SerialNumber: big.NewInt(2), Subject: pkix.Name{CommonName: "Test issuer"},
		NotBefore: now.Add(-time.Hour), NotAfter: now.Add(60 * 24 * time.Hour),
		BasicConstraintsValid: true, IsCA: true, KeyUsage: x509.KeyUsageCertSign,
	}
	caDER, err := x509.CreateCertificate(rand.Reader, ca, ca, &caKey.PublicKey, caKey)
	if err != nil {
		t.Fatal(err)
	}
	leafDER, err := x509.CreateCertificate(rand.Reader, initial.Leaf, ca, initial.Leaf.PublicKey, caKey)
	if err != nil {
		t.Fatal(err)
	}
	leafPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: leafDER})
	chainPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: caDER})
	if err := os.WriteFile(path, leafPEM, 0600); err != nil {
		t.Fatal(err)
	}
	initial, err = tls.LoadX509KeyPair(path, key)
	if err != nil {
		t.Fatal(err)
	}
	reloader := NewTLSCertificateReloader(path, key, initial)
	if err := os.WriteFile(path, append(append([]byte{}, leafPEM...), chainPEM...), 0600); err != nil {
		t.Fatal(err)
	}
	updated := reloader.currentAt(now.Add(2 * tlsRefreshInterval))
	if len(updated.Certificate) != 2 {
		t.Fatalf("expected updated chain with unchanged leaf, got %d certificates", len(updated.Certificate))
	}
	if err := os.WriteFile(path, leafPEM, 0600); err != nil {
		t.Fatal(err)
	}
	if got := reloader.currentAt(now.Add(4 * tlsRefreshInterval)); got != updated {
		t.Fatal("a partially written bundle dropped the active issuer certificate")
	}
	unrelated := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: leafDER})
	if err := os.WriteFile(path, append(append([]byte{}, leafPEM...), unrelated...), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := safeLoadTLSKeyPair(path, key); err == nil {
		t.Fatal("accepted an unrelated certificate as issuer")
	}
	if status := InspectCertificate("panel", path, key, now); status.Status != "invalid" {
		t.Fatalf("invalid issuer reported as %s on the certificate page", status.Status)
	}

	renewedLeaf := *initial.Leaf
	renewedLeaf.SerialNumber = big.NewInt(3)
	renewedLeaf.NotAfter = now.Add(45 * 24 * time.Hour)
	renewedDER, err := x509.CreateCertificate(rand.Reader, &renewedLeaf, ca, renewedLeaf.PublicKey, caKey)
	if err != nil {
		t.Fatal(err)
	}
	renewedPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: renewedDER})
	if err := os.WriteFile(path, renewedPEM, 0600); err != nil {
		t.Fatal(err)
	}
	if got := reloader.currentAt(now.Add(6 * tlsRefreshInterval)); got != updated {
		t.Fatal("a new leaf from the same issuer replaced the full chain before its issuer arrived")
	}
	if err := os.WriteFile(path, append(renewedPEM, chainPEM...), 0600); err != nil {
		t.Fatal(err)
	}
	if got := reloader.currentAt(now.Add(8 * tlsRefreshInterval)); got == updated || len(got.Certificate) != 2 {
		t.Fatal("complete renewed chain did not replace the previous chain")
	}
}
